"""Observable store holding the layers of a map, the single source of truth."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from .spec import LayerSpec, Legend

log = logging.getLogger(__name__)

EventKind = Literal["added", "removed", "updated", "moved", "visibility", "opacity", "status"]
Status = Literal["pending", "ready", "error"]


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
    status: Status = "pending"
    error: str = ""
    legend: Legend | None = None
    kind: str | None = None


class LayerStore:
    """Ordered collection of layer specs with views, history, events and write guards.

    Index 0 is the top layer. Every write that touches an id bumps its generation, so an
    async writer can ``reserve`` an id before awaiting and pass the token back as
    ``expect_generation``; a newer write makes the stale one a no-op.
    """

    def __init__(self) -> None:
        """Create an empty store."""
        self._ids: list[str] = []
        self._history: dict[str, list[LayerSpec]] = {}
        self._views: dict[str, LayerView] = {}
        self._generations: dict[str, int] = {}
        self._reserved: dict[str, str] = {}
        self._subscribers: list[Callable[[StoreEvent], None]] = []

    def subscribe(self, callback: Callable[[StoreEvent], None]) -> Callable[[], None]:
        """Register ``callback`` and return a function that unregisters it."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def _emit(self, kind: EventKind, layer_id: str) -> None:
        event = StoreEvent(kind, layer_id)
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                log.exception("Layer store subscriber failed on %s", event)

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
        index: int = 0,
        replace: bool = False,
        expect_generation: int | None = None,
    ) -> str | None:
        """Add a layer, or revise an existing one with ``replace=True``.

        Returns:
            The layer id, or None when ``expect_generation`` was stale.
        """
        layer_id = spec.id
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
        self._views[layer_id] = LayerView(visible=visible, opacity=min(max(opacity, 0.0), 1.0))
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

    def specs(self) -> list[LayerSpec]:
        """Return copies of the current specs, top first."""
        return [self.get(layer_id) for layer_id in self._ids]

    def __contains__(self, layer_id: object) -> bool:
        """Return whether a layer id is in the store."""
        return layer_id in self._history

    def __len__(self) -> int:
        """Return the number of layers."""
        return len(self._ids)
