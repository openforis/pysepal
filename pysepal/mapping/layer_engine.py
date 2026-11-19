"""Mirror a :class:`~pysepal.layers.LayerStore` onto an ipyleaflet map.

Every store slot owns a Leaflet pane, so the store order decides the stacking whatever
the layer type: a GeoJSON can sit below a tile layer.
"""

import asyncio
import logging
from collections import OrderedDict
from typing import Optional

import ipyleaflet as ipl
from traitlets import Unicode

from pysepal.frontend.styles import THEMES
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    LayerStore,
    RenderLayer,
    StoreEvent,
    VectorStyle,
    local_fingerprint,
    prepare,
    prepare_sync,
)
from pysepal.mapping.layer import EELayer
from pysepal.scripts.gee_interface import GEEInterface

__all__ = [
    "OVERLAY_PANE",
    "OVERLAY_Z",
    "PANE_PREFIX",
    "PANE_Z_MAX",
    "PANE_Z_MIN",
    "LeafletEngine",
    "PanedGeoJSON",
    "leaflet_style",
    "pane_definitions",
    "pane_name",
]

log = logging.getLogger("sepalui.mapping")

PANE_Z_MIN = 201
PANE_Z_MAX = 398
PANE_PREFIX = "pysepal-layer-"
OVERLAY_PANE = "pysepal-overlay"
OVERLAY_Z = 399

_CACHE_SIZE = 64
_POINT_RADIUS = 5
_overflow_warned = False


def pane_name(slot: int) -> str:
    """Return the pane of a store slot, 0 being the top one.

    Args:
        slot: the index of the layer in the store.

    Returns:
        The pane name. Slots past the last pane share the lowest one.
    """
    global _overflow_warned
    z = PANE_Z_MAX - slot
    if z < PANE_Z_MIN:
        if not _overflow_warned:
            _overflow_warned = True
            log.warning(
                "More than %d layers: the lowest ones share a pane.", PANE_Z_MAX - PANE_Z_MIN + 1
            )
        z = PANE_Z_MIN
    return f"{PANE_PREFIX}{z}"


def pane_definitions() -> dict[str, dict[str, str]]:
    """Return the panes the engine draws in, in the shape of ``ipyleaflet.Map.panes``."""
    panes = {f"{PANE_PREFIX}{z}": {"zIndex": str(z)} for z in range(PANE_Z_MIN, PANE_Z_MAX + 1)}
    panes[OVERLAY_PANE] = {"zIndex": str(OVERLAY_Z)}
    return panes


class PanedGeoJSON(ipl.GeoJSON):
    """A GeoJSON layer whose polygons and lines are drawn in its pane.

    Its ``pane`` must be set: an empty one reaches Leaflet as the name of a pane that
    does not exist. Points are not covered, they take the pane of ``point_style``.
    """

    # A creation option of L.geoJson, which every path inherits; the base view only
    # sets the group's pane after the paths exist.
    pane = Unicode("").tag(sync=True, o=True)

    theme_style: Optional[dict] = None
    "the style entries that follow the map theme, keyed by whether it is dark"


def leaflet_style(style: VectorStyle, opacity: float, default_color: str) -> dict:
    """Translate a vector style to Leaflet path options.

    Args:
        style: the vector style.
        opacity: the layer opacity, applied to both the stroke and the fill.
        default_color: the stroke colour of a style that leaves it to the theme.

    Returns:
        The ``color``, ``weight``, ``opacity``, ``fillColor`` and ``fillOpacity`` options.
    """
    color = style.stroke or default_color
    return {
        "color": color,
        "weight": style.width,
        "opacity": opacity,
        "fillColor": style.fill or color,
        "fillOpacity": style.effective_fill_opacity * opacity,
    }


def _theme_style(style: VectorStyle) -> dict[bool, dict[str, str]]:
    """Return the style entries that follow the theme primary, keyed by ``is_dark``."""
    if style.stroke is not None:
        return {}
    themed = {}
    for is_dark in (True, False):
        primary = THEMES[is_dark]["primary"]
        themed[is_dark] = {"color": primary}
        if style.fill is None:
            themed[is_dark]["fillColor"] = primary
    return themed


