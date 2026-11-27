"""The status of a store's layers, reduced over every engine that draws the store.

Each engine computes its own status per id; the store's one
:class:`LayerStatusBoard` reduces them and writes ``LayerStore.set_status``. The
board holds the store and its engines weakly: it lives in a module-level
``WeakKeyDictionary`` keyed by the store, so a strong reference would keep the
store alive forever.
"""

import asyncio
import threading
import weakref
from typing import Literal, Optional, Protocol

from pysepal.layers import LayerSpec, LayerStore, RenderLayer

__all__ = ["EngineStatus", "LayerStatusBoard", "StatusSource", "status_board"]

EngineStatus = tuple[Literal["pending", "ready", "error"], str]
"an engine's status of one id, and its error message"


class StatusSource(Protocol):
    """What the board reads from each engine registered with it."""

    def _status_of(self, layer_id: str) -> Optional[EngineStatus]:
        """The engine's status of an id, or None while it has no say (closed or stopped)."""

    def _live_loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """The engine's loop if it is live and the engine still schedules, else None."""

    def accepted(self, layer_id: str) -> Optional[tuple[LayerSpec, RenderLayer]]:
        """The entry the engine draws for an id."""


class LayerStatusBoard:
    """Reduce the statuses that the engines of one store give each layer.

    Across the engines, in registration order: an error if any says error, with
    the first one's message; else pending if any says pending; else ready. The
    legend and kind come from the first engine that draws the id, so the result
    does not depend on which engine settled first.
    """

    def __init__(self, store: LayerStore) -> None:
        """Start a board with no engine.

        Args:
            store: the store whose statuses the board writes.
        """
        self._store = weakref.ref(store)
        self._engines: list[weakref.ref] = []

    def engines(self) -> list[StatusSource]:
        """The live registered engines, in registration order."""
        return [engine for ref in self._engines if (engine := ref()) is not None]

    def compatible(self, engine: StatusSource, loop: Optional[asyncio.AbstractEventLoop]) -> bool:
        """Whether ``engine`` may run on ``loop`` next to the other engines of the store.

        Engines sharing a store must run on one live loop: a live ``loop`` that
        differs from another engine's live loop is not compatible.
        """
        if loop is None or loop.is_closed():
            return True
        for other in self.engines():
            theirs = None if other is engine else other._live_loop()
            if theirs is not None and theirs is not loop:
                return False
        return True

    def register(self, engine: StatusSource) -> None:
        """Add an engine after the others.

        Raises:
            RuntimeError: when its loop is live and another engine of the store runs
                on another live loop. Two kernels cannot share a store.
        """
        if not self.compatible(engine, engine._live_loop()):
            raise RuntimeError(
                "The engines drawing one layer store must run on one loop: "
                "two kernels cannot share a store."
            )
        self._engines.append(weakref.ref(engine))

    def unregister(self, engine: StatusSource, layer_ids=()) -> None:
        """Drop an engine and recompute the ids it contributed to.

        Args:
            engine: the engine to drop.
            layer_ids: the ids whose status to recompute without it.
        """
        self._engines = [ref for ref in self._engines if ref() not in (None, engine)]
        for layer_id in layer_ids:
            self.refresh(layer_id)

    def refresh(self, layer_id: str) -> None:
        """Write the reduced status of an id to the store; no engine with a say writes nothing."""
        store = self._store()
        if store is None or layer_id not in store:
            return
        statuses: list[EngineStatus] = []
        drawn = None
        for engine in self.engines():
            status = engine._status_of(layer_id)
            if status is None:
                continue
            statuses.append(status)
            if drawn is None:
                drawn = engine.accepted(layer_id)
        if not statuses:
            return
        legend, kind = (None, None) if drawn is None else (drawn[1].legend, drawn[1].kind)
        errors = [message for status, message in statuses if status == "error"]
        if errors:
            store.set_status(layer_id, "error", error=errors[0], legend=legend, kind=kind)
        elif any(status == "pending" for status, _ in statuses):
            store.set_status(layer_id, "pending", legend=legend, kind=kind)
        else:
            store.set_status(layer_id, "ready", legend=legend, kind=kind)


_boards: "weakref.WeakKeyDictionary[LayerStore, LayerStatusBoard]" = weakref.WeakKeyDictionary()
_boards_lock = threading.Lock()


def status_board(store: LayerStore) -> LayerStatusBoard:
    """Return the board of a store, made on first use."""
    with _boards_lock:
        board = _boards.get(store)
        if board is None:
            board = _boards[store] = LayerStatusBoard(store)
        return board
