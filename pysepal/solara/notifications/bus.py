"""Scope-keyed notification bus: state management and registry."""

import logging
import threading
from dataclasses import replace
from typing import Dict, Optional

import solara

from pysepal._scope_registry import ScopeRegistry

from .state import Toast, ToastType, TrackedTask

logger = logging.getLogger(__name__)

MAX_TOAST_QUEUE = 20
MAX_TASK_HISTORY = 50
DEDUP_WINDOW_SECONDS = 2.0


class NotificationBus:
    """Owns notification state for a single runtime scope.

    All mutations produce new list copies (never mutate in place).
    Thread-safe via internal lock.
    """

    def __init__(self):
        """Initialize reactive state containers and thread lock."""
        self.toasts: solara.Reactive[list[Toast]] = solara.reactive([])
        self.tasks: solara.Reactive[list[TrackedTask]] = solara.reactive([])
        # Reentrant because solara fires subscribers synchronously inside the
        # assignment to ``.value``, so every subscriber runs while the mutation
        # that notified it still holds this lock.
        self._lock = threading.RLock()
        # The reactives are a published mirror. These are the state a mutation
        # reads and writes, and holding the two apart is what lets a
        # subscriber's own mutation be deferred without it reading a stale list.
        self._toasts: list[Toast] = []
        self._tasks: list[TrackedTask] = []
        self._published_toasts: list[Toast] = self._toasts
        self._published_tasks: list[TrackedTask] = self._tasks
        self._publishing = False

    def _publish(self) -> None:
        """Push pending state onto the reactives, one dispatch at a time.

        A subscriber that mutates the bus must not start a second dispatch:
        the nested one would hand the newer list to whichever subscribers it
        reached, and the dispatch already running would then resume and hand
        its own, now stale, list to the ones it had not reached yet. A UI
        subscriber could end on the older list and hide a toast until some
        later, unrelated update.

        Such a mutation therefore only writes the state above and returns
        here; the dispatch in progress publishes it on its next turn. The same
        turn absorbs another thread's mutation, so two threads cannot publish
        out of order either.
        """
        with self._lock:
            if self._publishing:
                return
            self._publishing = True
        try:
            while True:
                with self._lock:
                    toasts, tasks = self._toasts, self._tasks
                    toasts_changed = toasts is not self._published_toasts
                    tasks_changed = tasks is not self._published_tasks
                    if not (toasts_changed or tasks_changed):
                        return
                    self._published_toasts = toasts
                    self._published_tasks = tasks
                # Outside the lock: these fire subscribers, and another thread
                # has to be able to queue its own mutation while they run.
                if toasts_changed:
                    self.toasts.value = toasts
                if tasks_changed:
                    self.tasks.value = tasks
        finally:
            with self._lock:
                self._publishing = False

    @staticmethod
    def _with_toast(current: list[Toast], toast: Toast) -> list[Toast]:
        """Return ``current`` plus ``toast``, applying dedup and queue limits.

        Error toasts replace previous errors: only the latest error is kept.
        """
        if toast.type == ToastType.ERROR:
            current = [t for t in current if t.type != ToastType.ERROR]
            current.append(toast)
            return current[-MAX_TOAST_QUEUE:]

        for i, existing in enumerate(current):
            if (
                existing.message == toast.message
                and existing.type == toast.type
                and (toast.created_at - existing.created_at) < DEDUP_WINDOW_SECONDS
            ):
                # Refresh the toast identity/timestamp so the frontend resets
                # its dismiss timer and progress bar on repeated notifications
                # instead of expiring relative to the first of the burst.
                current[i] = replace(
                    existing,
                    id=toast.id,
                    created_at=toast.created_at,
                    timeout=toast.timeout,
                    count=existing.count + 1,
                )
                return current

        current.append(toast)
        if len(current) > MAX_TOAST_QUEUE:
            # Drop oldest non-errors first, then oldest errors.
            errors = [t for t in current if t.type == ToastType.ERROR][-MAX_TOAST_QUEUE:]
            keep_non_errors = max(0, MAX_TOAST_QUEUE - len(errors))
            non_errors = [t for t in current if t.type != ToastType.ERROR]
            non_errors = non_errors[-keep_non_errors:] if keep_non_errors else []
            current = errors + non_errors
        return current

    def add_toast(self, toast: Toast) -> None:
        """Add a toast, applying dedup and queue limit rules."""
        with self._lock:
            self._toasts = self._with_toast(list(self._toasts), toast)
        self._publish()

    def remove_toast(self, toast_id: str) -> None:
        """Remove a toast by ID."""
        with self._lock:
            self._toasts = [t for t in self._toasts if t.id != toast_id]
        self._publish()

    def add_task(self, task: TrackedTask) -> None:
        """Add a tracked task. Prunes oldest finished tasks beyond MAX_TASK_HISTORY."""
        with self._lock:
            current = [*self._tasks, task]
            if len(current) > MAX_TASK_HISTORY:
                # Keep running/pending tasks, prune oldest finished
                active = [t for t in current if t.status.value in ("running", "pending")]
                finished = [t for t in current if t.status.value not in ("running", "pending")]
                finished = finished[-(MAX_TASK_HISTORY - len(active)) :]
                current = active + finished
            self._tasks = current
        self._publish()

    def update_task(self, task_id: str, **changes) -> None:
        """Update a tracked task by ID. Unknown IDs are silently ignored."""
        with self._lock:
            self._tasks = [replace(t, **changes) if t.id == task_id else t for t in self._tasks]
        self._publish()

    def remove_task(self, task_id: str) -> None:
        """Remove a tracked task by ID."""
        with self._lock:
            self._tasks = [t for t in self._tasks if t.id != task_id]
        self._publish()

    def find_task(self, task_id: str) -> Optional[TrackedTask]:
        """Return a tracked task by ID, reading the state a mutation would.

        Not ``tasks.value``: that mirror lags by one turn while a deferred
        publication is in flight, and a tracker stepping from inside a
        subscriber would compute its update from the older list.
        """
        with self._lock:
            return next((t for t in self._tasks if t.id == task_id), None)


