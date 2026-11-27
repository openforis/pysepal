"""Observable store holding the layers of a map, the single source of truth."""

import asyncio
import logging
import threading
import weakref
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Optional, get_args

from mapframe import Side

from .spec import LayerSpec, Legend

log = logging.getLogger(__name__)

_SIDES = get_args(Side)

EventKind = Literal[
    "added", "removed", "updated", "moved", "visibility", "opacity", "side", "status"
]
Status = Literal["pending", "ready", "error"]


def _running_loop() -> Optional[asyncio.AbstractEventLoop]:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _open(loop: Optional[asyncio.AbstractEventLoop]) -> Optional[asyncio.AbstractEventLoop]:
    return loop if loop is not None and not loop.is_closed() else None


def _check_side(side: object) -> None:
    if side not in _SIDES:
        raise ValueError(f"side must be one of {_SIDES}, got {side!r}")


@dataclass(frozen=True)
class StoreEvent:
    """A change notification."""

    kind: EventKind
    layer_id: str


@dataclass
class LayerView:
    """Mutable, non-serialized state of a layer."""

    visible: bool = True
    opacity: float = 1.0
    side: Side = "both"
    status: Status = "pending"
    error: str = ""
    legend: Legend | None = None
    kind: str | None = None


class LayerStore:
    """Ordered collection of layer specs with views, history, events and write guards.

    Index 0 is the top layer. Every write that touches an id bumps its generation, so an
    async writer can ``reserve`` an id before awaiting and pass the token back as
    ``expect_generation``; a newer write makes the stale one a no-op.

    The subscribers run on the store's :attr:`loop`. A write made on another thread, such
    as an ``asyncio.to_thread`` worker, changes the store at once, and its events reach the
    subscribers later on the loop, in order; they read the store as it is then. With no
    loop known, or on the loop, the subscribers run at once.
    """

    def __init__(self) -> None:
        """Create an empty store."""
        self._ids: list[str] = []
        self._history: dict[str, list[LayerSpec]] = {}
        self._views: dict[str, LayerView] = {}
        self._generations: dict[str, int] = {}
        self._reserved: dict[str, str] = {}
        self._subscribers: list[Callable[[StoreEvent], None]] = []
        self._owners: list[weakref.ref] = []
        self._captured: Optional[asyncio.AbstractEventLoop] = None
        # events waiting for the subscribers, and the loop a drain is scheduled on
        self._queue: deque[StoreEvent] = deque()
        self._drain_loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = threading.Lock()
        self._delivering = 0

    def subscribe(self, callback: Callable[[StoreEvent], None]) -> Callable[[], None]:
        """Register ``callback`` and return a function that unregisters it."""
        self._resolve_loop()
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def follow_loop(self, owner: object) -> None:
        """Run the subscribers on ``owner.loop`` while it is open, ahead of the captured loop.

        The owner is held weakly and its ``loop`` read at every event, so an owner that
        adopts a new loop, after a reconnect for instance, takes the store along.

        Args:
            owner: an object with a ``loop`` attribute, such as a map.
        """
        self._owners = [ref for ref in self._owners if ref() is not None]
        self._owners.append(weakref.ref(owner))

    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """The loop the subscribers run on, or None.

        It is the first open loop of the owners given to :meth:`follow_loop`, else the one
        captured: the loop running at the first subscription or write made on one, taken
        again the same way once it closes.
        """
        for ref in self._owners:
            loop = _open(getattr(ref(), "loop", None))
            if loop is not None:
                return loop
        return _open(self._captured)

    @property
    def pending_events(self) -> int:
        """The number of events handed to a running loop that the subscribers have not had yet.

        Events left on a loop that stopped without closing are not counted: nothing delivers
        them until the next write, so a wait on them would never end.
        """
        with self._lock:
            loop = self._drain_loop
            return len(self._queue) if loop is not None and loop.is_running() else 0

    def _resolve_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        loop = self.loop
        if loop is None:
            loop = self._captured = _running_loop()
        return loop

    def _emit(self, kind: EventKind, layer_id: str) -> None:
        event = StoreEvent(kind, layer_id)
        loop = self._resolve_loop()
        if loop is not None and loop.is_running() and _running_loop() is not loop:
            # Off a kernel's thread, as on a pool worker, the widgets a subscriber builds
            # have no kernel and never reach the browser.
            self._hand_over(loop, event)
        elif self._delivering:
            self._deliver(event)  # a subscriber wrote: everyone hears it first, as before
        else:
            with self._lock:
                self._queue.append(event)
            self._drain()

    def _hand_over(self, loop: asyncio.AbstractEventLoop, event: StoreEvent) -> None:
        with self._lock:
            self._queue.append(event)
            if self._drain_loop is loop:
                return
            self._drain_loop = loop
        try:
            loop.call_soon_threadsafe(self._drain)
        except RuntimeError:  # closed meanwhile: the next write delivers the queue
            with self._lock:
                self._drain_loop = None

    def _drain(self) -> None:
        with self._lock:
            self._drain_loop = None
            # Only what is queued now: a later hand-over schedules its own drain, so a
            # writer in a tight loop cannot hold the loop here.
            count = len(self._queue)
        for _ in range(count):
            with self._lock:
                if not self._queue:
                    return
                event = self._queue.popleft()
            self._deliver(event)

    def _deliver(self, event: StoreEvent) -> None:
        self._delivering += 1
        try:
            for callback in list(self._subscribers):
                try:
                    callback(event)
                except Exception:
                    log.exception("Layer store subscriber failed on %s", event)
        finally:
            self._delivering -= 1

    def _bump(self, layer_id: str) -> None:
        # A newer write supersedes any pending reservation for the id.
        self._generations[layer_id] = self.generation(layer_id) + 1
        self._reserved.pop(layer_id, None)

    def generation(self, layer_id: str) -> int:
        """Return the write counter of an id, 0 if it was never touched."""
        return self._generations.get(layer_id, 0)

    def reserve(self, layer_id: str, name: str = "") -> int:
        """Announce an upcoming async write and return its generation token."""
        self._generations[layer_id] = self.generation(layer_id) + 1
        self._reserved[layer_id] = name
        return self._generations[layer_id]

    def reserved(self) -> dict[str, str]:
        """Return the ids reserved but not yet added, as id -> name."""
        return dict(self._reserved)

    def release(self, layer_id: str, generation: int) -> None:
        """Drop a reservation, only if no newer write happened since ``generation``."""
        if self.generation(layer_id) == generation:
            self._reserved.pop(layer_id, None)

    def add(
        self,
        spec: LayerSpec,
        *,
        visible: bool = True,
        opacity: float = 1.0,
        side: Side = "both",
        index: int = 0,
        replace: bool = False,
        expect_generation: int | None = None,
    ) -> str | None:
        """Add a layer, or revise an existing one with ``replace=True``.

        Returns:
            The layer id, or None when ``expect_generation`` was stale.
        """
        layer_id = spec.id
        _check_side(side)
        if expect_generation is not None and expect_generation != self.generation(layer_id):
            return None
        exists = layer_id in self._history
        if exists and not replace:
            raise ValueError(f"Layer {layer_id!r} already exists; pass replace=True.")

        # Deep copies: pydantic's frozen does not freeze nested lists and dicts.
        snapshot = spec.model_copy(deep=True)
        self._bump(layer_id)
        if exists:
            old = self._history[layer_id][-1]
            snapshot = snapshot.model_copy(
                update={"revision": old.revision + 1, "parent": old.render_hash}
            )
            self._history[layer_id].append(snapshot)
            self._emit("updated", layer_id)
            return layer_id

        index = max(0, min(index, len(self._ids)))
        self._ids.insert(index, layer_id)
        self._history[layer_id] = [snapshot]
        self._views[layer_id] = LayerView(
            visible=visible, opacity=min(max(opacity, 0.0), 1.0), side=side
        )
        self._emit("added", layer_id)
        return layer_id

    def remove(self, layer_id: str, *, missing_ok: bool = False) -> None:
        """Remove a layer; a missing id raises ``KeyError`` unless ``missing_ok``."""
        if layer_id not in self._history:
            if not missing_ok:
                raise KeyError(layer_id)
            self._bump(layer_id)
            return
        self._ids.remove(layer_id)
        del self._history[layer_id]
        del self._views[layer_id]
        self._bump(layer_id)
        self._emit("removed", layer_id)

    def clear(self) -> None:
        """Remove every layer and invalidate every reservation."""
        for layer_id in list(self._ids):
            self.remove(layer_id)
        for layer_id in list(self._generations):
            self._bump(layer_id)
        self._reserved.clear()

    def update(
        self, layer_id: str, spec: LayerSpec, *, expect_generation: int | None = None
    ) -> LayerSpec | None:
        """Replace the spec of an existing layer, keeping its slot and view.

        Returns:
            A copy of the stored spec, or None when ``expect_generation`` was stale.
        """
        if spec.id != layer_id:
            raise ValueError(f"Spec id {spec.id!r} does not match layer {layer_id!r}.")
        if layer_id not in self._history:
            raise KeyError(layer_id)
        if expect_generation is not None and expect_generation != self.generation(layer_id):
            return None

        snapshot = spec.model_copy(deep=True)
        history = self._history[layer_id]
        old = history[-1]
        changed = (
            snapshot.render_hash != old.render_hash
            or snapshot.legend != old.legend
            or snapshot.name != old.name
            or snapshot.zone != old.zone
            or snapshot.attribution != old.attribution
        )
        self._bump(layer_id)
        if changed:
            history.append(snapshot)
            self._emit("updated", layer_id)
        else:
            history[-1] = snapshot
        return snapshot.model_copy(deep=True)

    def restyle(self, layer_id: str, **changes: Any) -> LayerSpec:
        """Apply style ``changes`` to a layer, validating them against its style model.

        ``palette`` and ``colormap`` are one choice: setting one clears the other unless the
        changes mention both.
        """
        spec = self.get(layer_id)
        merged = {**spec.style.model_dump(), **changes}
        for chosen, other in (("palette", "colormap"), ("colormap", "palette")):
            if changes.get(chosen) is not None and other not in changes:
                merged[other] = None
        style = type(spec.style).model_validate(merged)
        result = self.update(layer_id, spec.revise(style=style))
        assert result is not None  # no expect_generation given
        return result

    def move(self, layer_id: str, to: int) -> None:
        """Move a layer to position ``to`` (0 is the top), clamped to the valid range."""
        current = self._ids.index(layer_id)
        to = max(0, min(to, len(self._ids) - 1))
        if to == current:
            return
        self._ids.insert(to, self._ids.pop(current))
        self._emit("moved", layer_id)

    def set_visible(self, layer_id: str, visible: bool) -> None:
        """Show or hide a layer."""
        view = self.view(layer_id)
        if view.visible == visible:
            return
        view.visible = visible
        self._emit("visibility", layer_id)

    def set_opacity(self, layer_id: str, opacity: float) -> None:
        """Set the opacity, clamped to [0, 1]."""
        view = self.view(layer_id)
        opacity = min(max(float(opacity), 0.0), 1.0)
        if view.opacity == opacity:
            return
        view.opacity = opacity
        self._emit("opacity", layer_id)

    def set_side(self, layer_id: str, side: Side) -> None:
        """Set which half of a compare map draws the layer; ignored outside compare."""
        _check_side(side)
        view = self.view(layer_id)
        if view.side == side:
            return
        view.side = side
        self._emit("side", layer_id)

    def set_status(
        self,
        layer_id: str,
        status: Status,
        *,
        error: str = "",
        legend: Legend | None = None,
        kind: str | None = None,
    ) -> None:
        """Record the render status of a layer."""
        view = self.view(layer_id)
        new = (status, error, legend, kind)
        if new == (view.status, view.error, view.legend, view.kind):
            return
        view.status, view.error, view.legend, view.kind = new
        self._emit("status", layer_id)

    def get(self, layer_id: str) -> LayerSpec:
        """Return a copy of the current spec."""
        return self._history[layer_id][-1].model_copy(deep=True)

    def view(self, layer_id: str) -> LayerView:
        """Return the live view of a layer."""
        return self._views[layer_id]

    def history(self, layer_id: str) -> list[LayerSpec]:
        """Return copies of every revision, oldest first."""
        return [spec.model_copy(deep=True) for spec in self._history[layer_id]]

    @property
    def ids(self) -> list[str]:
        """Layer ids, top first."""
        return list(self._ids)

    def drawing_order(self) -> list[str]:
        """Overlay ids, then data ids, each in store order (top first)."""
        overlay = [i for i in self._ids if self._history[i][-1].zone == "overlay"]
        data = [i for i in self._ids if self._history[i][-1].zone != "overlay"]
        return overlay + data

    def specs(self) -> list[LayerSpec]:
        """Return copies of the current specs, top first."""
        return [self.get(layer_id) for layer_id in self._ids]

    def __contains__(self, layer_id: object) -> bool:
        """Return whether a layer id is in the store."""
        return layer_id in self._history

    def __len__(self) -> int:
        """Return the number of layers."""
        return len(self._ids)
