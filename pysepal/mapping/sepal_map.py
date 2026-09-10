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
from pysepal.mapping.raster_style import (
    _class_color_kwargs,
    _continuous_color_kwargs,
    _densify_class_codes,
    _needs_dense_codes,
)
from pysepal.mapping.tiling import _optimize_for_tiles, default_cache_dir
from pysepal.mapping.visualization import (
    get_viz_params,
    get_viz_params_async,
    process_vis_params,
)
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.sepalwidgets.vue_app import ThemeToggle
from pysepal.solara.theme import ThemeState

if any(var in os.environ for var in GDAL_ENV_VARS):
    prune_foreign_gdal_env()

import asyncio
import json
import math
import random
import string
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Sequence, Union

import ee
import ipyleaflet as ipl
import ipyvuetify as v
import ipywidgets as widgets
import numpy as np
from deprecated.sphinx import deprecated
from eeclient.client import EESession
from ipyleaflet import TileLayer  # noqa: F401 - leave it here, it is used in the eval
from traitlets import Int as _TInt
from typing_extensions import Self

from pysepal import color as scolors
from pysepal import sepalwidgets as sw
from pysepal.frontend import styles as ss
from pysepal.mapping.basemaps import basemap_tiles
from pysepal.mapping.draw_control import GeomanDrawControl
from pysepal.mapping.inspector_control import InspectorControl
from pysepal.mapping.layer import EELayer
from pysepal.mapping.layer_state_control import LayerStateControl
from pysepal.mapping.layers_control import LayersControl
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

