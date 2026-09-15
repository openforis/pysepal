"""Centralized notification system for pysepal Solara applications.

Usage::

    from pysepal.solara.notifications import (
        NotificationProvider,  # Place once at app root
        use_notifications,     # Hook for Solara components
        notify,                # Global function for non-component code
        track_task,            # Global task tracking for non-component code
    )
"""

from .globals import notify, track_task
from .hook import use_notifications
from .notifier import NoopNotifier
from .provider import NotificationProvider
from .state import (
    TOAST_TIMEOUT_DEFAULTS,
    TaskMilestone,
    TaskStatus,
    Toast,
    ToastType,
    TrackedTask,
)

__all__ = [
    "NoopNotifier",
    "NotificationProvider",
    "notify",
    "track_task",
    "use_notifications",
    "Toast",
    "ToastType",
    "TaskMilestone",
    "TaskStatus",
    "TrackedTask",
    "TOAST_TIMEOUT_DEFAULTS",
]
