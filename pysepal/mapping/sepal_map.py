"""The ``SepalMap``: a MapLibre map that draws a layer store."""

# known bug of rasterio
import os

from pysepal.mapping.gdal_env import GDAL_ENV_VARS, prune_foreign_gdal_env
from pysepal.mapping.visualization import validate_ee_object
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.theme import ThemeState, resolve_theme_state

if any(var in os.environ for var in GDAL_ENV_VARS):
    prune_foreign_gdal_env()

import asyncio
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Union

import ee
import traitlets
from eeclient.client import EESession
from pysepal_map import DRAW_MODES, Controls, MapWidget, Side
from typing_extensions import Self

from pysepal.frontend.styles import THEMES
from pysepal.layers import (
    LayerSpec,
    LayerStore,
    Legend,
    RenderLayer,
    prepare,
    prepare_sync,
)
from pysepal.layers.preparation import (
    CLIENT_PREFIX_ENV_VAR,  # noqa: F401  (public re-export)
)
from pysepal.mapping.basemaps import BASEMAP_NAMES, get_basemap
from pysepal.mapping.handle import LayerHandle, ZoomResult
from pysepal.mapping.maplibre_engine import MapLibreEngine
from pysepal.message import msg
from pysepal.scripts import decorator as sd
from pysepal.scripts import utils as su

if TYPE_CHECKING:
    from matplotlib import colors as mpc

__all__ = ["SepalMap"]

log = logging.getLogger("sepalui.mapping")

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

_SEPAL_BASEMAPS = ("SEPAL_LIGHT", "SEPAL_DARK")

#: Metres per CSS pixel at zoom 0 on the equator, for MapLibre's 512 px world.
_METERS_PER_PX = 78271.517

_GUIDE = "docs/guides/migrating-to-pysepal-5.md"


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


def _in_zone(spec: LayerSpec, overlay: bool) -> LayerSpec:
    return spec.model_copy(update={"zone": "overlay"}) if overlay else spec


def _with_legend(spec: LayerSpec, legend: Legend | None) -> LayerSpec:
    return spec if legend is None else spec.model_copy(update={"legend": legend})


def _draw_labels() -> dict[str, str]:
    """The draw toolbar's labels in the current language, as ``Draw.set_labels`` takes them."""
    labels = {mode: msg(f"map_view.draw.{mode}") for mode in (*DRAW_MODES, "select")}
    return {**labels, "clear": msg("map_view.draw.clear_all")}


def _close_part(part: str, close: Callable[[], None]) -> None:
    """Run one step of a close, and log its failure instead of raising it.

    Solara closes a kernel's widgets in one loop with no guard
    (``Widget.close_all``): a raise would stop it and leak the kernel.
    """
    try:
        close()
    except Exception:
        log.exception("closing the map's %s failed", part)