CLIENT_PREFIX_ENV_VAR = "LOCALTILESERVER_CLIENT_PREFIX"


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

    state: Optional[sw.StateBar] = None
    "The statebar to inform the user about tile loading"

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
        theme_toggle: ThemeToggle = None,
        theme_state: Optional[ThemeState] = None,
        gee_session: Optional[EESession] = None,
        gee_interface: Optional[GEEInterface] = None,
        fullscreen: bool = False,
        map_id: str = "",
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
            theme_toggle: deprecated ThemeToggle source. Use theme_state instead.
            theme_state: shared theme state for Solara apps
            gee_session (optional): a custom EESession object to do gee requests. default to None (deprecated in favor of gee_interface)
            gee_interface: a shared GEEInterface instance. If provided, takes precedence over gee_session
            fullscreen: whether or not to display the map in full screen. default to False
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
        kwargs.setdefault("zoom", 2)
        kwargs.setdefault("max_zoom", 24)
        kwargs["basemap"] = {}
        kwargs["zoom_control"] = False
        kwargs["attribution_control"] = False
        kwargs["scroll_wheel_zoom"] = True
        kwargs.setdefault("world_copy_jump", True)

        if fullscreen:
            self.add_class("full-screen-map")

        super().__init__(**kwargs)
        self._theme_source = None

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

        # add the basemaps
        self.clear()
        theme_source = self._resolve_theme_source(theme_state, theme_toggle)
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
        self.add(ZoomControl(self))
        self.add(LayersControl(self, group=-1))
        self.add(ipl.AttributionControl(position="bottomleft", prefix="SEPAL"))
        self.add(ipl.ScaleControl(position="bottomleft", imperial=False))

        if kwargs.get("fullscreen_control", False):
            self.add(FullScreenControl(self))

        # specific drawing control
        self.dc = GeomanDrawControl(self)
        not dc or self.add(self.dc)

        # specific v_inspector
        self.v_inspector = InspectorControl(self)
        not vinspector or self.add(self.v_inspector)

        # specific statebar
        self.state = LayerStateControl(self)
        not statebar or self.add(self.state)

        # create a proxy ID to the element
        # this id should be unique and will be used by mutators to identify this map
        self._id = map_id or "".join(random.choice(string.ascii_lowercase) for i in range(6))
        self.add_class(self._id)
        self._bind_theme_source(theme_source)

    def _on_theme_change(self, change) -> None:
        """Change the basemap layer."""
        # This is the way to make it work in solara do not ask me why
        light = eval(str(basemap_tiles["SEPAL_LIGHT"]))
        dark = eval(str(basemap_tiles["SEPAL_DARK"]))

        layer_names = [layer.name for layer in self.layers]
        self._apply_theme_class(change["new"])

        if change["new"]:
            if light.name in layer_names:
                idx = layer_names.index(light.name)
                layer = self.layers[idx]
                self.remove_layer(layer, base=True, none_ok=True)
                self.layers = self.layers[:idx] + (dark,) + self.layers[idx:]
        else:
            if dark.name in layer_names:
                idx = layer_names.index(dark.name)
                layer = self.layers[idx]
                self.remove_layer(layer, base=True, none_ok=True)
                self.layers = self.layers[:idx] + (light,) + self.layers[idx:]

    def _apply_theme_class(self, is_dark: bool) -> None:
        """Keep a theme marker class on the map root for theme-aware CSS hooks."""
        dark_class = "pysepal-map-theme-dark"
        light_class = "pysepal-map-theme-light"
        self.remove_class(light_class if is_dark else dark_class)
        self.add_class(dark_class if is_dark else light_class)

    def bind_theme_state(self, theme_state: Optional[ThemeState]) -> None:
        """Bind the map to a shared theme state."""
        self._bind_theme_source(theme_state if theme_state is not None else v.theme)

    def _bind_theme_source(self, source) -> None:
        """Bind the map to the resolved source used to drive dark/light changes."""
        if source is self._theme_source:
            return

        previous = self._theme_source
        if previous is not None:
            try:
                previous.unobserve(self._on_theme_change, "dark")
            except (AttributeError, KeyError, ValueError):
                pass

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

    @staticmethod
    def _resolve_theme_source(
        theme_state: Optional[ThemeState], theme_toggle: Optional[ThemeToggle]
    ):
        """Resolve the theme source used to initialize and drive the map theme."""
        if theme_state is not None:
            return theme_state

        if theme_toggle is not None:
            return SepalMap._resolve_deprecated_theme_toggle_source(theme_toggle)

        return v.theme

    @staticmethod
    @deprecated(
        version="3.4.0",
        reason="SepalMap(theme_toggle=...) is deprecated; pass theme_state=... instead.",
        category=DeprecationWarning,
    )
    def _resolve_deprecated_theme_toggle_source(theme_toggle: ThemeToggle):
        """Resolve the legacy theme_toggle constructor path."""
        if hasattr(theme_toggle, "get_theme_state"):
            bound_theme_state = theme_toggle.get_theme_state()
            if bound_theme_state is not None:
                return bound_theme_state
        return theme_toggle

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
        layer_name: str = "Layer_" + su.random_string(),
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

        Args:
            image: The image file path.
            bands: The image bands to use. It can be either a number (e.g., 1) or a list (e.g., [3, 2, 1]). Defaults to None.
            layer_name: The layer name to use for the raster. Defaults to None. If a layer is already using this name 3 random letter will be added
            colormap: The name of the colormap to use for the raster, such as 'gray' and 'terrain'. More can be found at https://matplotlib.org/3.1.0/tutorials/colors/colormaps.html. Defaults to inferno.
            opacity: the opacity of the layer, default 1.0.
            key: the unequivocal key of the layer. by default use a normalized str of the layer name
            fit_bounds: Whether or not we should fit the map to the image bounds. Default to True.
            class_colors: mapping of class code to ``'#rgb'`` or ``'#rrggbb'``, for a categorical raster. When set, each class is drawn in its exact color and anything absent is transparent, instead of stretching ``colormap`` across the value range. Code 0 is colored like any other; codes outside ``0-255`` are served from a renumbered copy, since a tile palette only holds 256 entries. Up to 255 classes.
            vmin: value mapped to the first color. Defaults to the file's own minimum, i.e. an auto-stretch. Pin both ends to reproduce a fixed palette (a QGIS ramp, a shared legend) rather than one that shifts per file. Ignored when ``class_colors`` is set.
            vmax: value mapped to the last color. See ``vmin``.
            nodata: value to render transparent. Defaults to the file's declared nodata, which some products tag incorrectly.
            optimize: prepare a tiled COG with overviews before serving. On by default because rio-tiler otherwise reads full-resolution pixels for every tile. Turn it off for a large raster you do not want copied into the tile cache, or one that already has ``.ovr`` sidecars.
            warp_to_3857: reproject to Web Mercator while preparing, so tiles are cut in the CRS they are served in instead of being warped per request. Needs ``optimize=True``. Off by default because it doubles the preparation work for a raster that is already close to 3857.

        Returns:
            the local tile layer embedding the raster member (to be used with other tools of sepal-ui)

        Note:
            The first add of a large raster rewrites every one of its pixels and
            blocks until it finishes. In a Solara app use :meth:`add_raster_async`
            instead, which does that part in a worker thread.
        """
        served, class_colors = self._prepare_raster(image, class_colors, optimize, warp_to_3857)
        return self._attach_raster(
            image,
            served,
            bands=bands,
            layer_name=layer_name,
            colormap=colormap,
            opacity=opacity,
            fit_bounds=fit_bounds,
            key=key,
            class_colors=class_colors,
            vmin=vmin,
            vmax=vmax,
            nodata=nodata,
        )

    async def add_raster_async(
        self,
        image: Union[str, Path],
        bands: Optional[Union[list, int]] = None,
        layer_name: str = "Layer_" + su.random_string(),
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
        """Add a local raster without blocking the event loop.

        Same arguments and return as :meth:`add_raster`. Preparing a raster
        rewrites every one of its pixels into a tiled COG; that runs in a worker
        thread here, leaving only the layer attach on the loop.
        """
        served, class_colors = await asyncio.to_thread(
            self._prepare_raster, image, class_colors, optimize, warp_to_3857
        )
        return self._attach_raster(
            image,
            served,
            bands=bands,
            layer_name=layer_name,
            colormap=colormap,
            opacity=opacity,
            fit_bounds=fit_bounds,
            key=key,
            class_colors=class_colors,
            vmin=vmin,
            vmax=vmax,
            nodata=nodata,
        )

    def _prepare_raster(
        self,
        image: Union[str, Path],
        class_colors: Optional[dict],
        optimize: bool,
        warp_to_3857: bool = False,
    ) -> tuple:
        """Produce the serve-ready raster path, doing all of the expensive work.

        Touches only the filesystem, so it is safe to run off the UI thread --
        which is what :meth:`add_raster_async` does. Returns the path to serve
        and the ``class_colors`` restated in whatever codes that path uses.
        """
        image = Path(image)

        if not image.is_file():
            raise Exception(msg("mapping.no_image"))

        source = image
        if class_colors and _needs_dense_codes(class_colors):
            cache_dir = default_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)
            source, class_colors = _densify_class_codes(image, class_colors, cache_dir)

        if warp_to_3857 and not optimize:
            # reprojecting means writing a new raster, which is the very thing
            # optimize=False asks us not to do
            log.warning("warp_to_3857 needs optimize=True; %s is served in its own CRS.", image)

        # rio-tiler reads full-resolution pixels for every tile when the source
        # has no overviews, so serve a prepared COG. Fast no-op when the raster
        # is already tiled with overviews. class_colors settles the overview
        # resampling either way -- without it the raster is being drawn as a ramp,
        # so averaged overviews are right even for the integer dtypes
        # prepare_for_tiles would otherwise guess were classes (an int16 DEM).
        served = (
            _optimize_for_tiles(
                source,
                categorical=bool(class_colors),
                warp_to_3857=warp_to_3857,
            )
            if optimize
            else str(source)
        )
        return served, class_colors

    def _attach_raster(
        self,
        image: Union[str, Path],
        served: str,
        bands: Optional[Union[list, int]] = None,
        layer_name: str = "",
        colormap: Union[str, "mpc.Colormap"] = "inferno",
        opacity: float = 1.0,
        fit_bounds: bool = True,
        key: str = "",
        class_colors: Optional[dict] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
        nodata: Optional[float] = None,
    ) -> ipl.TileLayer:
        """Serve a prepared raster and put it on the map.

        The half of ``add_raster`` that mutates the map, so it belongs on the
        thread that owns the widgets.
        """
        from localtileserver import TileClient, get_leaflet_tile_layer

        image = Path(image)
        # Pass the variable through rather than letting localtileserver read it:
        # unset gives None and it autodetects a jupyter-server-proxy prefix, which
        # Voila does not serve. Defined-but-empty reaches TileClient as "", the one
        # value that suppresses both the env read and the autodetect.
        client = TileClient(served, client_prefix=os.environ.get(CLIENT_PREFIX_ENV_VAR))

        # check inputs
        if layer_name in [layer.name for layer in self.layers]:
            layer_name = layer_name + su.random_string()

        color_kwargs = _class_color_kwargs(class_colors) if class_colors else None
        if class_colors and color_kwargs is None:
            log.warning(
                "localtileserver register_colormap unavailable; %s falls back to "
                "the continuous colormap and its classes may render dark.",
                image,
            )
        if color_kwargs is None:
            color_kwargs = _continuous_color_kwargs(image, bands, colormap)
            color_kwargs |= {"vmin": vmin, "vmax": vmax}
        elif vmin is not None or vmax is not None:
            # the categorical path pins its own range; a caller's would rescale
            # the class codes into ramp positions and blank the raster
            log.warning("vmin/vmax are ignored when class_colors is set.")

        # create the layer
        layer = get_leaflet_tile_layer(
            client,
            name=layer_name,
            opacity=opacity,
            max_zoom=20,
            max_native_zoom=20,
            nodata=nodata,
            **color_kwargs,
        )
        self.add_layer(layer, key=key)

        # add the da to the layer as an extra member for the v_inspector
        layer.raster = str(image)

        # zoom on the layer if requested. Not client.default_zoom: that frames the
        # raster in a single 256px tile, leaving it about an eighth of the
        # viewport wide. zoom_bounds is what add_ee_layer autocenters with -- it
        # sizes to the canvas, allows for whatever panels MapApp has laid over it,
        # and stops at the tightest zoom that still shows the whole raster.
        if fit_bounds is True:
            (south, west), (north, east) = layer.bounds
            self.zoom_bounds((west, south, east, north))

        return layer

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
    ) -> None:
        """Customized add_layer method designed for EE objects.

        Copy the addLayer method from geemap to read and guess the vizaulization
        parameters the same way as in SEPAL recipes.
        If the vizparams are empty and visualization metadata exist, SepalMap will use
        them automatically.

        Args:
            ee_object: the ee OBject to draw on the map
            vis_params: the visualization parameters set as in GEE
            name: the name of the layer
            shown: either to show the layer or not, default to true (it is bugged in ipyleaflet)
            opacity: the opcity of the layer from 0 to 1, default to 1.
            viz_name: the name of the vizaulization you want to use. default to the first one if existing
            key: the unequivocal key of the layer. by default use a normalized str of the layer name
            use_map_vis: whether or not to use the map visualization parameters. default to True
            autocenter: whether or not to center the map on the layer. default to False
        """
        # get the own visualization parameters
        map_own_visualization = get_viz_params(ee_object, gee_interface=self.gee_interface)

        image, obj, vis_params = process_vis_params(
            ee_object,
            vis_params=vis_params,
            viz=map_own_visualization,
            use_map_vis=use_map_vis,
            viz_name=viz_name,
        )

        # create the layer based on these new values
        if not name:
            layer_count = len(self.layers)
            name = "Layer " + str(layer_count + 1)

        # create the colored image
        map_id_dict = self.gee_interface.get_map_id(image, vis_params)
        tile_layer = EELayer(
            ee_object=obj,
            url=map_id_dict["tile_fetcher"].url_format,
            attribution="Google Earth Engine",
            name=name,
            opacity=opacity,
            visible=shown,
            max_zoom=24,
        )

        if autocenter:
            try:
                self.zoom_bounds(self.gee_interface.get_bounds(ee_object))
            except Exception:
                log.debug("autocenter skipped: unable to compute bounds (unbounded image?)")

        self.add_layer(tile_layer, key=key)

        return

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
    ) -> None:
        """Customized add_layer method designed for EE objects.

        Copy the addLayer method from geemap to read and guess the vizaulization
        parameters the same way as in SEPAL recipes.
        If the vizparams are empty and visualization metadata exist, SepalMap will use
        them automatically.

        Args:
            ee_object: the ee OBject to draw on the map
            vis_params: the visualization parameters set as in GEE
            name: the name of the layer
            shown: either to show the layer or not, default to true (it is bugged in ipyleaflet)
            opacity: the opcity of the layer from 0 to 1, default to 1.
            viz_name: the name of the vizaulization you want to use. default to the first one if existing
            key: the unequivocal key of the layer. by default use a normalized str of the layer name
            use_map_vis: whether or not to use the map visualization parameters. default to True
            autocenter: whether or not to center the map on the layer. default to False
        """
        # get the own visualization parameters
        map_own_visualization = await get_viz_params_async(
            ee_object,
            gee_interface=self.gee_interface,
        )

        image, obj, vis_params = process_vis_params(
            ee_object,
            vis_params=vis_params,
            viz=map_own_visualization,
            use_map_vis=use_map_vis,
            viz_name=viz_name,
        )

        # create the layer based on these new values
        if not name:
            layer_count = len(self.layers)
            name = "Layer " + str(layer_count + 1)

        # create the colored image
        map_id_dict = await self.gee_interface.get_map_id_async(image, vis_params)
        tile_layer = EELayer(
            ee_object=obj,
            url=map_id_dict["tile_fetcher"].url_format,
            attribution="Google Earth Engine",
            name=name,
            opacity=opacity,
            visible=shown,
            max_zoom=24,
        )

        if autocenter:
            try:
                self.zoom_bounds(await self.gee_interface.get_bounds_async(ee_object))
            except Exception:
                log.debug("autocenter skipped: unable to compute bounds (unbounded image?)")

        self.add_layer(tile_layer, key=key)

        return

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

        The key can be, a Layer object, the name of a layer or the index in the layer list.

        Args:
            key: the key to find the layer to delete
            base: either the basemaps should be included in the search or not. default t false
            none_ok: if True the function will not raise error if no layer is found. Default to False
        """
        layer = self.find_layer(key, base, none_ok)

        # the error is caught in find_layer
        if layer is not None:
            super().remove(layer)

        return

    def remove_all(self, base: bool = False, keep_names: Optional[list[str]] = None) -> None:
        """Remove all the layers from the maps.

        If base is set to True, the basemaps are removed as well.

        Args:
            base: whether or not the basemaps should be removed, default to False
            keep_names: if set, will keep the layers with these names
        """
        # filter out the basemaps if base == False
        layers = self.layers if base else [lyr for lyr in self.layers if not lyr.base]

        # remove them using the layer objects as keys
        [
            self.remove_layer(layer, base)
            for layer in layers
            if not keep_names or layer.name not in keep_names
        ]

        return

    def add_layer(self, layer: ipl.Layer, hover: bool = False, key: str = "") -> None:
        """Add layer and use a default style for the GeoJSON inputs.

        Remove existing layer if already on the map.

        Args:
            layer: any layer type from ipyleaflet
            hover: whether to use the default hover style or not.
            key: the unequivocal key of the layer. by default use a normalized str of the layer name
        """
        # set up a unique key
        layer.key = key if key else su.normalize_str(layer.name)

        # remove existing layer before addition
        existing_layer = self.find_layer(layer.key, none_ok=True)
        not existing_layer or self.remove_layer(existing_layer)

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

        self.add_layer(eval(str(basemap_tiles[basemap])))

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
    ) -> ipl.TileLayer:
        """Search a layer by name or index.

        Args:
            key: the layer name, the layer key, the index or directly the layer
            base: either the basemaps should be included in the search or not. default to false
            none_ok: if True the function will not raise error if no layer is found. Default to False

        Returns:
            The first layer using the same name or index else None
        """
        # filter the layers
        layers = self.layers if base else [lyr for lyr in self.layers if not lyr.base]

        if isinstance(key, str):
            layer = next((lyr for lyr in layers if lyr.key == key), None)
            layer = layer or next((lyr for lyr in layers if lyr.name == key), None)
        elif isinstance(key, int):
            size = len(layers)
            layer = layers[key] if -size <= key < size else None
        elif isinstance(key, ipl.Layer):
            layer = next((lyr for lyr in layers if lyr == key), None)
        else:
            raise ValueError(f"key must be a int or a str, {type(key)} given")

        if layer is None and none_ok is False:
            raise ValueError(f"no layer corresponding to {key} on the map")

        return layer

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

        return self.add(self.legend)

        # ##########################################################################
        # ###                overwrite geemap calls                              ###
        # ##########################################################################

    setCenter = set_center
    centerObject = zoom_ee_object
    addLayer = add_ee_layer
    getScale = get_scale
