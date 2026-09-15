"""Publisher API: Notifier (toast methods) and TaskTracker (context manager)."""

import asyncio
import logging
import time
from typing import Optional

from .bus import NotificationBus
from .state import (
    TaskMilestone,
    TaskStatus,
    Toast,
    ToastType,
    TrackedTask,
)

logger = logging.getLogger(__name__)


class TaskTracker:
    """Context manager for tracking a long-running task with milestones."""

    def __init__(self, bus: NotificationBus, task: TrackedTask):
        """Initialize tracker with a bus reference and task identity."""
        self._bus = bus
        self._task_id = task.id
        self._finished = False

    def step(self, message: str) -> None:
        """Add a named milestone and increment current_step."""
        if self._finished:
            return
        current = self._get_task()
        if current is None:
            return
        milestone = TaskMilestone(message=message)
        self._bus.update_task(
            self._task_id,
            milestones=(*current.milestones, milestone),
            current_step=current.current_step + 1,
            status=TaskStatus.RUNNING,
        )

    def set_progress(self, value: float) -> None:
        """Update continuous progress (0.0-1.0). Does NOT create a milestone."""
        if self._finished:
            return
        self._bus.update_task(self._task_id, progress=value)

    def update(self, title: str) -> None:
        """Update the task title."""
        if self._finished:
            return
        self._bus.update_task(self._task_id, title=title)

    def complete(self, message: Optional[str] = None) -> None:
        """Explicitly mark the task as completed."""
        if self._finished:
            return
        self._finished = True
        changes = {
            "status": TaskStatus.COMPLETED,
            "progress": 1.0,
            "completed_at": time.time(),
        }
        if message:
            current = self._get_task()
            if current:
                changes["milestones"] = (
                    *current.milestones,
                    TaskMilestone(message=message),
                )
        self._bus.update_task(self._task_id, **changes)

    def fail(self, message: str) -> None:
        """Explicitly mark the task as failed."""
        if self._finished:
            return
        self._finished = True
        self._bus.update_task(
            self._task_id,
            status=TaskStatus.FAILED,
            error_message=message,
            completed_at=time.time(),
        )

    def cancel(self) -> None:
        """Explicitly mark the task as cancelled."""
        if self._finished:
            return
        self._finished = True
        self._bus.update_task(
            self._task_id,
            status=TaskStatus.CANCELLED,
            completed_at=time.time(),
        )

    def _get_task(self) -> Optional[TrackedTask]:
        """Get the current task state from the bus."""
        return self._bus.find_task(self._task_id)


class Notifier:
    """Main publisher API for notifications."""

    def __init__(self, bus: NotificationBus):
        """Initialize notifier with a notification bus."""
        self._bus = bus

    def success(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Publish a success toast. ``timeout`` overrides the per-type default."""
        self._bus.add_toast(Toast(message=message, type=ToastType.SUCCESS, timeout=timeout))

    def error(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Publish an error toast. ``timeout`` overrides the per-type default."""
        self._bus.add_toast(Toast(message=message, type=ToastType.ERROR, timeout=timeout))

    def warning(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Publish a warning toast. ``timeout`` overrides the per-type default."""
        self._bus.add_toast(Toast(message=message, type=ToastType.WARNING, timeout=timeout))

    def info(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Publish an info toast. ``timeout`` overrides the per-type default."""
        self._bus.add_toast(Toast(message=message, type=ToastType.INFO, timeout=timeout))

    def cancel(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Publish a cancellation toast (gray). ``timeout`` overrides default."""
        self._bus.add_toast(Toast(message=message, type=ToastType.CANCEL, timeout=timeout))

    def dismiss(self, toast_id: str) -> None:
        """Dismiss a toast by ID."""
        self._bus.remove_toast(toast_id)

    def track(self, title: str, total_steps: Optional[int] = None) -> "_TaskTrackerContextManager":
        """Return a TaskTracker context manager for a long-running task."""
        task = TrackedTask(title=title, total_steps=total_steps)
        self._bus.add_task(task)
        return _TaskTrackerContextManager(self._bus, task)


class _TaskTrackerContextManager(TaskTracker):
    """TaskTracker that also acts as a context manager."""

    def __enter__(self) -> TaskTracker:
        self._bus.update_task(self._task_id, status=TaskStatus.RUNNING)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._finished:
            # Already explicitly completed/failed/cancelled.
            # But if there's an exception AND the task wasn't already
            # FAILED or CANCELLED, override to FAILED so the error is visible.
            if exc_type is not None:
                current = self._get_task()
                if current and current.status not in (
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ):
                    self._bus.update_task(
                        self._task_id,
                        status=TaskStatus.FAILED,
                        error_message=str(exc_val),
                        completed_at=None,
                    )
                    self._bus.add_toast(Toast(message=str(exc_val), type=ToastType.ERROR))
            return False  # Re-raise if exception

        if exc_type is None:
            self._finished = True
            self._bus.update_task(
                self._task_id,
                status=TaskStatus.COMPLETED,
                completed_at=time.time(),
            )
        elif issubclass(exc_type, asyncio.CancelledError):
            self.cancel()
            return False  # Re-raise CancelledError
        else:
            self.fail(str(exc_val))
            # Publish error toast
            self._bus.add_toast(Toast(message=str(exc_val), type=ToastType.ERROR))
            return False  # Re-raise exception

        return False


def _dropped(kind: str, message: str) -> None:
    """Report a notification nothing will display.

    The provider is missing, but the text is not: an error the user never sees
    must still be findable in the server log.
    """
    logger.warning("No NotificationProvider is mounted; %s dropped: %s", kind, message)


class _NoopTaskTracker:
    """TaskTracker that does nothing (used when no provider is mounted)."""

    def step(self, message: str) -> None:
        pass

    def set_progress(self, value: float) -> None:
        pass

    def update(self, title: str) -> None:
        pass

    def complete(self, message: Optional[str] = None) -> None:
        pass

    def fail(self, message: str) -> None:
        """Log the failure: a task nobody tracked still failed."""
        _dropped("task failure", message)

    def cancel(self) -> None:
        pass


class _NoopTaskTrackerContextManager(_NoopTaskTracker):
    """Noop context manager version."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None:
            _dropped("task failure", str(exc_val))
        return False


class NoopNotifier:
    """Notifier that does nothing (used when no provider is mounted).

    Nothing reaches the screen, so every message goes to the log instead. A
    dropped error is the one that matters: without this the app reports a
    failure and looks like it succeeded.
    """

    def success(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Log a success toast that nothing will display."""
        _dropped("success", message)

    def error(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Log an error toast that nothing will display."""
        _dropped("error", message)

    def warning(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Log a warning toast that nothing will display."""
        _dropped("warning", message)

    def info(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Log an info toast that nothing will display."""
        _dropped("info", message)

    def cancel(self, message: str, *, timeout: Optional[float] = None) -> None:
        """Log a cancel toast that nothing will display."""
        _dropped("cancel", message)

    def dismiss(self, toast_id: str) -> None:
        """No-op dismiss: nothing was displayed to dismiss."""

    def track(self, title: str, total_steps: Optional[int] = None):
        """Log the task and return a no-op tracker context manager."""
        _dropped("task", title)
        return _NoopTaskTrackerContextManager()
