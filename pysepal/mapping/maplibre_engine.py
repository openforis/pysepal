"""Draw a :class:`~pysepal.layers.LayerStore` on a :class:`pysepal_map.MapWidget`.

Each spec is prepared into a :class:`~pysepal.layers.RenderLayer`, and the whole
map is published as one declarative ``MapState``, at most once per tick of the
event loop.

An id's *accepted entry* is the ``(spec, render)`` the map draws for it. A
settled render becomes one only once its widget ``Layer`` builds under both
themes, so accepted entries always convert. A replacement being prepared, or
one that fails, leaves the previous entry drawn, and every conversion reads the
accepted spec, never the store's newer one.

The engine has no loop of its own. At every schedule it follows the first live
loop of the ``loop`` it was given, the widget's and the one running now; with
none, it prepares with ``prepare_sync`` and draws at once. Store writes belong
on that loop: an event that arrives on another thread is handed over to it.
Statuses go through the store's
:class:`~pysepal.mapping._layer_status.LayerStatusBoard`, shared with every
other engine drawing the store.
"""

import asyncio
import contextlib
import dataclasses
import hashlib
import inspect
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Literal, Optional, Union

import ee
from eeclient.exceptions import EERestException
from pysepal_map import (
    Basemap,
    Cluster,
    Controls,
    GeoJSONSource,
    Interaction,
    Layer,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)

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
from pysepal.mapping._layer_status import EngineStatus, status_board
from pysepal.mapping.basemaps import tile_urls
from pysepal.scripts.gee_interface import GEEInterface

__all__ = ["Bounds", "BoundsResult", "MapLibreEngine"]

log = logging.getLogger("sepalui.mapping")

Bounds = tuple[float, float, float, float]
BoundsResult = Union[Bounds, Literal["missing", "preparing", "failed", "no_bounds"]]

_CACHE_SIZE = 64
_KEEP: Any = object()
_TRANSIENT_CODES = (401, 403, 429)


def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _off_thread(loop: Optional[asyncio.AbstractEventLoop]) -> bool:
    """Whether ``loop`` runs, on another thread than this one."""
    return loop is not None and loop.is_running() and _running_loop() is not loop


def _transient(error: Exception) -> bool:
    """Whether an ee-client error is an auth, quota or server status it gave up retrying."""
    code = getattr(error, "code", None)
    if not isinstance(error, EERestException) or not isinstance(code, int):
        return False
    return code in _TRANSIENT_CODES or code >= 500


def _geojson_bytes(data: Optional[dict]) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode()


def _style_of(spec: LayerSpec) -> VectorStyle:
    return spec.style if isinstance(spec.style, VectorStyle) else VectorStyle()


def _fields(value: Union[bool, list]) -> Optional[tuple]:
    return None if value is False else () if value is True else tuple(value)


def _check_clusterable(data: Optional[dict]) -> None:
    """Raise ``ValueError`` unless every feature is a point without ``cluster=true``."""
    for feature in (data or {}).get("features", ()):
        geometry = feature.get("geometry")
        if geometry is None or geometry.get("type") != "Point":
            raise ValueError("clustering needs point features only")
        if (feature.get("properties") or {}).get("cluster") is True:
            raise ValueError("property cluster=true is reserved for clusters")


def _paint(spec: LayerSpec, is_dark: bool) -> VectorPaint:
    style = _style_of(spec)
    stroke = style.stroke or THEMES[is_dark]["primary"]
    return VectorPaint(
        stroke=stroke,
        fill=style.fill or stroke,
        fill_opacity=style.effective_fill_opacity,
        width=style.width,
        point_radius=style.radius,
        marker=style.marker,
        color_by=style.color_by,
        class_colors=tuple((style.class_colors or {}).items()),
    )


@dataclasses.dataclass
class _Entry:
    """An accepted entry; ``instance`` is the widget's, once a draw published it."""

    spec: LayerSpec
    render: RenderLayer
    token: int
    payload: Optional[bytes] = None
    digest: Optional[str] = None
    instance: Optional[int] = None

    @property
    def identity(self) -> tuple:
        return self.render.kind, self.spec.data_hash, self.render.fingerprint