class SepalMap(MapWidget):
    """A MapLibre map of the SEPAL theme, drawing the layers of a :class:`~pysepal.layers.LayerStore`.

    Its persistent configuration (layers, basemap, theme, controls, insets) is
    declared in the widget state; only camera moves are commands. Layers live in
    :attr:`layer_store`, top first, and the layer methods return a live
    :class:`~pysepal.mapping.LayerHandle`. It can display local rasters and Earth
    Engine objects with methods that have the same signature as in the GEE
    JavaScript console.
    """

    basemaps = traitlets.Tuple()
    "The basemaps a user can pick from, in the order they were given."

    basemap = traitlets.Unicode()
    "The basemap shown, one of :attr:`basemaps`."

    theme = traitlets.Unicode("light", read_only=True)
    "The theme the map draws in, ``light`` or ``dark``, read-only: the map follows its theme state."

    gee: bool = True
    "Whether the map uses the Earth Engine binding."

    layer_store: LayerStore
    "The layers the map draws, top first: what the layer panel lists and edits."

    layer_engine: Optional[MapLibreEngine] = None
    "Draws :attr:`layer_store` on the map."

    # Class defaults, for close(): ipywidgets' __del__ calls it on an instance whose
    # constructor arguments were refused, and a failed construction calls it too.
    _theme_source = None
    inspector = None
    _map_closed = False
    _widget_ready = False

    _REMOVED_MEMBERS = {
        "dc": "m.draw.begin(modes) and the DrawSession it returns",
        "show_dc": "m.draw.begin(modes)",
        "hide_dc": "end() on the DrawSession that m.draw.begin(modes) returns",
        "v_inspector": "SepalMap(inspector=True) shown in a MapView",
        "on_interaction": "m.on_click(callback) for clicks; tooltips (VectorStyle(tooltip=...)) for hover",
        "add_legend": "the MapView legend, built from each layer's legend",
        "add_colorbar": "the MapView legend, built from each layer's legend",
        "add_layer": "m.layer_store.add() with a LayerSpec (LayerSpec.from_tiles, ...)",
        "layers": "m.layer_store, top first, and the LayerHandle the layer methods return",
        "add_control": "Solara components in MapView(overlays=...)",
        "remove_control": "Solara components in MapView(overlays=...)",
        "controls": "Solara components in MapView(overlays=...)",
        "viewport_inset_left": "m.set_insets(left=..., right=..., top=..., bottom=...)",
        "viewport_inset_right": "m.set_insets(left=..., right=..., top=..., bottom=...)",
        "viewport_inset_bottom": "m.set_insets(left=..., right=..., top=..., bottom=...)",
        "canvas_width_px": "nothing: the browser fits the camera to the map element itself",
        "canvas_height_px": "nothing: the browser fits the camera to the map element itself",
        "center": "m.view to read the camera and m.set_center(lng, lat, zoom) to move it",
        "zoom": "m.view to read the camera and m.set_center(lng, lat, zoom) to move it",
    }

    def __init__(
        self,
        basemaps: Sequence[str] = (),
        *,
        gee: bool = True,
        theme_state: Optional[ThemeState] = None,
        gee_session: Optional[EESession] = None,
        gee_interface: Optional[GEEInterface] = None,
        fullscreen: bool = False,
        fullscreen_control: bool = False,
        layer_store: Optional[LayerStore] = None,
        center: tuple[float, float] = (0.0, 0.0),
        zoom: float = 3.0,
        height: str = "400px",
        loop: Optional[asyncio.AbstractEventLoop] = None,
        inspector: bool = False,
        coordinates: bool = False,
        link_group: Optional[str] = None,
    ) -> None:
        """Build a map that draws a layer store.

        Args:
            basemaps: the basemaps a user can pick from, the first one shown. Defaults to the SEPAL background of the theme.
            gee: whether or not to use the ee binding. If False none of the earthengine display functionalities can be used. default to True
            theme_state: the theme state the map follows. Defaults to the current kernel's theme, which ``resolve_theme_state()`` returns.
            gee_session (optional): a custom EESession object to do gee requests. default to None (deprecated in favor of gee_interface)
            gee_interface: a shared GEEInterface instance. If provided, takes precedence over gee_session
            fullscreen: make the map fill its container (``height="100%"``).
            fullscreen_control: show the fullscreen control; the zoom and scale controls are always shown.
            layer_store: the layers to draw, for a store shared with other components. The layers already in it are drawn with their stored visibility. Defaults to a new, empty store.
            center: the first camera center, as ``(lng, lat)``.
            zoom: the first zoom level. MapLibre counts a 512 px world at zoom 0.
            height: the CSS height of the map.
            loop: the loop the widget and the engine run their callbacks on. Leave it unset under Solara: the widget adopts the loop of the first message from a view, and the new one after a reconnect. Pass one only for a host other than Solara.
            inspector: build the map's value inspector as ``m.inspector``.
            coordinates: show the pointer's coordinates.
            link_group: the group of maps this one keeps one camera with (see :attr:`link_group`). A group that has a camera replaces ``center`` and ``zoom`` with it.

        Raises:
            ValueError: if both gee_session and gee_interface are provided, or a basemap is unknown

        .. versionadded:: 3.0.0
            Added gee_interface parameter for sharing GEEInterface instances across components.
        """
        if gee_session and gee_interface:
            raise ValueError(
                "Cannot provide both gee_session and gee_interface. "
                "Use gee_interface for shared instances or gee_session for component-specific sessions."
            )

        log.debug(
            f"Map initialization with gee: {gee} and session: {gee_session} and interface: {gee_interface} ID: {id(gee_interface)}"
        )

        self._zooms_started = 0
        self.inspector = None
        self._home = (tuple(center), zoom)
        # MapWidget sets what its close() reads before anything in it can raise
        self._widget_ready = True
        super().__init__(
            center=center,
            zoom=zoom,
            height="100%" if fullscreen else height,
            loop=loop,
            link_group=link_group,
        )
        try:
            self.layer_store = layer_store if layer_store is not None else LayerStore()
            self.layer_store.follow_loop(self)
            self.gee = gee
            if gee:
                if gee_interface:
                    self.gee_interface = gee_interface
                else:
                    # Raises under PER_CONNECTION when gee_session is None; keep it
                    # ahead of init_ee() so a refused map initialises no global ee.
                    self.gee_interface = GEEInterface(session=gee_session)
                su.init_ee()

            source = resolve_theme_state(theme_state)
            self.set_trait("theme", "dark" if self._theme_is_dark(source) else "light")
            choices = tuple(basemaps) or (f"SEPAL_{self.theme.upper()}",)
            self._set_basemaps(choices, choices[0])

            self.layer_engine = MapLibreEngine(
                self,
                self.layer_store,
                gee_interface=getattr(self, "gee_interface", None),
                loop=loop,
            )
            self.layer_engine.configure(
                basemap=get_basemap(self.basemap),
                theme=self.theme,
                controls=Controls(
                    zoom=True,
                    fullscreen=fullscreen_control,
                    scale=True,
                    coordinates=coordinates,
                ),
            )
            self.draw.set_color(THEMES[self.theme == "dark"]["info"])
            self.draw.set_labels(_draw_labels())
            if inspector:
                from pysepal.mapping.inspector import MapInspector

                self.inspector = MapInspector(self)
            self._bind_theme_source(source)
        except BaseException:
            self.close()
            raise

    @property
    def compare(self) -> bool:
        """Whether the map draws a swipe compare: each layer on its :attr:`LayerHandle.side`."""
        return self.layer_engine.compare if self.layer_engine is not None else False

    @compare.setter
    def compare(self, value: bool) -> None:
        """Turn the swipe compare on or off."""
        self.layer_engine.configure(compare=value)

    def __getattr__(self, name: str):
        """Say what replaced a removed member; only reached when normal lookup fails."""
        if name in type(self)._REMOVED_MEMBERS:
            raise AttributeError(
                f"SepalMap.{name} was removed in pysepal 5.0; use "
                f'{type(self)._REMOVED_MEMBERS[name]} or pin "pysepal<5". See {_GUIDE}'
            )
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

    def close(self) -> None:
        """Close the map: its pending async adds commit nothing, the store keeps its layers.

        A part that fails to close is logged, and the rest still closes.
        """
        self._map_closed = True
        _close_part("theme binding", self._unbind_theme_source)
        if self.inspector is not None:
            _close_part("inspector", self.inspector.close)
        if self.layer_engine is not None:
            _close_part("layer engine", self.layer_engine.close)
        if self._widget_ready:
            _close_part("widget", super().close)

    # -- theme ------------------------------------------------------------------------------

    def bind_theme_state(self, theme_state: Optional[ThemeState]) -> None:
        """Follow the ``dark`` trait of a theme state, or the current kernel's theme for None."""
        self._bind_theme_source(resolve_theme_state(theme_state))

    def _bind_theme_source(self, source) -> None:
        if source is self._theme_source or self._map_closed:
            return
        self._unbind_theme_source()
        source.observe(self._on_theme_change, "dark")
        self._theme_source = source
        self._apply_theme(self._theme_is_dark(source))

    def _unbind_theme_source(self) -> None:
        """Stop following the current theme source, if any.

        traitlets keeps ``_on_theme_change``, and a bound method holds the map.
        A source outliving the map -- the kernel's theme outlives every map built
        in it -- would otherwise keep it, its layers and its Earth Engine objects
        reachable.
        """
        previous, self._theme_source = self._theme_source, None
        if previous is None:
            return
        try:
            previous.unobserve(self._on_theme_change, "dark")
        except (AttributeError, KeyError, ValueError):
            pass

    def _on_theme_change(self, change) -> None:
        self._apply_theme(bool(change["new"]))

    def _apply_theme(self, is_dark: bool) -> None:
        """Draw in a theme, with the SEPAL basemaps of that theme."""
        theme = "dark" if is_dark else "light"
        if theme == self.theme:
            return
        self.set_trait("theme", theme)
        self.draw.set_color(THEMES[is_dark]["info"])
        if self.layer_engine is not None:
            self.layer_engine.configure(theme=theme)
        variant = f"SEPAL_{theme.upper()}"

        def swap(name: str) -> str:
            return variant if name in _SEPAL_BASEMAPS else name

        # With both variants offered, the choices stay; only the one shown follows the theme.
        both = all(name in self.basemaps for name in _SEPAL_BASEMAPS)
        choices = self.basemaps if both else [swap(name) for name in self.basemaps]
        self._set_basemaps(choices, swap(self.basemap))

    @staticmethod
    def _theme_is_dark(source) -> bool:
        """Normalize theme sources that expose a `dark` traitlet."""
        return getattr(source, "dark", None) is True

    # -- basemaps ---------------------------------------------------------------------------

    def _set_basemaps(self, choices: Sequence[str], current: str) -> None:
        """Set the choices and the current basemap together, so no observer sees a bad pair."""
        choices = tuple(dict.fromkeys(choices))
        unknown = [name for name in choices if name not in BASEMAP_NAMES]
        if unknown:
            raise ValueError(f"Unknown basemap {unknown}: use one of SepalMap.get_basemap_list()")
        if current not in choices:
            raise ValueError(f"The basemap {current!r} is not among {choices}")
        with self.hold_trait_notifications():
            self.basemaps = choices
            self.basemap = current

    @traitlets.validate("basemaps")
    def _valid_basemaps(self, proposal) -> tuple:
        choices = tuple(dict.fromkeys(proposal["value"]))
        unknown = [name for name in choices if name not in BASEMAP_NAMES]
        if unknown:
            raise traitlets.TraitError(f"Unknown basemap {unknown}")
        if self.basemap not in choices:
            raise traitlets.TraitError(f"The basemap {self.basemap!r} is not among {choices}")
        return choices

    @traitlets.validate("basemap")
    def _valid_basemap(self, proposal) -> str:
        if proposal["value"] not in self.basemaps:
            raise traitlets.TraitError(f"{proposal['value']!r} is not among {self.basemaps}")
        return proposal["value"]

    @traitlets.observe("basemap")
    def _draw_basemap(self, change) -> None:
        if self.layer_engine is not None:
            self.layer_engine.configure(basemap=get_basemap(change["new"]))

    def add_basemap(self, basemap: str = "HYBRID") -> None:
        """Add a basemap to the choices and show it.

        Args:
            basemap: one of :meth:`get_basemap_list`. Defaults to 'HYBRID'.
        """
        self._set_basemaps((*self.basemaps, basemap), basemap)

    @staticmethod
    def get_basemap_list() -> List[str]:
        """Return the names of every basemap the map accepts."""
        return list(BASEMAP_NAMES)

    # -- camera -----------------------------------------------------------------------------

    def zoom_bounds(
        self, bounds: Sequence[float], *, padding: int = 20, max_zoom: float = 18
    ) -> Self:
        """Fit the camera to the given bounds.

        Args:
            bounds: coordinates corners as minx, miny, maxx, maxy in EPSG:4326
            padding: px kept free around the bounds; one the map cannot hold is reduced.
            max_zoom: the closest zoom of the fit, so that a point is not shown at zoom 24.
        """
        self.fit_bounds(tuple(bounds), padding=padding, max_zoom=max_zoom)
        return self

    @sd.need_ee
    def zoom_ee_object(self, item: ee.ComputedObject, *, padding: int = 20) -> Self:
        """Fit the camera to an Earth Engine object.

        Args:
            item: the geometry to zoom on
            padding: px kept free around the object
        """
        return self.zoom_bounds(self.gee_interface.get_bounds(item), padding=padding)

    def zoom_raster(self, layer: Union[LayerHandle, str, Path], *, padding: int = 20) -> Self:
        """Fit the camera to a raster: a layer of the map, by handle or id, or a file.

        Args:
            layer: a handle or an id of :attr:`layer_store`, which uses the bounds of its render, or the path of a raster file.
            padding: px kept free around the raster
        """
        if isinstance(layer, LayerHandle):
            self._check_handle(layer)
            self.zoom_layer(layer.id, padding=padding)
            return self
        if isinstance(layer, str) and layer in self.layer_store:
            self.zoom_layer(layer, padding=padding)
            return self

        import rioxarray
        from rasterio.crs import CRS

        da = rioxarray.open_rasterio(layer, masked=True)

        # unproject if necessary
        epsg_4326 = "EPSG:4326"
        if da.rio.crs != CRS.from_string(epsg_4326):
            da = da.rio.reproject(epsg_4326)

        return self.zoom_bounds(da.rio.bounds(), padding=padding)

    def zoom_layer(self, layer_id: str, *, padding: int = 20) -> ZoomResult:
        """Fit the camera to a layer, with the bounds its render knows.

        Returns:
            ``"moved"``, or why it did not: ``"missing"``, ``"preparing"``, ``"failed"`` or ``"no_bounds"``.
        """
        result = self.layer_engine.bounds(layer_id)
        if isinstance(result, str):
            return result
        self.zoom_bounds(result, padding=padding)
        return "moved"

    async def zoom_layer_async(self, layer_id: str, *, padding: int = 20) -> ZoomResult:
        """Fit the camera to a layer, looking Earth Engine bounds up without blocking.

        A camera command issued meanwhile wins: a newer zoom, ``fit_bounds`` or
        ``set_center``, a replaced layer or a closed map make it return
        ``"superseded"``, without moving.

        Returns:
            What :meth:`zoom_layer` returns, or ``"superseded"``.
        """
        self._zooms_started += 1
        ticket, seq = self._zooms_started, self.view_request["seq"]
        before = self.layer_engine.accepted(layer_id)
        result = await self.layer_engine.bounds_async(layer_id)
        after = None if self._map_closed else self.layer_engine.accepted(layer_id)
        if (
            self._map_closed
            or not _same_entry(before, after)
            or ticket != self._zooms_started
            or self.view_request["seq"] != seq
        ):
            return "superseded"
        if isinstance(result, str):
            return result
        self.zoom_bounds(result, padding=padding)
        return "moved"

    @sd.need_ee
    def centerObject(self, item: ee.ComputedObject, zoom: Optional[float] = None) -> Self:
        """Center the map on an Earth Engine object, as the Code Editor does.

        Args:
            item: the object to center on
            zoom: the zoom to use; without one, the map zooms to fit the object
        """
        if zoom is None:
            return self.zoom_ee_object(item)
        west, south, east, north = self.gee_interface.get_bounds(item)
        self.set_center((west + east) / 2, (south + north) / 2, zoom)
        return self

    def get_scale(self) -> float:
        """Return the approximate size of a CSS pixel at the map center, in meters.

        It reads the camera a view reported, else the constructor's center and zoom.
        """
        if self.view:
            (_, lat), zoom = self.view["center"], self.view["zoom"]
        else:
            (_, lat), zoom = self._home
        return _METERS_PER_PX * math.cos(math.radians(lat)) / 2**zoom

    # -- layers -----------------------------------------------------------------------------

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
        side: Side = "both",
        legend: Legend | None = None,
    ) -> LayerHandle:
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
            vmin: value mapped to the first color. Defaults to the file's own minimum, i.e. an auto-stretch, except that a byte raster given neither end is drawn over 0-255; the legend shows the range drawn. Pin both ends to reproduce a fixed palette (a QGIS ramp, a shared legend) rather than one that shifts per file. Ignored when ``class_colors`` is set.
            vmax: value mapped to the last color. See ``vmin``.
            nodata: value to render transparent. Defaults to the file's declared nodata, which some products tag incorrectly.
            optimize: prepare a tiled COG with overviews before serving. On by default because rio-tiler otherwise reads full-resolution pixels for every tile. Turn it off for a large raster you do not want copied into the tile cache, or one that already has ``.ovr`` sidecars.
            warp_to_3857: reproject to Web Mercator while preparing, so tiles are cut in the CRS they are served in instead of being warped per request. Needs ``optimize=True``. Off by default because it doubles the preparation work for a raster that is already close to 3857.
            side: the half of a compare map that draws a new layer, ``"left"``, ``"right"`` or ``"both"``; a replaced layer keeps its side. Ignored outside compare.
            legend: the legend of the layer, shown in place of the one the asset or the style gives and kept when the layer is restyled; an empty ``Legend()`` shows none. Change it later through :attr:`LayerHandle.legend`.

        Returns:
            a handle to the layer.

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
        spec = _with_legend(spec, legend)
        render = prepare_sync(spec, optimize=optimize, warp_to_3857=warp_to_3857)
        return self._commit(spec, render, opacity=opacity, side=side, fit=fit_bounds)

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
        side: Side = "both",
        legend: Legend | None = None,
    ) -> Optional[LayerHandle]:
        """Add a local raster without blocking the event loop.

        Same arguments as :meth:`add_raster`, ``legend`` included. Preparing a raster rewrites every
        one of its pixels into a tiled COG; that runs in a worker thread here,
        leaving only the commit to the store on the loop.

        Returns:
            a handle to the layer, or None when a newer action on the same key (a remove,
            a restyle or another add) superseded this call while it was preparing, or the
            map closed meanwhile.

        Raises:
            LayerPrepareError: when the raster cannot be prepared for display.
        """
        spec = self._raster_spec(
            image, bands, layer_name, colormap, key, class_colors, vmin, vmax, nodata
        )
        spec = _with_legend(spec, legend)
        return await self._commit_async(
            spec,
            opacity=opacity,
            side=side,
            fit=fit_bounds,
            optimize=optimize,
            warp_to_3857=warp_to_3857,
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
        side: Side = "both",
        fit: bool = False,
        generation: Optional[int] = None,
    ) -> Optional[LayerHandle]:
        """Put a prepared spec in the store, replacing a layer with the same id in place.

        Args:
            spec: the layer spec, in either zone.
            render: the render prepared from ``spec``; the engine draws it as is.
            shown: whether a new layer is visible.
            opacity: the opacity of a new layer.
            side: the side of a new layer.
            fit: fit the map to the layer bounds, when the render knows them.
            generation: the token of the reservation made before preparing; the add is
                dropped, and None returned, when a newer write to the id happened since or
                the map closed.
        """
        store = self.layer_store
        if generation is not None and (self._map_closed or store.generation(spec.id) != generation):
            return None
        self.layer_engine.put(render)
        added = store.add(
            spec,
            visible=shown,
            opacity=opacity,
            side=side,
            replace=True,
            expect_generation=generation,
        )
        if added is None:
            return None
        if fit and render.bounds is not None and not self._map_closed:
            self.zoom_bounds(render.bounds)
        return LayerHandle(self, spec.id)

    async def _commit_async(
        self,
        spec: LayerSpec,
        *,
        shown: bool = True,
        opacity: float = 1.0,
        side: Side = "both",
        fit: bool = False,
        **options,
    ) -> Optional[LayerHandle]:
        """Prepare a spec without blocking the loop, then :meth:`_commit` it.

        The id stays reserved while preparing, so that any newer write to it (from the
        panel, a sync add, another async one, a removal) wins over this call.

        Args:
            spec: the layer spec, in either zone.
            shown: whether a new layer is visible.
            opacity: the opacity of a new layer.
            side: the side of a new layer.
            fit: fit the map to the layer bounds, when the render knows them.
            options: the keyword arguments of :func:`~pysepal.layers.prepare`.
        """
        if self._map_closed:
            return None
        store = self.layer_store
        generation = store.reserve(spec.id, spec.name)
        try:
            render = await prepare(spec, **options)
            return self._commit(
                spec,
                render,
                shown=shown,
                opacity=opacity,
                side=side,
                fit=fit,
                generation=generation,
            )
        finally:
            store.release(spec.id, generation)

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
        side: Side = "both",
        legend: Legend | None = None,
    ) -> LayerHandle:
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
            overlay: put the layer in the overlay zone of :attr:`layer_store`, drawn above every data layer and listed by no layer panel. For a reference layer such as the AOI. Default to False.
            side: the half of a compare map that draws a new layer, ``"left"``, ``"right"`` or ``"both"``; a replaced layer keeps its side. Ignored outside compare.
            legend: the legend of the layer, shown in place of the one the asset or the style gives and kept when the layer is restyled; an empty ``Legend()`` shows none. Change it later through :attr:`LayerHandle.legend`.

        Returns:
            a handle to the layer.

        Raises:
            LayerPrepareError: when Earth Engine cannot render the layer.
        """
        spec = self._ee_spec(ee_object, vis_params, name, key, viz_name, use_map_vis)
        spec = _with_legend(_in_zone(spec, overlay), legend)
        render = prepare_sync(spec, gee_interface=self.gee_interface)
        handle = self._commit(spec, render, shown=shown, opacity=opacity, side=side)
        if autocenter and handle is not None:
            self.zoom_layer(spec.id)
        return handle

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
        side: Side = "both",
        legend: Legend | None = None,
    ) -> Optional[LayerHandle]:
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
            overlay: put the layer in the overlay zone of :attr:`layer_store`, drawn above every data layer and listed by no layer panel. For a reference layer such as the AOI. Default to False.
            side: the half of a compare map that draws a new layer, ``"left"``, ``"right"`` or ``"both"``; a replaced layer keeps its side. Ignored outside compare.
            legend: the legend of the layer, shown in place of the one the asset or the style gives and kept when the layer is restyled; an empty ``Legend()`` shows none. Change it later through :attr:`LayerHandle.legend`.

        Returns:
            a handle to the layer, or None when a newer action on the same key superseded
            this call, or the map closed meanwhile.

        Raises:
            LayerPrepareError: when Earth Engine cannot render the layer.
        """
        spec = self._ee_spec(ee_object, vis_params, name, key, viz_name, use_map_vis, attribution)
        spec = _with_legend(_in_zone(spec, overlay), legend)
        handle = await self._commit_async(
            spec, shown=shown, opacity=opacity, side=side, gee_interface=self.gee_interface
        )
        if autocenter and handle is not None:
            await self.zoom_layer_async(spec.id)
        return handle

    def _default_name(self, key: str) -> str:
        """Name a layer added without a name.

        A key already in the store keeps the name of its layer. Otherwise the name is
        ``Layer N``, N counting the layers of the store, raised until neither the name nor
        the id it gives is used by a layer of the store or reserved.
        """
        store = self.layer_store
        if key and key in store:
            return store.get(key).name
        taken = {name for spec in store.specs() for name in (spec.id, spec.name)}
        taken |= {name for item in store.reserved().items() for name in item}
        n = len(store) + 1
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

    # -- lookup -----------------------------------------------------------------------------

    def find_layer(self, key: Union[str, LayerHandle]) -> Optional[LayerHandle]:
        """Find a layer of :attr:`layer_store`.

        A string is looked up as an id, then as a name in drawing order: the overlay
        zone first, then the data zone, each top first. Hidden layers are found too.

        Args:
            key: the layer id or name, or a handle.

        Returns:
            a handle to the layer, or None when there is none.

        Raises:
            ValueError: for a handle of another layer store.
            TypeError: for a key that is neither a string nor a handle.
        """
        layer_id = self._resolve(key, pending=False)
        return None if layer_id is None else LayerHandle(self, layer_id)

    def remove_layer(self, key: Union[str, LayerHandle], *, none_ok: bool = False) -> None:
        """Remove a layer of :attr:`layer_store`, found as :meth:`find_layer` does.

        An id or a name an async add reserved cancels that add.

        Args:
            key: the layer id or name, or a handle.
            none_ok: do not raise when no layer is found.

        Raises:
            ValueError: when no layer is found and not ``none_ok``, or for a handle of
                another layer store.
            TypeError: for a key that is neither a string nor a handle.
        """
        layer_id = self._resolve(key, pending=True)
        if layer_id is not None:
            self.layer_store.remove(layer_id, missing_ok=True)
        elif not none_ok:
            raise ValueError(f"no layer corresponding to {key} on the map")

    def remove_all(self, keep_names: Optional[list[str]] = None) -> None:
        """Remove every layer of :attr:`layer_store`, both zones and pending async adds.

        Args:
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

    def _check_handle(self, handle: LayerHandle) -> None:
        if handle.store is not self.layer_store:
            raise ValueError(f"{handle!r} belongs to the layer store of another map")

    def _resolve(self, key: Union[str, LayerHandle], *, pending: bool) -> Optional[str]:
        """The id ``key`` names: in the store, else, when ``pending``, reserved by an async add."""
        store = self.layer_store
        reserved = store.reserved() if pending else {}
        if isinstance(key, LayerHandle):
            self._check_handle(key)
            return key.id if key.id in store or key.id in reserved else None
        if not isinstance(key, str):
            raise TypeError(f"key must be a layer id, a name or a LayerHandle, got {type(key)}")
        if key in store or key in reserved:
            return key
        named = [i for i in store.drawing_order() if store.get(i).name == key]
        named += [layer_id for layer_id, name in reserved.items() if name == key]
        return named[0] if named else None

    # ##########################################################################
    # ###                overwrite geemap calls                              ###
    # ##########################################################################

    setCenter = MapWidget.set_center
    addLayer = add_ee_layer
    getScale = get_scale


def _same_entry(before, after) -> bool:
    """Whether two ``accepted`` answers name the same accepted entry."""
    if before is None or after is None:
        return before is after
    return before[0] is after[0] and before[1] is after[1]