# --- Scope-keyed bus registry ---

_registry: ScopeRegistry[NotificationBus] = ScopeRegistry("NotificationBus")

# Refcounting is this module's lifetime policy, not the registry's -- other
# consumers of ScopeRegistry drop a scope on its first release. Every read and
# write below happens under that scope's ``scope_lock``.
_refcounts: Dict[str, int] = {}


def get_current_bus() -> Optional[NotificationBus]:
    """Return the current scope's NotificationBus, or None when none exists.

    No ``try``/``except`` on purpose. Every *runtime* shape this can meet --
    including a kernel with no usable connection file -- is absorbed by
    :func:`~pysepal._runtime_context.resolve_scope_id` and resolves to
    the process scope, so anything still raising here is a genuine bug and
    must not be hidden behind a ``None`` return.

    Returns:
        The scope's bus, or None.
    """
    return _registry.get()


def create_bus() -> NotificationBus:
    """Get or create the current scope's NotificationBus.

    Reuses an existing bus and takes a second reference, so a remount or a
    double-mount of ``NotificationProvider`` does not invalidate active
    notifiers.

    Returns:
        The scope's bus.
    """
    scope_id = _registry.resolve()
    with _registry.scope_lock(scope_id):
        bus = _registry.get(scope_id)
        if bus is None:
            bus = NotificationBus()
            _registry.set(bus, scope_id=scope_id)
            _refcounts[scope_id] = 1
            logger.debug(f"Created NotificationBus for scope {scope_id}")
        else:
            _refcounts[scope_id] = _refcounts.get(scope_id, 1) + 1
            logger.debug(
                f"Reusing NotificationBus for scope {scope_id} "
                f"(refcount={_refcounts[scope_id]})"
            )
        return bus


def cleanup_bus() -> None:
    """Drop one reference to the current scope's bus; remove it at zero."""
    scope_id = _registry.resolve()
    with _registry.scope_lock(scope_id):
        count = _refcounts.get(scope_id, 0)
        if count > 1:
            _refcounts[scope_id] = count - 1
            logger.debug(
                f"Released NotificationBus for scope {scope_id} "
                f"(refcount={_refcounts[scope_id]})"
            )
            return
        _refcounts.pop(scope_id, None)
        _registry.pop(scope_id)
        logger.debug(f"Cleaned up NotificationBus for scope {scope_id}")