class MapLibreEngine:
    """Keep a MapLibre widget in step with a layer store."""

    def __init__(
        self,
        widget: MapWidget,
        store: LayerStore,
        *,
        gee_interface: Optional[GEEInterface] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        """Bind the engine to a widget and a store, and draw the layers already in the store.

        Args:
            widget: the map to draw on.
            store: the layers to draw.
            gee_interface: the interface that prepares Earth Engine layers and finds
                their bounds.
            loop: the session loop, followed while it is open.

        Raises:
            RuntimeError: when another engine of the store runs on another live loop.
        """
        self.widget = widget
        self.store = store
        self.gee_interface = gee_interface
        self._given = loop
        self._basemap: Optional[Basemap] = None
        self._theme: Literal["light", "dark"] = "light"
        self._controls = Controls()
        self._compare = False
        self._cache: OrderedDict[str, RenderLayer] = OrderedDict()
        self._bounds: OrderedDict[str, BoundsResult] = OrderedDict()
        self._accepted: dict[str, _Entry] = {}
        # per id: request tokens, which added/updated/removed bump, and Layer.token
        self._tokens: dict[str, int] = {}
        self._incarnations: dict[str, int] = {}
        # per id: the request token being prepared or that failed
        self._running: dict[str, tuple[int, Optional[asyncio.Task]]] = {}
        self._failed: dict[str, tuple[int, str]] = {}
        self._tasks: set[asyncio.Task] = set()
        self._handle: Optional[asyncio.Handle] = None
        self._handle_loop: Optional[asyncio.AbstractEventLoop] = None
        self._dirty = False
        self._depth = 0
        self._publishing = False
        # events received off the loop's thread, and the loop a drain is pending on
        self._inbox: list[StoreEvent] = []
        self._inbox_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._warned_thread = False
        self._closed = False
        self._stopped = False

        self._board = status_board(store)
        self._loop = self._resolve()
        self._board.register(self)
        self._unsubscribe = store.subscribe(self._on_event)
        widget.on_status(self._on_widget_status)
        loop = self._loop
        if _off_thread(loop):
            for layer_id in store.ids:
                self._hand_over(loop, StoreEvent("added", layer_id), warn=False)
            self._touch()
        elif self._follow():
            with self._batch():
                for layer_id in store.ids:
                    self._handle_event(StoreEvent("added", layer_id))
                self._mark_dirty()

    # -- public API ---------------------------------------------------------------

    def configure(
        self,
        *,
        basemap: Optional[Basemap] = _KEEP,
        theme: Literal["light", "dark"] = _KEEP,
        controls: Controls = _KEEP,
        compare: bool = _KEEP,
    ) -> None:
        """Change what the map shows besides the layers; the arguments left out stay.

        Args:
            basemap: the basemap, None for none.
            theme: ``"light"`` or ``"dark"``.
            controls: the controls to show.
            compare: whether the map draws a swipe compare, each layer on its side.
        """
        if theme is not _KEEP and theme not in ("light", "dark"):
            raise ValueError(f"theme must be 'light' or 'dark', got {theme!r}")
        if basemap is not _KEEP and basemap is not None and not isinstance(basemap, Basemap):
            raise TypeError(f"basemap must be a Basemap or None, got {basemap!r}")
        if controls is not _KEEP and not isinstance(controls, Controls):
            raise TypeError(f"controls must be Controls, got {controls!r}")
        if compare is not _KEEP and not isinstance(compare, bool):
            raise TypeError(f"compare must be a bool, got {compare!r}")
        if basemap is not _KEEP:
            self._basemap = basemap
        if theme is not _KEEP:
            self._theme = theme
        if controls is not _KEEP:
            self._controls = controls
        if compare is not _KEEP:
            self._compare = compare
        self._touch()

    @property
    def compare(self) -> bool:
        """Whether the map draws a swipe compare."""
        return self._compare

    def put(self, render: RenderLayer) -> None:
        """Seed the render cache, keyed by ``render_hash``.

        Args:
            render: the render to cache.
        """
        self._cache[render.render_hash] = render
        self._cache.move_to_end(render.render_hash)
        while len(self._cache) > _CACHE_SIZE:
            self._cache.popitem(last=False)

    def accepted(self, layer_id: str) -> Optional[tuple[LayerSpec, RenderLayer]]:
        """Return the ``(spec, render)`` the map draws for an id, or None."""
        entry = self._accepted.get(layer_id)
        return None if entry is None else (entry.spec, entry.render)

    def accepted_instance(self, layer_id: str) -> Optional[int]:
        """Return the widget instance the last publish gave an id, or None."""
        entry = self._accepted.get(layer_id)
        return None if entry is None else entry.instance

    def bounds(self, layer_id: str) -> BoundsResult:
        """Return the bounds of a layer, looking those of an Earth Engine render up once.

        Args:
            layer_id: the layer id.

        Returns:
            ``(west, south, east, north)``, or ``"missing"``, ``"preparing"``,
            ``"failed"`` or ``"no_bounds"``.
        """
        known = self._known_bounds(layer_id)
        if not isinstance(known, _Entry):
            return known
        try:
            answer = self.gee_interface.get_bounds(known.render.ee_object)
            return self._bounds_found(known, answer)
        except Exception as exc:
            return self._bounds_failed(known, exc)

    async def bounds_async(self, layer_id: str) -> BoundsResult:
        """Return what :meth:`bounds` does, looking Earth Engine bounds up asynchronously."""
        known = self._known_bounds(layer_id)
        if not isinstance(known, _Entry):
            return known
        try:
            answer = await self.gee_interface.get_bounds_async(known.render.ee_object)
            return self._bounds_found(known, answer)
        except Exception as exc:
            return self._bounds_failed(known, exc)

    def flush(self) -> None:
        """Publish the state now, in place of the draw pending for this tick."""
        if self._closed or self._stopped:
            return
        loop = self._resolve()
        if _off_thread(loop):
            self._dirty = True
            self._call_soon_threadsafe(loop, self.flush)
            return
        if not self._follow():
            return
        if self._handle is not None:
            self._handle.cancel()
            self._handle = self._handle_loop = None
        self._publish()

    async def wait_idle(self) -> None:
        """Wait until no prepare, draw or dirty state is left, work queued meanwhile included."""
        here = asyncio.get_running_loop()
        while not (self._closed or self._stopped):
            if not _off_thread(self._resolve()):
                self._follow()
            loop = self._loop
            tasks = [
                task
                for task in self._tasks
                if not task.done() and (task.get_loop() is here or task.get_loop().is_running())
            ]
            if not (tasks or self._handle or self._dirty or self._inbox):
                return
            if loop is not here and (loop is None or not loop.is_running()):
                return  # no loop that runs could make progress
            if self._dirty and self._handle is None and loop is here:
                self._mark_dirty()
            mine = [task for task in tasks if task.get_loop() is here]
            if mine:
                await asyncio.gather(*mine, return_exceptions=True)
            else:
                await asyncio.sleep(0 if loop is here else 0.01)

    def close(self) -> None:
        """Stop following the store and drop the engine's share of the layer statuses."""
        if self._closed:
            return
        contributed = () if self._stopped else tuple(self._tokens)
        self._closed = True
        self._unsubscribe()
        self.widget.on_status(self._on_widget_status, remove=True)
        if self._handle is not None:
            self._handle.cancel()
        for task in self._tasks:
            if task.get_loop().is_closed():
                continue
            if _off_thread(task.get_loop()):
                self._call_soon_threadsafe(task.get_loop(), task.cancel)
            else:
                task.cancel()
        self._handle = self._handle_loop = None
        self._accepted.clear()
        self._cache.clear()
        self._bounds.clear()
        self._running.clear()
        self._failed.clear()
        self._tasks.clear()
        self._inbox.clear()
        self._board.unregister(self, contributed)

    # -- loops --------------------------------------------------------------------

    def _resolve(self) -> Optional[asyncio.AbstractEventLoop]:
        """The owner loop now: the first open one of the given, the widget's, the running one."""
        for loop in (self._given, self.widget.loop, _running_loop()):
            if loop is not None and not loop.is_closed():
                return loop
        return None

    def _live_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        if self._closed or self._stopped:
            return None
        loop = self._loop
        return None if loop is None or loop.is_closed() else loop

    def _follow(self) -> bool:
        """Adopt the owner loop and take the events handed over; False to schedule nothing."""
        if self._closed or self._stopped:
            return False
        loop = self._resolve()
        if loop is not self._loop:
            if not self._board.compatible(self, loop):
                # Two engines writing one store from two loops would break its single thread.
                self._stopped = True
                log.error(
                    "The engines drawing one layer store must run on one loop; "
                    "this engine stops drawing until it is closed."
                )
                return False
            self._loop = loop
            self._rehome()
        self._take_inbox()
        return True

    def _rehome(self) -> None:
        """Move the work left on a closed loop to the current one."""
        with self._batch():
            for task in self._tasks:
                coro = task.get_coro()
                stranded = task.get_loop().is_closed() and inspect.iscoroutine(coro)
                if stranded and inspect.getcoroutinestate(coro) == inspect.CORO_CREATED:
                    coro.close()  # it never ran: closed, it does not warn when collected
            self._tasks = {task for task in self._tasks if not task.get_loop().is_closed()}
            if self._handle is not None and self._handle_loop.is_closed():
                self._handle = self._handle_loop = None
            # a prepare task of a closed loop never completes
            stuck = [
                layer_id
                for layer_id, (_, task) in self._running.items()
                if task is not None and task.get_loop().is_closed()
            ]
            for layer_id in stuck:
                del self._running[layer_id]
                if layer_id in self.store:
                    self._request(layer_id)
            if self._dirty:
                self._mark_dirty()

    def _call_soon_threadsafe(self, loop: asyncio.AbstractEventLoop, callback, *args) -> None:
        try:
            loop.call_soon_threadsafe(callback, *args)
        except RuntimeError:
            pass  # closed meanwhile: the next schedule finds the work left

    def _hand_over(self, loop: asyncio.AbstractEventLoop, event: StoreEvent, warn=True) -> None:
        if warn and not self._warned_thread:
            self._warned_thread = True
            log.warning(
                "The layer store was written from another thread than its loop's. The map "
                "follows, but the writer must hand its writes to the loop first."
            )
        with self._lock:
            self._inbox.append(event)
            if self._inbox_loop is loop:
                return
            self._inbox_loop = loop
        self._call_soon_threadsafe(loop, self._drain)

    def _drain(self) -> None:
        with self._lock:
            self._inbox_loop = None
        self._follow()

    def _take_inbox(self) -> None:
        with self._lock:
            events, self._inbox = self._inbox, []
        if events:
            with self._batch():
                for event in events:
                    self._handle_event(event)

    # -- events -------------------------------------------------------------------

    def _on_event(self, event: StoreEvent) -> None:
        if event.kind == "status" or self._closed or self._stopped:
            return
        loop = self._resolve()
        if _off_thread(loop):
            self._hand_over(loop, event)
        elif self._follow():
            with self._batch():
                self._handle_event(event)

    def _on_widget_status(self, _status) -> None:
        if self._closed or self._stopped or self._publishing:
            return  # a publish refreshes the statuses after its draw
        loop = self._resolve()
        if _off_thread(loop):
            self._call_soon_threadsafe(loop, self._on_widget_status, None)
        elif self._follow():
            self._refresh_all()

    def _touch(self) -> None:
        """Mark the state dirty, from any thread."""
        if self._closed or self._stopped:
            return
        loop = self._resolve()
        if _off_thread(loop):
            self._dirty = True
            self._call_soon_threadsafe(loop, self._touch)
        elif self._follow():
            self._mark_dirty()

    def _handle_event(self, event: StoreEvent) -> None:
        layer_id = event.layer_id
        if event.kind in ("added", "updated", "removed"):
            self._tokens[layer_id] = self._tokens.get(layer_id, 0) + 1
        if event.kind == "removed":
            self._incarnations[layer_id] = self._incarnations.get(layer_id, 0) + 1
            self._accepted.pop(layer_id, None)
            self._running.pop(layer_id, None)
            self._failed.pop(layer_id, None)
        elif layer_id not in self.store:
            return
        elif event.kind in ("added", "updated"):
            self._request(layer_id)
        self._mark_dirty()

    # -- preparation --------------------------------------------------------------

    def _request(self, layer_id: str) -> None:
        token = self._tokens[layer_id]
        spec = self.store.get(layer_id)
        render = self._cached(spec) or self._restyled(layer_id, spec)
        if render is not None:
            self._running.pop(layer_id, None)
            self.put(render)
            self._offer(layer_id, token, spec, render, fresh=False)
            return

        entry = self._accepted.get(layer_id)
        options = entry.render.prepare_options if entry is not None else {}
        loop = self._loop
        if loop is None:
            self._running[layer_id] = (token, None)
            self._board.refresh(layer_id)
            if self._tokens[layer_id] != token:
                return  # a status subscriber wrote to the layer meanwhile
            try:
                render = prepare_sync(spec, gee_interface=self.gee_interface, **options)
            except Exception as exc:
                self._settle(layer_id, token, spec, error=exc)
            else:
                self._settle(layer_id, token, spec, render=render)
            return
        task = loop.create_task(self._prepare(layer_id, token, spec, options))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        self._running[layer_id] = (token, task)
        self._board.refresh(layer_id)

    async def _prepare(self, layer_id: str, token: int, spec: LayerSpec, options: dict) -> None:
        try:
            render = await prepare(spec, gee_interface=self.gee_interface, **options)
        except Exception as exc:
            self._settle(layer_id, token, spec, error=exc)
        else:
            self._settle(layer_id, token, spec, render=render)

    def _settle(
        self,
        layer_id: str,
        token: int,
        spec: LayerSpec,
        *,
        render: Optional[RenderLayer] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Apply a preparation outcome, unless a newer request for the id superseded it."""
        if self._closed or self._stopped:
            return
        if self._tokens.get(layer_id) != token or layer_id not in self.store:
            return
        running = self._running.get(layer_id)
        if running is not None and running[0] == token:
            del self._running[layer_id]
        with self._batch():
            if error is not None:
                self._reject(layer_id, token, error, expected=isinstance(error, LayerPrepareError))
            else:
                self.put(render)
                self._offer(layer_id, token, spec, render, fresh=True)

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

    def _restyled(self, layer_id: str, spec: LayerSpec) -> Optional[RenderLayer]:
        """Return the accepted vector render under the new style, when only the style changed.

        It shares the accepted render's data, so neither the file nor the cache holds a copy.
        """
        entry = self._accepted.get(layer_id)
        if entry is None or entry.render.kind not in ("geojson", "pmtiles", "raster-xyz"):
            return None
        if entry.spec.source.type != spec.source.type or entry.spec.data_hash != spec.data_hash:
            return None
        try:
            fresh = entry.render.fingerprint == local_fingerprint(spec)
        except OSError:
            fresh = False
        if not fresh:
            return None
        if entry.render.kind == "raster-xyz":
            # an Earth Engine vector: only the parameters sent to Earth Engine change its tiles
            old, new = entry.spec.style, spec.style
            if not (
                isinstance(old, VectorStyle)
                and isinstance(new, VectorStyle)
                and old.to_ee_style_params() == new.to_ee_style_params()
            ):
                return None
            return dataclasses.replace(entry.render, render_hash=spec.render_hash)
        return dataclasses.replace(
            entry.render, render_hash=spec.render_hash, vector_style=spec.style
        )

    def _offer(
        self,
        layer_id: str,
        token: int,
        spec: LayerSpec,
        render: RenderLayer,
        *,
        fresh: bool,
    ) -> None:
        """Accept a settled render once its layer builds under both themes, else reject it.

        A render that shares the accepted entry's data, from the cache or a restyle, takes
        over its GeoJSON bytes and digest.

        Args:
            layer_id: the layer id.
            token: the request token it settles.
            spec: the spec it was prepared from.
            render: the render.
            fresh: whether a prepare just made it, rather than the cache or a restyle.
        """
        previous = self._accepted.get(layer_id)
        incarnation = self._incarnations.get(layer_id, 0)
        changed = previous is not None and previous.identity != (
            render.kind,
            spec.data_hash,
            render.fingerprint,
        )
        if changed or (fresh and render.fingerprint is None):
            incarnation += 1
        candidate = _Entry(spec, render, incarnation)
        if render.kind == "geojson":
            shared = previous is not None and previous.render.data is render.data
            if shared and previous.digest is not None:
                candidate.payload, candidate.digest = previous.payload, previous.digest
            else:
                candidate.payload = _geojson_bytes(render.data)
                candidate.digest = hashlib.sha256(candidate.payload).hexdigest()
        try:
            if render.kind == "geojson" and _style_of(spec).cluster:
                _check_clusterable(render.data)
            for is_dark in (False, True):
                self._layer(layer_id, candidate, is_dark)
        except Exception as exc:
            self._reject(layer_id, token, exc, expected=isinstance(exc, ValueError))
            return
        self._accepted[layer_id] = candidate
        self._incarnations[layer_id] = incarnation
        self._failed.pop(layer_id, None)
        self._mark_dirty()

    def _reject(self, layer_id: str, token: int, error: Exception, *, expected: bool) -> None:
        log.warning(
            "Layer %s cannot be drawn: %s",
            layer_id,
            error,
            exc_info=None if expected else error,
        )
        self._failed[layer_id] = (token, str(error))
        self._board.refresh(layer_id)

    # -- drawing ------------------------------------------------------------------

    @contextlib.contextmanager
    def _batch(self):
        """Hold back the draws of a loopless engine to the end of the outermost batch."""
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
        if self._depth == 0 and self._dirty:
            self._mark_dirty()

    def _mark_dirty(self) -> None:
        """Schedule one draw: at the next tick on a loop, else at once outside a batch."""
        self._dirty = True
        loop = self._loop
        if loop is None:
            if self._depth == 0:
                self._publish()
            return
        if self._handle is not None and self._handle_loop is not loop:
            self._handle.cancel()
            self._handle = None
        if self._handle is None:
            try:
                self._handle = loop.call_soon(self._on_handle)
                self._handle_loop = loop
            except RuntimeError:
                pass  # closed meanwhile: the next schedule draws

    def _on_handle(self) -> None:
        self._handle = self._handle_loop = None
        self._publish()

    def _publish(self) -> None:
        if self._closed or self._stopped:
            return
        if self._publishing:
            self._dirty = True
            return
        self._publishing = True
        self._depth += 1
        try:
            while True:
                self._dirty = False
                self._draw()
                self._refresh_all()
                if not self._dirty or self._loop is not None:
                    break
        finally:
            self._depth -= 1
            self._publishing = False
        if self._dirty:
            self._mark_dirty()

    def _draw(self) -> None:
        is_dark = self._theme == "dark"
        ids = [layer_id for layer_id in self.store.ids if layer_id in self._accepted]
        overlay = [i for i in ids if self._accepted[i].spec.zone == "overlay"]
        data = [i for i in ids if self._accepted[i].spec.zone != "overlay"]
        drawn = [
            (self._accepted[i], self._layer(i, self._accepted[i], is_dark)) for i in overlay + data
        ]
        state = MapState(
            layers=tuple(layer for _, layer in drawn),
            basemap=self._basemap,
            theme=self._theme,
            controls=self._controls,
            compare=self._compare,
        )
        # a draw drops the payloads its state does not hold, a nested one's too
        for entry, _ in drawn:
            if entry.digest is not None and not self.widget.has_payload(entry.digest):
                self.widget.add_payload(entry.payload)
        self.widget.publish(state)
        published = {x["id"]: x for x in self.widget.state.get("layers", ())}
        for entry, layer in drawn:
            x = published.get(layer.id)
            entry.instance = x["instance"] if x is not None and x["token"] == layer.token else None

    def _layer(self, layer_id: str, entry: _Entry, is_dark: bool) -> Layer:
        """Convert an entry to the widget layer; raises ``ValueError`` when it cannot be drawn."""
        spec, render = entry.spec, entry.render
        paint = None
        source: Union[RasterSource, GeoJSONSource, PMTilesSource]
        if render.kind == "raster-xyz":
            url = render.theme_urls[is_dark] if render.theme_urls else render.url
            source = RasterSource(
                tile_urls(url),
                tile_size=render.tile_size,
                bounds=render.bounds,
                # explicit: without a maxzoom MapLibre stops the source at 22
                max_native_zoom=render.max_zoom,
            )
        elif render.kind == "geojson":
            style = _style_of(spec)
            cluster = (
                Cluster(style.cluster_radius, style.cluster_max_zoom) if style.cluster else None
            )
            source = GeoJSONSource(entry.digest, cluster=cluster)
            paint = _paint(spec, is_dark)
        else:
            if not render.source_layer:
                raise ValueError("PMTiles layer needs a source layer")
            if _style_of(spec).cluster:
                raise ValueError("clustering needs a GeoJSON layer; PMTiles cannot be clustered")
            source = PMTilesSource(render.url, render.source_layer)
            paint = _paint(spec, is_dark)
        interaction = None
        if paint is not None:
            style = _style_of(spec)
            interaction = Interaction(popup=_fields(style.popup), tooltip=_fields(style.tooltip))
        view = self.store.view(layer_id)
        return Layer(
            layer_id,
            source,
            token=entry.token,
            zone=spec.zone,
            visible=view.visible,
            opacity=view.opacity,
            side=view.side,
            max_zoom=None,
            paint=paint,
            interaction=interaction,
            attribution=spec.attribution,
        )

    # -- status -------------------------------------------------------------------

    def _status_of(self, layer_id: str) -> Optional[EngineStatus]:
        """The engine's own status of an id, by the first rule that applies."""
        if self._closed or self._stopped:
            return None
        token = self._tokens.get(layer_id)
        running = self._running.get(layer_id)
        if running is not None and running[0] == token:
            return "pending", ""
        failed = self._failed.get(layer_id)
        if failed is not None and failed[0] == token:
            return "error", failed[1]
        entry = self._accepted.get(layer_id)
        if entry is None:
            return "pending", ""
        report = self.widget.layer_status.get(layer_id)
        if (
            report is None
            or entry.instance is None
            or (report.token, report.instance) != (entry.token, entry.instance)
        ):
            return "ready", ""  # no view is mounted, or its report is on another instance
        if report.status == "error":
            return "error", report.error or ""
        return ("pending", "") if report.status == "loading" else ("ready", "")

    def _refresh_all(self) -> None:
        for layer_id in self.store.ids:
            self._board.refresh(layer_id)

    # -- bounds -------------------------------------------------------------------

    def _known_bounds(self, layer_id: str) -> Union[BoundsResult, _Entry]:
        """The bounds known without a lookup, or the entry whose bounds to look up."""
        if layer_id not in self.store:
            return "missing"
        entry = self._accepted.get(layer_id)
        if entry is None:
            failed = self._failed.get(layer_id)
            if failed is not None and failed[0] == self._tokens.get(layer_id):
                return "failed"
            return "preparing"
        render = entry.render
        if render.bounds is not None:
            west, south, east, north = (float(v) for v in render.bounds)
            return west, south, east, north
        if render.ee_object is None:
            return "no_bounds"
        if self.gee_interface is None:
            return "failed"
        cached = self._bounds.get(render.render_hash)
        if cached is None:
            return entry
        self._bounds.move_to_end(render.render_hash)
        return cached

    def _remember_bounds(self, entry: _Entry, result: BoundsResult) -> BoundsResult:
        self._bounds[entry.render.render_hash] = result
        self._bounds.move_to_end(entry.render.render_hash)
        while len(self._bounds) > _CACHE_SIZE:
            self._bounds.popitem(last=False)
        return result

    def _bounds_found(self, entry: _Entry, answer) -> BoundsResult:
        west, south, east, north = (float(v) for v in answer)
        if west <= -179.9 and east >= 179.9 and south <= -89.9 and north >= 89.9:
            return self._remember_bounds(entry, "no_bounds")
        return self._remember_bounds(entry, (west, south, east, north))

    def _bounds_failed(self, entry: _Entry, error: Exception) -> BoundsResult:
        if isinstance(error, ee.EEException) and not _transient(error):
            return self._remember_bounds(entry, "no_bounds")
        log.warning("The bounds of layer %s are unavailable: %s", entry.spec.id, error)
        return "failed"
