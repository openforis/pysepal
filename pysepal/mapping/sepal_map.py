"""The customized ``Map`` object."""

# known bug of rasterio
import os

from pysepal.mapping.bounds import (
    compute_center,
    compute_zoom_for_bounds,
    viewport_pixels_from_map,
)
from pysepal.mapping.fullscreen_control import FullScreenControl
from pysepal.mapping.gdal_env import GDAL_ENV_VARS, prune_foreign_gdal_env
from pysepal.mapping.visualization import validate_ee_object
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.theme import ThemeState

if any(var in os.environ for var in GDAL_ENV_VARS):
    prune_foreign_gdal_env()

import json
import math
import random
import string
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence, Union

import ee
import ipyleaflet as ipl
import ipyvuetify as v
import ipywidgets as widgets
import numpy as np
from eeclient.client import EESession
from ipyleaflet import TileLayer  # noqa: F401 - leave it here, it is used in the eval
from traitlets import Int as _TInt
from typing_extensions import Self

from pysepal import color as scolors
from pysepal.frontend import styles as ss
from pysepal.layers import LayerSpec, LayerStore, RenderLayer, prepare, prepare_sync
from pysepal.mapping._widget_tree import close_tree
from pysepal.mapping.basemaps import basemap_tiles
from pysepal.mapping.draw_control import GeomanDrawControl
from pysepal.mapping.inspector_control import InspectorControl
from pysepal.mapping.layer import EELayer
from pysepal.mapping.layer_engine import OVERLAY_PANE, LeafletEngine
from pysepal.mapping.layer_state_control import LayerStateControl
from pysepal.mapping.legend_control import LegendControl
from pysepal.mapping.zoom_control import ZoomControl
from pysepal.message import msg
from pysepal.scripts import decorator as sd
from pysepal.scripts import utils as su

if TYPE_CHECKING:
    from matplotlib import colors as mpc

__all__ = ["SepalMap"]

import logging

log = logging.getLogger("sepalui.mapping")

DEFAULT_MAP_WIDTH_PX = 1024

# the add_raster default, which stands for "no name given"
_DEFAULT_RASTER_NAME = "Layer_" + su.random_string()

# the arguments ee.FeatureCollection.style takes
_EE_STYLE_ARGS = frozenset(
    (
        "color",
        "pointSize",
        "pointShape",
        "width",
        "fillColor",
        "styleProperty",
        "neighborhood",
        "lineType",
    )
)


def _check_ee_inputs(ee_object: ee.ComputedObject, vis_params: dict) -> None:
    """Raise, before a spec is built, the errors ``add_ee_layer`` always raised for bad inputs.

    Raises:
        AttributeError: when ``ee_object`` is not an Earth Engine image, collection or vector.
        TypeError: when a vector is given a style argument ``ee.FeatureCollection.style`` lacks.
    """
    validate_ee_object(ee_object)
    if isinstance(ee_object, (ee.Geometry, ee.Feature, ee.FeatureCollection)):
        unknown = sorted(set(vis_params) - _EE_STYLE_ARGS)
        if unknown:
            raise TypeError(
                f"Unknown vector style arguments {unknown}, use {sorted(_EE_STYLE_ARGS)}."
            )


@contextmanager
def _unless_unbounded():
    """Skip an autocenter whose bounds Earth Engine cannot compute."""
    try:
        yield
    except Exception:
        log.debug("autocenter skipped: unable to compute bounds (unbounded image?)")