def _pmtiles_style(style: VectorStyle, source_layer: Optional[str], default_color: str) -> dict:
    options = leaflet_style(style, 1.0, default_color)
    return {
        "layers": [
            {
                "id": "fill",
                "type": "fill",
                "source-layer": source_layer,
                "paint": {
                    "fill-color": options["fillColor"],
                    "fill-opacity": options["fillOpacity"],
                },
            },
            {
                "id": "line",
                "type": "line",
                "source-layer": source_layer,
                "paint": {"line-color": options["color"], "line-width": options["weight"]},
            },
        ]
    }


class LeafletEngine:
    """Keep an ipyleaflet map in step with a layer store.

    Each spec is prepared into a :class:`~pysepal.layers.RenderLayer`, cached by its
    ``render_hash``, and drawn as a leaflet layer in the pane of its slot. Layers added
    hidden are prepared and built too, but stay off the map until shown.
    """

    def __init__(
        self, m: ipl.Map, store: LayerStore, *, gee_interface: Optional[GEEInterface] = None
    ) -> None:
        """Bind the engine to a map and a store, and draw the layers already in the store.

        Args:
            m: the map to draw on.
            store: the layers to mirror.
            gee_interface: the interface that prepares Earth Engine layers.
        """
        self.m = m
        self.store = store
        self.gee_interface = gee_interface
        self._cache: OrderedDict[str, RenderLayer] = OrderedDict()
        self._layers: dict[str, ipl.Layer] = {}
        self._drawn: dict[str, tuple[LayerSpec, RenderLayer]] = {}
        self._tokens: dict[str, int] = {}
        self._tasks: set[asyncio.Task] = set()
        self._closed = False

        m.panes = {**m.panes, **pane_definitions()}
        self._unsubscribe = store.subscribe(self._on_event)
        for layer_id in store.ids:
            self._on_event(StoreEvent("added", layer_id))

    def put(self, render: RenderLayer) -> None:
        """Seed the render cache, keyed by ``render_hash``.

        Args:
            render: the render to cache.
        """
        self._cache[render.render_hash] = render
        self._cache.move_to_end(render.render_hash)
        while len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)

    def leaflet_layer(self, layer_id: str) -> Optional[ipl.Layer]:
        """Return the leaflet layer built for an id, attached or not.

        Args:
            layer_id: the layer id.

        Returns:
            The layer, or None while it is not built.
        """
        return self._layers.get(layer_id)

    async def wait_idle(self) -> None:
        """Wait for every preparation in flight."""
        while pending := [task for task in self._tasks if not task.done()]:
            await asyncio.gather(*pending, return_exceptions=True)

    def close(self) -> None:
        """Stop following the store and take the engine's layers off the map."""
        self._closed = True
        self._unsubscribe()
        for task in self._tasks:
            task.cancel()
        for layer in self._layers.values():
            self._detach(layer)
            layer.close()
        self._layers.clear()
        self._drawn.clear()
        self._cache.clear()

    def _on_event(self, event: StoreEvent) -> None:
        layer_id = event.layer_id
        if event.kind in ("added", "updated", "removed"):
            self._tokens[layer_id] = self._tokens.get(layer_id, 0) + 1
        if event.kind == "removed":
            self._discard(layer_id)
        elif layer_id not in self.store:
            return
        if event.kind in ("added", "removed", "moved"):
            self._reconcile_order()
        if event.kind in ("added", "updated"):
            self._request(layer_id)
        elif event.kind == "visibility":
            self._show(layer_id)
        elif event.kind == "opacity":
            self._apply_opacity(layer_id)

    def _request(self, layer_id: str) -> None:
        token = self._tokens[layer_id]
        spec = self.store.get(layer_id)
        render = self._cached(spec)
        if render is not None:
            self._draw(layer_id, render)
            return

        self.store.set_status(layer_id, "pending")
        if self._tokens[layer_id] != token:
            return  # a status subscriber wrote to the layer meanwhile
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            try:
                render = prepare_sync(spec, gee_interface=self.gee_interface)
            except Exception as exc:
                self._settle(layer_id, token, error=exc)
            else:
                self._settle(layer_id, token, render=render)
            return
        task = loop.create_task(self._prepare(layer_id, token, spec))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _prepare(self, layer_id: str, token: int, spec: LayerSpec) -> None:
        try:
            render = await prepare(spec, gee_interface=self.gee_interface)
        except Exception as exc:
            self._settle(layer_id, token, error=exc)
        else:
            self._settle(layer_id, token, render=render)

    def _settle(
        self,
        layer_id: str,
        token: int,
        *,
        render: Optional[RenderLayer] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Apply a preparation outcome, unless a newer request for the id superseded it."""
        if self._closed or self._tokens.get(layer_id) != token or layer_id not in self.store:
            return
        if error is not None:
            unexpected = not isinstance(error, LayerPrepareError)
            log.warning(
                "Layer %s cannot be drawn: %s",
                layer_id,
                error,
                exc_info=error if unexpected else None,
            )
            self.store.set_status(layer_id, "error", error=str(error))
            return
        self.put(render)
        self._draw(layer_id, render)

    def _cached(self, spec: LayerSpec) -> Optional[RenderLayer]:
        """Return the cached render of a spec, unless its local files changed since."""
        render = self._cache.get(spec.render_hash)
        if render is None:
            return None
        try:
            fresh = render.fingerprint == local_fingerprint(spec)
        except OSError:
            fresh = False
        if not fresh:
            return None
        self._cache.move_to_end(spec.render_hash)
        return render

    def _draw(self, layer_id: str, render: RenderLayer) -> None:
        spec = self.store.get(layer_id)
        view = self.store.view(layer_id)
        layer = self._layers.get(layer_id)
        drawn = self._drawn.get(layer_id)
        if layer is not None and self._updatable(drawn, spec, render):
            self._update(layer, spec, render, view.opacity)
        else:
            pane = pane_name(self.store.ids.index(layer_id))
            new = self._build(spec, render, pane, view.opacity)
            self._layers[layer_id] = new
            if layer is not None:
                self._detach(layer)
                layer.close()
            if view.visible:
                self._attach(new)
        self._drawn[layer_id] = (spec, render)
        self.store.set_status(layer_id, "ready", legend=render.legend, kind=render.kind)

    @staticmethod
    def _updatable(
        drawn: Optional[tuple[LayerSpec, RenderLayer]], spec: LayerSpec, render: RenderLayer
    ) -> bool:
        """Whether the drawn widget can take ``render`` without being rebuilt."""
        if drawn is None:
            return False
        old_spec, old_render = drawn
        same_data = (
            old_spec.source.type == spec.source.type
            and old_spec.data_hash == spec.data_hash
            and old_render.kind == render.kind
            and old_render.fingerprint == render.fingerprint
        )
        # a PMTiles paint style is only read when the widget is created
        restyled_pmtiles = render.kind == "pmtiles" and old_render.render_hash != render.render_hash
        return same_data and not restyled_pmtiles

    def _build(self, spec: LayerSpec, render: RenderLayer, pane: str, opacity: float) -> ipl.Layer:
        if render.kind == "raster-xyz" and render.keepalive is not None:
            from localtileserver import get_leaflet_tile_layer

            layer = get_leaflet_tile_layer(
                render.keepalive,
                name=spec.name,
                pane=pane,
                opacity=opacity,
                visible=True,
                **(render.tile_kwargs or {}),
            )
            layer.raster = render.raster
        elif render.kind == "raster-xyz":
            layer = EELayer(
                ee_object=render.ee_object,
                theme_urls=render.theme_urls,
                url=self._themed_url(render),
                name=spec.name,
                pane=pane,
                opacity=opacity,
                max_zoom=render.max_zoom,
            )
        elif render.kind == "geojson":
            layer = PanedGeoJSON(data=render.data or {}, name=spec.name, pane=pane)
            self._style_vector(layer, render.vector_style, opacity)
        else:
            style = render.vector_style or VectorStyle()
            layer = ipl.PMTilesLayer(
                url=render.url,
                style=_pmtiles_style(style, render.source_layer, self._primary()),
                name=spec.name,
                pane=pane,
            )
        self._bind(layer, spec)
        return layer

    def _update(
        self, layer: ipl.Layer, spec: LayerSpec, render: RenderLayer, opacity: float
    ) -> None:
        """Restyle a widget in place; the data, the tile server and the pane stay."""
        self._bind(layer, spec)
        if render.kind == "raster-xyz":
            if isinstance(layer, EELayer):
                layer.ee_object = render.ee_object
                layer.theme_urls = render.theme_urls
            layer.url = self._themed_url(render)
        elif render.kind == "geojson":
            self._style_vector(layer, render.vector_style, opacity)

    @staticmethod
    def _bind(layer: ipl.Layer, spec: LayerSpec) -> None:
        layer.key = layer.layer_id = spec.id
        layer.name = spec.name
        if layer.has_trait("attribution"):
            layer.attribution = spec.attribution

    def _style_vector(
        self, layer: ipl.GeoJSON, style: Optional[VectorStyle], opacity: float
    ) -> None:
        style = style or VectorStyle()
        options = leaflet_style(style, opacity, self._primary())
        layer.theme_style = _theme_style(style)
        layer.style = options
        # points are circle markers, which do not inherit the pane of the group
        layer.point_style = {"radius": _POINT_RADIUS, **options, "pane": layer.pane}

    def _reconcile_order(self) -> None:
        """Move every built layer whose slot changed to the pane of its new slot."""
        moving = []
        for slot, layer_id in enumerate(self.store.ids):
            layer, pane = self._layers.get(layer_id), pane_name(slot)
            if layer is not None and layer.pane != pane:
                moving.append((layer_id, layer, pane))
        if not moving:
            return
        # a pane change on a displayed layer re-renders the whole map, so it happens detached
        for _, layer, _ in moving:
            self._detach(layer)
        # bottom first, so that m.layers, which index lookups read, keeps the stacking order
        for layer_id, layer, pane in reversed(moving):
            layer.pane = pane
            if isinstance(layer, ipl.GeoJSON):
                layer.point_style = {**layer.point_style, "pane": pane}
            if self.store.view(layer_id).visible:
                self._attach(layer)

    def _show(self, layer_id: str) -> None:
        # A GeoJSON view draws its features at creation even when hidden, and the map
        # recreates views on any layer change, so hidden layers stay off the map.
        layer = self._layers.get(layer_id)
        if layer is None:
            return
        if self.store.view(layer_id).visible:
            self._attach(layer)
        else:
            self._detach(layer)

    def _apply_opacity(self, layer_id: str) -> None:
        layer = self._layers.get(layer_id)
        opacity = self.store.view(layer_id).opacity
        if isinstance(layer, ipl.GeoJSON):
            self._style_vector(layer, self._drawn[layer_id][1].vector_style, opacity)
        elif isinstance(layer, ipl.RasterLayer):
            layer.opacity = opacity

    def _discard(self, layer_id: str) -> None:
        self._drawn.pop(layer_id, None)
        layer = self._layers.pop(layer_id, None)
        if layer is not None:
            self._detach(layer)
            layer.close()

    def _attach(self, layer: ipl.Layer) -> None:
        """Put a layer on the map, recoloured for the theme.

        Layers go on and off one at a time, through the base ``ipyleaflet.Map`` methods:
        ``LayerStateControl`` reads each change of ``m.layers`` as one layer, and the
        engine works on a plain map without reaching ``SepalMap.add_layer``.
        """
        if layer not in self.m.layers:
            self._theme(layer)
            ipl.Map.add(self.m, layer)

    def _detach(self, layer: ipl.Layer) -> None:
        if layer in self.m.layers:
            ipl.Map.remove(self.m, layer)

    def _theme(self, layer: ipl.Layer) -> None:
        """Recolour a layer for the map theme; the map only recolours attached layers."""
        apply = getattr(self.m, "_apply_layer_theme", None)
        if apply is not None:
            apply(layer, self._is_dark())

    def _is_dark(self) -> bool:
        is_dark = getattr(self.m, "_is_dark", None)
        return bool(is_dark()) if callable(is_dark) else False

    def _primary(self) -> str:
        return THEMES[self._is_dark()]["primary"]

    def _themed_url(self, render: RenderLayer) -> str:
        return render.theme_urls[self._is_dark()] if render.theme_urls else render.url