class SepalMap(ipl.Map):
    # ##########################################################################
    # ###                              Map parameters                        ###
    # ##########################################################################

    gee: bool = True
    "Either the map will use ee binding or not"

    v_inspector: Optional[InspectorControl] = None
    "The value inspector of the map"

    dc: Optional[GeomanDrawControl] = None
    "The drawing control of the map"

    _id: str = ""
    "A unique 6 letters str to identify the map in the DOM"

    state: Optional[LayerStateControl] = None
    "The statebar to inform the user about tile loading"

    layer_store: Optional[LayerStore] = None
    "The layers the map draws, top first: what the layer panel lists and edits"

    layer_engine: Optional[LeafletEngine] = None
    "Draws ``layer_store`` on the map"

    viewport_inset_left = _TInt(0)
    "Left overlay width in px. Set by the parent shell (e.g. MapApp) so fit_bounds targets the visible region."

    viewport_inset_right = _TInt(0)
    "Right overlay width in px. Set by the parent shell (e.g. MapApp) so fit_bounds targets the visible region."

    viewport_inset_bottom = _TInt(0)
    "Bottom overlay height in px. Set by the parent shell (e.g. MapApp narrow-mode bottom panel) so fit_bounds targets the visible region."

    canvas_width_px = _TInt(0)
    "Canvas width in px, pushed from the frontend."

    canvas_height_px = _TInt(0)
    "Canvas height in px, pushed from the frontend."

    def __init__(
        self,
        basemaps: List[str] = [],
        dc: bool = False,
        vinspector: bool = False,
        gee: bool = True,
        statebar: bool = False,
        theme_state: Optional[ThemeState] = None,
        gee_session: Optional[EESession] = None,
        gee_interface: Optional[GEEInterface] = None,
        fullscreen: bool = False,
        map_id: str = "",
        layer_store: Optional[LayerStore] = None,
        **kwargs,
    ) -> None:
        """Custom Map object design to build application.

        The SepalMap class inherits from ipyleaflet.Map. It can thus be initialized with all its parameter.
        The map will fall back to the SEPAL dark background that well fits with the rest of the pysepal layout.
        Numerous methods have been added in the class to help you deal with your workflow implementation.
        It can natively display raster from .tif files and files and ee objects using methods
        that have the same signature as the GEE JavaScripts console.

        Args:
            basemaps: the basemaps used as background in the map. If multiple selection, they will be displayed as layers.
            dc: whether or not the drawing control should be displayed. default to false
            vinspector: Add value inspector to map, useful to inspect pixel values. default to false
            gee: whether or not to use the ee binding. If False none of the earthengine display functionalities can be used. default to True
            statebar: whether or not to display the Statebar in the map
            theme_state: shared theme state for Solara apps
            gee_session (optional): a custom EESession object to do gee requests. default to None (deprecated in favor of gee_interface)
            gee_interface: a shared GEEInterface instance. If provided, takes precedence over gee_session
            fullscreen: whether or not to display the map in full screen. default to False
            layer_store: the layers to draw, for a store shared with other components. The layers already in it are drawn with their stored visibility. Defaults to a new, empty store.
            kwargs (optional): any parameter from a ipyleaflet.Map. if set, 'ee_initialize' will be overwritten.

        Raises:
            ValueError: if both gee_session and gee_interface are provided

        .. versionadded:: 3.0.0
            Added gee_interface parameter for sharing GEEInterface instances across components.
        """
        # Validate input parameters
        if gee_session and gee_interface:
            raise ValueError(
                "Cannot provide both gee_session and gee_interface. "
                "Use gee_interface for shared instances or gee_session for component-specific sessions."
            )

        log.debug(
            f"Map initialization with gee: {gee} and session: {gee_session} and interface: {gee_interface} ID: {id(gee_interface)}"
        )

        # set the default parameters
        kwargs.setdefault("center", [0, 0])
        kwargs.setdefault("zoom", 3)
        kwargs.setdefault("min_zoom", 3)
        kwargs.setdefault("max_zoom", 24)
        kwargs["basemap"] = {}
        kwargs["zoom_control"] = False
        kwargs["attribution_control"] = False
        kwargs["scroll_wheel_zoom"] = True
        kwargs.setdefault("world_copy_jump", True)

        if fullscreen:
            self.add_class("full-screen-map")

        # not an ipyleaflet trait, it only asks for the control below
        fullscreen_control = kwargs.pop("fullscreen_control", False)

        super().__init__(**kwargs)
        self._theme_source = None
        # the widgets this map built, closed with it
        self._owned = []
        parts = ("layout", "style", "default_style", "dragging_style")
        self._owned_parts = [
            getattr(self, n) for n in parts if not isinstance(kwargs.get(n), widgets.Widget)
        ]
        self.layer_store = layer_store if layer_store is not None else LayerStore()

        # init ee
        self.gee = gee
        if gee:
            if gee_interface:
                self.gee_interface = gee_interface
            else:
                # Raises under PER_CONNECTION when gee_session is None; keep it
                # ahead of init_ee() so a refused map initialises no global ee.
                self.gee_interface = GEEInterface(session=gee_session)
            su.init_ee()

        # add the basemaps, ipyleaflet's default one is discarded
        self._owned.extend([] if "layers" in kwargs else self.layers)
        self.clear()
        theme_source = theme_state if theme_state is not None else v.theme
        default_basemap = "SEPAL_DARK" if self._theme_is_dark(theme_source) else "SEPAL_LIGHT"
        basemaps = basemaps or [default_basemap]
        # dict.fromkeys, not set: a set has no order, so the basemap left visible
        # below would otherwise vary with the hash seed, i.e. at every restart.
        [self.add_basemap(basemap) for basemap in dict.fromkeys(basemaps)]

        self._apply_theme_class(default_basemap == "SEPAL_DARK")

        # set the visibility of all the basemaps to False but the first one
        [setattr(lyr, "visible", False) for lyr in self.layers]
        self.layers[0].visible = True

        # add the base controls
        base_controls = [
            ZoomControl(self),
            ipl.AttributionControl(position="bottomleft", prefix="SEPAL"),
            ipl.ScaleControl(position="bottomleft", imperial=False),
        ]
        if fullscreen_control:
            base_controls.append(FullScreenControl(self))
        for control in base_controls:
            self._owned.append(control)
            self.add(control)

        # specific drawing control
        self.dc = GeomanDrawControl(self)
        not dc or self.add(self.dc)

        # specific v_inspector
        self.v_inspector = InspectorControl(self)
        not vinspector or self.add(self.v_inspector)

        # specific statebar
        self.state = LayerStateControl(self)
        not statebar or self.add(self.state)

        # built even when hidden, and each one holds the map
        self._owned.extend([self.dc, self.v_inspector, self.state])

        # create a proxy ID to the element
        # this id should be unique and will be used by mutators to identify this map
        self._id = map_id or "".join(random.choice(string.ascii_lowercase) for i in range(6))
        self.add_class(self._id)
        self._bind_theme_source(theme_source)

        # Last: the layers of a given store then go over the basemaps, in the theme just
        # bound, and the state bar counts them.
        self.layer_engine = LeafletEngine(
            self, self.layer_store, gee_interface=getattr(self, "gee_interface", None)
        )

    def _on_theme_change(self, change) -> None:
        """Change the basemap layer."""
        layer_names = [layer.name for layer in self.layers]
        self._apply_theme_class(change["new"])

        # Before the basemap swap: replacing layers[0] makes the frontend rebuild
        # every layer view above it, and a view rebuilt ahead of its new url keeps
        # the old tiles (ipyleaflet's refresh skips tiles that are still loading).
        for layer in self.layers:
            self._apply_layer_theme(layer, bool(change["new"]))

        current, target = ("SEPAL_LIGHT", "SEPAL_DARK")
        if not change["new"]:
            current, target = target, current

        if basemap_tiles[current].name in layer_names:
            idx = layer_names.index(basemap_tiles[current].name)
            layer = self.layers[idx]
            # This is the way to make it work in solara do not ask me why
            new_layer = eval(str(basemap_tiles[target]))
            self.remove_layer(layer, base=True, none_ok=True)
            self.layers = self.layers[:idx] + (new_layer,) + self.layers[idx:]
            self._owned.append(new_layer)
            self._close_owned(layer)

    @staticmethod
    def _apply_layer_theme(layer: ipl.Layer, is_dark: bool) -> None:
        """Recolour a layer that follows the theme.

        An ``EELayer`` swaps to the tiles rendered for the theme (``theme_urls``); a
        layer with a ``style`` merges in ``theme_style``, its theme-dependent entries,
        and so does a non-empty ``point_style``, which a recreated GeoJSON view draws
        its points with. Both are keyed by whether the theme is dark.
        """
        theme_urls = getattr(layer, "theme_urls", None)
        if theme_urls:
            layer.url = theme_urls[is_dark]

        theme_style = getattr(layer, "theme_style", None)
        if theme_style:
            layer.style = {**layer.style, **theme_style[is_dark]}
            if getattr(layer, "point_style", None):
                layer.point_style = {**layer.point_style, **theme_style[is_dark]}

    def _is_dark(self) -> bool:
        """Whether the theme the map follows is dark."""
        return self._theme_is_dark(self._theme_source or v.theme)

    def _apply_theme_class(self, is_dark: bool) -> None:
        """Keep a theme marker class on the map root for theme-aware CSS hooks."""
        dark_class = "pysepal-map-theme-dark"
        light_class = "pysepal-map-theme-light"
        self.remove_class(light_class if is_dark else dark_class)
        self.add_class(dark_class if is_dark else light_class)

    def bind_theme_state(self, theme_state: Optional[ThemeState]) -> None:
        """Bind the map to a shared theme state."""
        self._bind_theme_source(theme_state if theme_state is not None else v.theme)

    def _unbind_theme_source(self) -> None:
        """Stop following the current theme source, if any.

        traitlets keeps ``_on_theme_change``, and a bound method holds the map.
        A source outliving the map -- ``v.theme`` is process-global -- would
        otherwise keep it, its layers and its Earth Engine objects reachable.
        """
        previous = self._theme_source
        self._theme_source = None
        if previous is None:
            return
        try:
            previous.unobserve(self._on_theme_change, "dark")
        except (AttributeError, KeyError, ValueError):
            pass

    def close(self) -> None:
        """Close the map with every widget it built.

        Its controls hold the map, and the kernel holds every widget left open,
        so a control left open keeps the whole map alive. Layers and controls
        added by the caller stay open. The layers drawn from ``layer_store`` are
        closed, and the store keeps its layers.
        """
        self._unbind_theme_source()
        # closed first so that releasing the controls sends nothing to the frontend
        super().close()
        # before the basemaps: taking a layer off reads the id of every layer on the map
        if self.layer_engine is not None:
            self.layer_engine.close()
        owned, self._owned = self._owned, []
        close_tree(*owned)
        close_tree(*self._owned_parts)

    def _close_owned(self, widget) -> None:
        """Close a widget this map built and no longer uses."""
        if any(widget is item for item in self._owned):
            self._owned = [item for item in self._owned if item is not widget]
            close_tree(widget)

    def _bind_theme_source(self, source) -> None:
        """Bind the map to the resolved source used to drive dark/light changes."""
        if source is self._theme_source:
            return

        previous = self._theme_source
        self._unbind_theme_source()

        source.observe(self._on_theme_change, "dark")
        self._theme_source = source

        is_dark = self._theme_is_dark(source)
        if previous is None:
            # Initial bind: basemaps already reflect the theme; only sync the CSS marker.
            self._apply_theme_class(is_dark)
        else:
            self._on_theme_change({"new": is_dark})

    @staticmethod
    def _theme_is_dark(source) -> bool:
        """Normalize theme sources that expose a `dark` traitlet."""
        return getattr(source, "dark", None) is True

    def show_dc(self) -> Self:
        """Show the drawing control on the map.

        Returns:
            Self for method chaining
        """
        self.dc.show()
        return self

    def hide_dc(self) -> Self:
        """Hide the drawing control of the map.

        Returns:
            Self for method chaining
        """
        self.dc.hide()
        return self

    def set_center(self, lon: float, lat: float, zoom: int = -1) -> None:
        """Centers the map view at a given coordinates with the given zoom level.

        Args:
            lon: The longitude of the center, in degrees.
            lat: The latitude of the center, in degrees.
            zoom: The zoom level, from 1 to 24. Defaults to None.
        """
        self.center = [lat, lon]
        self.zoom = self.zoom if zoom == -1 else zoom

        return

    @sd.need_ee
    def zoom_ee_object(self, item: ee.ComputedObject, zoom_out: int = 1) -> Self:
        """Get the proper zoom to the given ee geometry.

        Args:
            item: the geometry to zoom on
            zoom_out: Zoom out the bounding zoom
        """
        bounds = self.gee_interface.get_bounds(item)

        # zoom on these bounds
        return self.zoom_bounds(bounds, zoom_out)

    def zoom_raster(self, layer: ipl.LocalTileLayer, zoom_out: int = 1) -> Self:
        """Adapt the zoom to the given LocalLayer.

        The localLayer need to come from the add_raster method to embed the image name.

        Args:
            layer: the localTile layer to zoom on. it needs to embed the "raster" member
            zoom_out: Zoom out the bounding zoom
        """
        import rioxarray
        from rasterio.crs import CRS

        da = rioxarray.open_rasterio(layer.raster, masked=True)

        # unproject if necessary
        epsg_4326 = "EPSG:4326"
        if da.rio.crs != CRS.from_string(epsg_4326):
            da = da.rio.reproject(epsg_4326)

        return self.zoom_bounds(da.rio.bounds(), zoom_out)

    def zoom_bounds(self, bounds: Sequence[float], zoom_out: int = 1) -> Self:
        """Adapt the zoom to the given bounds. and center the image.

        Args:
            bounds: coordinates corners as minx, miny, maxx, maxy in EPSG:4326
            zoom_out: Zoom out the bounding zoom
        """
        # center the map
        minx, miny, maxx, maxy = bounds
        self.fit_bounds([[miny, minx], [maxy, maxx]])

        # adapt the zoom level
        zoom_out = (self.zoom - 1) if zoom_out > self.zoom else zoom_out

        self.zoom -= zoom_out

        return self

    def add_raster(
        self,
        image: Union[str, Path],
        bands: Optional[Union[list, int]] = None,
        layer_name: str = _DEFAULT_RASTER_NAME,
        colormap: Union[str, "mpc.Colormap"] = "inferno",
        opacity: float = 1.0,
        fit_bounds: bool = True,
        key: str = "",
        class_colors: Optional[dict] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        nodata: Optional[float] = None,
        optimize: bool = True,
        warp_to_3857: bool = False,
    ) -> ipl.TileLayer:
        """Adds a local raster dataset to the map.

        The raster is served by a ``localtileserver`` instance bound to ``127.0.0.1`` inside the kernel, so the browser cannot reach it without help. ``LOCALTILESERVER_CLIENT_PREFIX`` names the route that reaches it: SEPAL sets it for its sandboxes, and under solara-server you mount one yourself. Set, it wins and is used as given. **Unset**, localtileserver autodetects a ``jupyter-server-proxy`` prefix and assumes something serves it -- true in JupyterLab, false under a plain ``voila notebook.ipynb``, where every tile then 404s. **Define it empty** in that case to fall back to the loopback URL. See ``docs/guides/local-tile-servers.md``.

        The layer goes into :attr:`layer_store`, with ``key`` as its id.

        Args:
            image: The image file path.
            bands: The image bands to use. It can be either a number (e.g., 1) or a list (e.g., [3, 2, 1]). Defaults to None.
            layer_name: The layer name to use for the raster. Without one, the layer is named ``Layer N`` after the first number no other layer uses, so it never replaces another layer.
            colormap: The name of the colormap to use for the raster, such as 'gray' and 'terrain'. More can be found at https://matplotlib.org/3.1.0/tutorials/colors/colormaps.html. Defaults to inferno.
            opacity: the opacity of the layer, default 1.0.
            key: the unequivocal key of the layer, its id in :attr:`layer_store`. By default a normalized str of the layer name. A layer already using this key is replaced in place, keeping its position, visibility and opacity.
            fit_bounds: Whether or not we should fit the map to the image bounds. Default to True.
            class_colors: mapping of class code to ``'#rgb'`` or ``'#rrggbb'``, for a categorical raster. When set, each class is drawn in its exact color and anything absent is transparent, instead of stretching ``colormap`` across the value range. Code 0 is colored like any other; codes outside ``0-255`` are served from a renumbered copy, since a tile palette only holds 256 entries. Up to 255 classes.
            vmin: value mapped to the first color. Defaults to the file's own minimum, i.e. an auto-stretch. Pin both ends to reproduce a fixed palette (a QGIS ramp, a shared legend) rather than one that shifts per file. Ignored when ``class_colors`` is set.
            vmax: value mapped to the last color. See ``vmin``.
            nodata: value to render transparent. Defaults to the file's declared nodata, which some products tag incorrectly.
            optimize: prepare a tiled COG with overviews before serving. On by default because rio-tiler otherwise reads full-resolution pixels for every tile. Turn it off for a large raster you do not want copied into the tile cache, or one that already has ``.ovr`` sidecars.
            warp_to_3857: reproject to Web Mercator while preparing, so tiles are cut in the CRS they are served in instead of being warped per request. Needs ``optimize=True``. Off by default because it doubles the preparation work for a raster that is already close to 3857.

        Returns:
            the local tile layer embedding the raster member (to be used with other tools of sepal-ui)

        Raises:
            LayerPrepareError: when the raster cannot be prepared for display.

        Note:
            The first add of a large raster rewrites every one of its pixels and
            blocks until it finishes. In a Solara app use :meth:`add_raster_async`
            instead, which does that part in a worker thread.
        """
        spec = self._raster_spec(
            image, bands, layer_name, colormap, key, class_colors, vmin, vmax, nodata
        )
        render = prepare_sync(spec, optimize=optimize, warp_to_3857=warp_to_3857)
        return self._commit(spec, render, opacity=opacity, fit=fit_bounds)

    async def add_raster_async(
        self,
        image: Union[str, Path],
        bands: Optional[Union[list, int]] = None,
        layer_name: str = _DEFAULT_RASTER_NAME,
        colormap: Union[str, "mpc.Colormap"] = "inferno",
        opacity: float = 1.0,
        fit_bounds: bool = True,
        key: str = "",
        class_colors: Optional[dict] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        nodata: Optional[float] = None,
        optimize: bool = True,
        warp_to_3857: bool = False,
    ) -> Optional[ipl.TileLayer]:
        """Add a local raster without blocking the event loop.

        Same arguments as :meth:`add_raster`. Preparing a raster rewrites every
        one of its pixels into a tiled COG; that runs in a worker thread here,
        leaving only the layer attach on the loop.

        Returns:
            the local tile layer, or None when a newer action on the same key (a remove,
            a restyle or another add) superseded this call while it was preparing.

        Raises:
            LayerPrepareError: when the raster cannot be prepared for display.
        """
        spec = self._raster_spec(
            image, bands, layer_name, colormap, key, class_colors, vmin, vmax, nodata
        )
        return await self._commit_async(
            spec, opacity=opacity, fit=fit_bounds, optimize=optimize, warp_to_3857=warp_to_3857
        )

    def _raster_spec(
        self,
        image: Union[str, Path],
        bands: Optional[Union[list, int]],
        layer_name: str,
        colormap: Union[str, "mpc.Colormap"],
        key: str,
        class_colors: Optional[dict],
        vmin: Optional[float],
        vmax: Optional[float],
        nodata: Optional[float],
    ) -> LayerSpec:
        """Build the spec of an :meth:`add_raster` call."""
        if layer_name is _DEFAULT_RASTER_NAME:
            layer_name = self._default_name(key)
        return LayerSpec.from_raster(
            image,
            name=layer_name,
            id=key or su.normalize_str(layer_name),
            bands=bands,
            colormap=colormap,
            class_colors=class_colors,
            vmin=vmin,
            vmax=vmax,
            nodata=nodata,
        )

    def _commit(
        self,
        spec: LayerSpec,
        render: RenderLayer,
        *,
        shown: bool = True,
        opacity: float = 1.0,
        overlay: bool = False,
        fit: bool = False,
        generation: Optional[int] = None,
    ) -> Optional[ipl.Layer]:
        """Draw a prepared spec and return its leaflet layer.

        A managed layer goes through :attr:`layer_store`, replacing a layer with the same
        id in place; an overlay is added raw, above the managed layers.

        Args:
            spec: the layer spec.
            render: the render prepared from ``spec``.
            shown: whether a new layer is visible.
            opacity: the opacity of a new layer.
            overlay: add an unmanaged Earth Engine layer in the overlay pane instead.
            fit: fit the map to the layer bounds, when the render knows them.
            generation: the token of the reservation made before preparing; the add is
                dropped, and None returned, when a newer write to the id happened since.
        """
        if overlay:
            layer = EELayer(
                ee_object=render.ee_object,
                url=render.url,
                theme_urls=render.theme_urls,
                attribution=spec.attribution,
                name=spec.name,
                opacity=opacity,
                visible=shown,
                max_zoom=render.max_zoom,
                pane=OVERLAY_PANE,
            )
            self.add_layer(layer, key=spec.id)
        else:
            store = self.layer_store
            if generation is not None and store.generation(spec.id) != generation:
                return None
            self.layer_engine.put(render)
            added = store.add(
                spec,
                visible=shown,
                opacity=opacity,
                replace=True,
                expect_generation=generation,
            )
            if added is None:
                return None
            layer = self.layer_engine.leaflet_layer(spec.id)

        if fit and render.bounds is not None:
            self.zoom_bounds(render.bounds)

        return layer

    async def _commit_async(
        self,
        spec: LayerSpec,
        *,
        shown: bool = True,
        opacity: float = 1.0,
        overlay: bool = False,
        fit: bool = False,
        **options,
    ) -> Optional[ipl.Layer]:
        """Prepare a spec without blocking the loop, then :meth:`_commit` it.

        The id stays reserved while preparing, so that any newer write to it (from the
        panel, a sync add, another async one, a removal) wins over this call.

        Args:
            spec: the layer spec.
            shown: whether a new layer is visible.
            opacity: the opacity of a new layer.
            overlay: add an unmanaged Earth Engine layer in the overlay pane instead.
            fit: fit the map to the layer bounds, when the render knows them.
            options: the keyword arguments of :func:`~pysepal.layers.prepare`.
        """
        if overlay:
            render = await prepare(spec, **options)
            return self._commit(spec, render, shown=shown, opacity=opacity, overlay=True)

        generation = self.layer_store.reserve(spec.id, spec.name)
        try:
            render = await prepare(spec, **options)
            return self._commit(
                spec, render, shown=shown, opacity=opacity, fit=fit, generation=generation
            )
        finally:
            self.layer_store.release(spec.id, generation)

    def add_colorbar(
        self,
        colors: list,
        cmap: str = "viridis",
        vmin: float = 0.0,
        vmax: float = 1.0,
        index: list = [],
        categorical: bool = False,
        step: int = 0,
        transparent_bg: bool = False,
        position: str = "bottomright",
        layer_name: str = "",
        **kwargs,
    ) -> None:
        """Add a colorbar to the map.

        Args:
            colors: The set of colors to be used for interpolation. Colors can be provided in the form: * tuples of RGBA ints between 0 and 255 (e.g: (255, 255, 0) or (255, 255, 0, 255)) * tuples of RGBA floats between 0. and 1. (e.g: (1.,1.,0.) or (1., 1., 0., 1.)) * HTML-like string (e.g: “#ffff00) * a color name or shortcut (e.g: “y” or “yellow”)
            cmap: a matplotlib colormap default to viridis
            vmin: The minimal value for the colormap. Values lower than vmin will be bound directly to colors[0].. Defaults to 0.
            vmax: The maximal value for the colormap. Values higher than vmax will be bound directly to colors[-1]. Defaults to 1.0.
            index: The values corresponding to each color. It has to be sorted, and have the same length as colors. If None, a regular grid between vmin and vmax is created. Defaults to None.
            categorical (bool, optional): Whether or not to create a categorical colormap. Defaults to False.
            step: The step to split the LinearColormap into a StepColormap. Defaults to None.
            position: The position for the colormap widget. Defaults to "bottomright".
            layer_name: Layer name of the colorbar to be associated with. Defaults to None.
            kwargs: any other argument of the colorbar object from matplotlib
        """
        import matplotlib.pyplot as plt
        from matplotlib import colorbar
        from matplotlib import colors as mpc

        width, height = 6.0, 0.4
        alpha = 1

        if colors is not None:
            # transform colors in hex colors
            hexcodes = [su.to_colors(c) for c in colors]

            if categorical:
                plot_color = mpc.ListedColormap(hexcodes)
                vals = np.linspace(vmin, vmax, plot_color.N + 1)
                norm = mpc.BoundaryNorm(vals, plot_color.N)

            else:
                plot_color = mpc.LinearSegmentedColormap.from_list("custom", hexcodes, N=256)
                norm = mpc.Normalize(vmin=vmin, vmax=vmax)

        elif cmap is not None:
            plot_color = plt.get_cmap(cmap)
            norm = mpc.Normalize(vmin=vmin, vmax=vmax)

        else:
            msg = '"cmap" keyword or "colors" key must be provided.'
            raise ValueError(msg)

        style = (
            "dark_background" if self._theme_is_dark(self._theme_source or v.theme) else "classic"
        )

        with plt.style.context(style):
            fig, ax = plt.subplots(figsize=(width, height))
            cb = colorbar.ColorbarBase(
                ax,
                norm=norm,
                alpha=alpha,
                cmap=plot_color,
                orientation="horizontal",
                **kwargs,
            )

            # cosmetic improvement
            cb.outline.set_visible(False)  # remove border of the color bar
            ax.tick_params(size=0)  # remove ticks
            fig.patch.set_alpha(0.0)  # remove bg of the fig
            ax.patch.set_alpha(0.0)  # remove bg of the ax

        not layer_name or cb.set_label(layer_name)

        output = widgets.Output()
        colormap_ctrl = ipl.WidgetControl(
            widget=output,
            position=position,
            transparent_bg=True,
        )
        with output:
            output.clear_output()
            plt.show()

        self._owned.append(colormap_ctrl)
        self.add(colormap_ctrl)

        return

    def add_ee_layer(
        self,
        ee_object: ee.ComputedObject,
        vis_params: dict = {},
        name: str = "",
        shown: bool = True,
        opacity: float = 1.0,
        viz_name: str = "",
        key: str = "",
        use_map_vis: bool = True,
        autocenter: bool = False,
        overlay: bool = False,
    ) -> None:
        """Customized add_layer method designed for EE objects.

        Copy the addLayer method from geemap to read and guess the vizaulization
        parameters the same way as in SEPAL recipes.
        If the vizparams are empty and visualization metadata exist, SepalMap will use
        them automatically. The layer goes into :attr:`layer_store`, with ``key`` as its id.

        Args:
            ee_object: the ee OBject to draw on the map
            vis_params: the visualization parameters set as in GEE. A vector given no ``color`` is drawn in the primary colour of the map theme, and follows it when the theme changes.
            name: the name of the layer
            shown: either to show the layer or not, default to true
            opacity: the opcity of the layer from 0 to 1, default to 1.
            viz_name: the name of the vizaulization you want to use. default to the first one if existing
            key: the unequivocal key of the layer, its id in :attr:`layer_store`. By default a normalized str of the layer name. A layer already using this key is replaced in place, keeping its position, visibility and opacity.
            use_map_vis: whether or not to use the map visualization parameters. default to True
            autocenter: whether or not to center the map on the layer. default to False
            overlay: draw the layer above every layer of :attr:`layer_store`, outside it, so that no layer panel lists it. For a reference layer such as the AOI. Default to False.

        Raises:
            LayerPrepareError: when Earth Engine cannot render the layer.
        """
        spec = self._ee_spec(ee_object, vis_params, name, key, viz_name, use_map_vis)
        render = prepare_sync(spec, gee_interface=self.gee_interface)
        layer = self._commit(spec, render, shown=shown, opacity=opacity, overlay=overlay)
        if autocenter and layer is not None:
            with _unless_unbounded():
                self.zoom_bounds(self.gee_interface.get_bounds(ee_object))

    async def add_ee_layer_async(
        self,
        ee_object: ee.ComputedObject,
        vis_params: dict = {},
        name: str = "",
        shown: bool = True,
        opacity: float = 1.0,
        viz_name: str = "",
        key: str = "",
        use_map_vis: bool = True,
        autocenter: bool = False,
        attribution: str = "Google Earth Engine",
        overlay: bool = False,
    ) -> None:
        """Customized add_layer method designed for EE objects.

        Copy the addLayer method from geemap to read and guess the vizaulization
        parameters the same way as in SEPAL recipes.
        If the vizparams are empty and visualization metadata exist, SepalMap will use
        them automatically. The layer goes into :attr:`layer_store`, with ``key`` as its
        id, unless a newer action on the same key happens while Earth Engine renders it.

        Args:
            ee_object: the ee OBject to draw on the map
            vis_params: the visualization parameters set as in GEE. A vector given no ``color`` is drawn in the primary colour of the map theme, and follows it when the theme changes.
            name: the name of the layer
            shown: either to show the layer or not, default to true
            opacity: the opcity of the layer from 0 to 1, default to 1.
            viz_name: the name of the vizaulization you want to use. default to the first one if existing
            key: the unequivocal key of the layer, its id in :attr:`layer_store`. By default a normalized str of the layer name. A layer already using this key is replaced in place, keeping its position, visibility and opacity.
            use_map_vis: whether or not to use the map visualization parameters. default to True
            autocenter: whether or not to center the map on the layer. default to False
            attribution: the attribution shown in the map corner while the layer is visible
            overlay: draw the layer above every layer of :attr:`layer_store`, outside it, so that no layer panel lists it. For a reference layer such as the AOI. Default to False.

        Raises:
            LayerPrepareError: when Earth Engine cannot render the layer.
        """
        spec = self._ee_spec(ee_object, vis_params, name, key, viz_name, use_map_vis, attribution)
        layer = await self._commit_async(
            spec,
            shown=shown,
            opacity=opacity,
            overlay=overlay,
            gee_interface=self.gee_interface,
        )
        if autocenter and layer is not None:
            with _unless_unbounded():
                self.zoom_bounds(await self.gee_interface.get_bounds_async(ee_object))

    def _default_name(self, key: str) -> str:
        """Name a layer added without a name.

        A key already in the store keeps the name of its layer. Otherwise the name is
        ``Layer N``, N counting the layers on the map, raised until neither the name nor
        the id it gives is used by a layer on the map, in the store or reserved.
        """
        store = self.layer_store
        if key and key in store:
            return store.get(key).name
        taken = {getattr(lyr, "key", None) for lyr in self.layers}
        taken |= {lyr.name for lyr in self.layers}
        taken |= {name for spec in store.specs() for name in (spec.id, spec.name)}
        taken |= {name for item in store.reserved().items() for name in item}
        n = len(self.layers) + 1
        while f"Layer {n}" in taken or su.normalize_str(f"Layer {n}") in taken:
            n += 1
        return f"Layer {n}"

    def _ee_spec(
        self,
        ee_object: ee.ComputedObject,
        vis_params: dict,
        name: str,
        key: str,
        viz_name: str,
        use_map_vis: bool,
        attribution: str = "Google Earth Engine",
    ) -> LayerSpec:
        """Build the spec of an :meth:`add_ee_layer` call."""
        _check_ee_inputs(ee_object, vis_params)
        name = name or self._default_name(key)
        return LayerSpec.from_ee(
            ee_object,
            vis_params,
            name=name,
            id=key or su.normalize_str(name),
            viz_name=viz_name,
            use_asset_viz=use_map_vis,
            attribution=attribution,
        )

    @staticmethod
    def get_basemap_list() -> List[str]:
        """Get the complete list of available basemaps.

        This function is intending for development use
        It give the list of all the available basemaps for SepalMap object.

        Returns:
            The list of the basemap names
        """
        return [k for k in basemap_tiles.keys()]

    def remove_layer(
        self, key: Union[ipl.Layer, int, str], base: bool = False, none_ok: bool = False
    ) -> None:
        """Remove a layer based on a key.

        The key can be, a Layer object, the key or the name of a layer or the index in the layer list. A layer of :attr:`layer_store` is removed from the store, even while hidden; a key an async add is still preparing cancels that add.

        Args:
            key: the key to find the layer to delete
            base: either the basemaps should be included in the search or not. default t false
            none_ok: if True the function will not raise error if no layer is found. Default to False
        """
        if isinstance(key, str):
            layer, layer_id = self._lookup(key, self._candidates(base))
        else:
            layer = self.find_layer(key, base, none_ok=True)
            layer_id = None if layer is None else self._managed_id(layer)

        if layer_id is not None:
            self.layer_store.remove(layer_id, missing_ok=True)
        elif layer is not None:
            super().remove(layer)
        elif not none_ok:
            raise ValueError(f"no layer corresponding to {key} on the map")

    def remove_all(self, base: bool = False, keep_names: Optional[list[str]] = None) -> None:
        """Remove all the layers from the maps.

        If base is set to True, the basemaps are removed as well. The layers of :attr:`layer_store` are removed from it, hidden ones and pending async adds included.

        Args:
            base: whether or not the basemaps should be removed, default to False
            keep_names: if set, will keep the layers with these names
        """
        keep = set(keep_names or [])
        store = self.layer_store
        for spec in store.specs():
            if spec.name not in keep:
                store.remove(spec.id)
        for layer_id, name in store.reserved().items():
            # a kept layer's pending replacement is left to land
            if name not in keep and layer_id not in store:
                store.remove(layer_id, missing_ok=True)

        for layer in self._candidates(base):
            if layer.name not in keep:
                self.remove_layer(layer, base)

    def add_layer(self, layer: ipl.Layer, hover: bool = False, key: str = "") -> None:
        """Add layer and use a default style for the GeoJSON inputs.

        Remove existing layer if already on the map. The layer is not managed: it stays out of :attr:`layer_store`, so no layer panel lists it. A tile layer without a pane is drawn in the overlay pane, above the layers of the store.

        Args:
            layer: any layer type from ipyleaflet
            hover: whether to use the default hover style or not.
            key: the unequivocal key of the layer. by default the key already set on the layer, else a normalized str of the layer name
        """
        layer.key = key or getattr(layer, "key", None) or su.normalize_str(layer.name)

        # remove the layer using the same key, or a raw one using it as name, as before the store
        existing_layer = self.find_layer(layer.key, none_ok=True)
        if existing_layer is not None and (
            getattr(existing_layer, "key", None) == layer.key
            or self._managed_id(existing_layer) is None
        ):
            self.remove_layer(existing_layer)

        if isinstance(layer, ipl.TileLayer) and not layer.base and not layer.pane:
            layer.pane = OVERLAY_PANE

        # apply default coloring for geoJson
        if isinstance(layer, ipl.GeoJSON):
            # define the default values
            default_style = json.loads((ss.JSON_DIR / "layer.json").read_text())["layer"]
            default_style.update(color=scolors.primary)
            default_hover_style = json.loads((ss.JSON_DIR / "layer_hover.json").read_text())
            default_hover_style.update(color=scolors.primary)

            # apply the style depending on the parameters
            layer.style = layer.style or default_style
            hover_style = default_hover_style if hover else layer.hover_style
            layer.hover_style = layer.hover_style or hover_style

        self._apply_layer_theme(layer, self._is_dark())

        super().add(layer)

        return

    def add_basemap(self, basemap: str = "HYBRID") -> None:
        """Adds a basemap to the map.

        Args:
            basemap: Can be one of string from basemaps. Defaults to 'HYBRID'.
        """
        if basemap not in basemap_tiles.keys():
            keys = "\n".join(basemap_tiles.keys())
            msg = f"Basemap can only be one of the following:\n{keys}"
            raise ValueError(msg)

        layer = eval(str(basemap_tiles[basemap]))
        self._owned.append(layer)
        self.add_layer(layer)

        return

    def get_scale(self) -> float:
        """Returns the approximate pixel scale of the current map view, in meters.

        Reference: https://blogs.bing.com/maps/2006/02/25/map-control-zoom-levels-gt-resolution.

        Returns:
            Map resolution in meters.
        """
        return 156543.04 * math.cos(0) / math.pow(2, self.zoom)

    def find_layer(
        self, key: Union[ipl.Layer, str, int], base: bool = False, none_ok: bool = False
    ) -> Optional[ipl.Layer]:
        """Search a layer by name or index.

        A string is looked up as a key first, then as a name. Hidden layers of :attr:`layer_store` are found too, by key, name or object; the index only counts the layers on the map.

        Args:
            key: the layer name, the layer key, the index or directly the layer
            base: either the basemaps should be included in the search or not. default to false
            none_ok: if True the function will not raise error if no layer is found. Default to False

        Returns:
            The first layer using the same name or index else None
        """
        layers = self._candidates(base)

        if isinstance(key, str):
            layer = self._lookup(key, layers)[0]
        elif isinstance(key, int):
            size = len(layers)
            layer = layers[key] if -size <= key < size else None
        elif isinstance(key, ipl.Layer):
            layer = key if key in layers or self._managed_id(key) is not None else None
        else:
            raise ValueError(f"key must be a int or a str, {type(key)} given")

        if layer is None and none_ok is False:
            raise ValueError(f"no layer corresponding to {key} on the map")

        return layer

    def _candidates(self, base: bool) -> list[ipl.Layer]:
        """The layers on the map, basemaps only when ``base``."""
        return list(self.layers) if base else [lyr for lyr in self.layers if not lyr.base]

    def _lookup(
        self, key: str, layers: Sequence[ipl.Layer]
    ) -> tuple[Optional[ipl.Layer], Optional[str]]:
        """Resolve a key, else a name, to a layer and, for a managed one, its store id.

        Each is looked up on the given ``layers`` of the map first, then in
        :attr:`layer_store` (top first), then among the ids an async add reserved. A
        managed match has no layer while it is still being prepared.

        Returns:
            The layer and the id, either one None when it does not apply.
        """
        store = self.layer_store
        reserved = store.reserved()

        layer = next((lyr for lyr in layers if getattr(lyr, "key", None) == key), None)
        if layer is not None:
            return layer, self._managed_id(layer)
        if key in store or key in reserved:
            return self._managed_layer(key), key

        layer = next((lyr for lyr in layers if lyr.name == key), None)
        if layer is not None:
            return layer, self._managed_id(layer)
        named = [spec.id for spec in store.specs() if spec.name == key]
        named += [layer_id for layer_id, name in reserved.items() if name == key]
        if named:
            return self._managed_layer(named[0]), named[0]

        return None, None

    def _managed_layer(self, layer_id: str) -> Optional[ipl.Layer]:
        """The leaflet layer built for a store id, attached or not."""
        return None if self.layer_engine is None else self.layer_engine.leaflet_layer(layer_id)

    def _managed_id(self, layer: ipl.Layer) -> Optional[str]:
        """The store id of a layer this map's engine built, else None."""
        layer_id = getattr(layer, "layer_id", None)
        if layer_id is None or self._managed_layer(layer_id) is not layer:
            return None
        return layer_id

    def fit_bounds(self, bounds):
        """Abstract method to fit the map to the given bounds."""
        # I've done this because the native ipyleaflet fit bounds method uses
        # awaitables that create conflicts with solara.
        # Also I don't like the way it zooms by levels

        # Canvas (width, height) in pixels. Prefer values pushed from the
        # frontend (accurate from render 0); fall back to bounds-derived
        # (accurate post-render); finally to defaults. The pushed path is
        # what fixes the "first fit_bounds is too far" cold-start bug —
        # before the first render self.bounds is the default world view.
        derived_w, derived_h = viewport_pixels_from_map(self)
        canvas_w = int(self.canvas_width_px) or derived_w or DEFAULT_MAP_WIDTH_PX
        canvas_h = int(self.canvas_height_px) or derived_h or (canvas_w * 9 / 16)

        # Subtract overlay panels (nav drawer, right panel) from the *width*
        # and the narrow-mode bottom panel from the *height* so fit_bounds
        # targets the truly visible region.
        left = max(int(self.viewport_inset_left), 0)
        right = max(int(self.viewport_inset_right), 0)
        bottom = max(int(self.viewport_inset_bottom), 0)
        visible_w = max(canvas_w - left - right, 1)
        visible_h = max(canvas_h - bottom, 1)

        log.debug(
            f"canvas=({canvas_w:.0f},{canvas_h:.0f}) "
            f"visible=({visible_w:.0f},{visible_h:.0f}) "
            f"insets=({left},{right},{bottom})"
        )

        zoom = (
            compute_zoom_for_bounds(
                bounds,
                map_width_px=visible_w,
                map_height_px=visible_h,
                min_zoom=getattr(self, "min_zoom", None),
                max_zoom=getattr(self, "max_zoom", None),
            )
            + 1
        )
        self.zoom = zoom

        # Shift the map center so the target's geographic center lands at the
        # *visible* center, not the canvas center.
        # X (longitude) is linear in Web Mercator pixels: 360° / (256 * 2**zoom).
        # Y (latitude) scale near lat_c is the X scale * cos(lat_c).
        lat_c, lon_c = compute_center(bounds)
        deg_per_px_x = 360.0 / (256 * (2**zoom))
        deg_per_px_y = deg_per_px_x * math.cos(math.radians(lat_c))

        px_offset_x = (left - right) / 2  # +ve when left panel dominates
        # bottom panel pushes the visible region upward → canvas center is
        # below visible center → map center must shift south (lower lat).
        px_offset_y = bottom / 2
        lon_shift = px_offset_x * deg_per_px_x
        lat_shift = px_offset_y * deg_per_px_y
        self.center = (lat_c - lat_shift, lon_c - lon_shift)

    def add_legend(
        self,
        title: Optional[str] = None,
        legend_dict: dict = {},
        position: str = "bottomright",
        vertical: bool = True,
    ) -> None:
        """Creates and adds a custom legend as widget control to the map.

        Args:
            title: Title of the legend. Defaults to 'Legend'.
            legend_dict: dictionary with key as label name and value as color
            position: the position (corners) of the legend on the map
            vertical: vertical or horizoal position of the legend
        """
        title = msg("mapping.legend") if title is None else title

        # Define as class member so it can be accessed from outside.
        self.legend = LegendControl(legend_dict, title=title, vertical=vertical, position=position)
        self._owned.append(self.legend)

        return self.add(self.legend)

        # ##########################################################################
        # ###                overwrite geemap calls                              ###
        # ##########################################################################

    setCenter = set_center
    centerObject = zoom_ee_object
    addLayer = add_ee_layer
    getScale = get_scale
