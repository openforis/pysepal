"""Notification state model: dataclasses, enums, and defaults."""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ToastType(Enum):
    """Type of toast notification, determines color and auto-dismiss behavior."""

    SUCCESS = "success"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CANCEL = "cancel"


TOAST_TIMEOUT_DEFAULTS: dict[ToastType, Optional[float]] = {
    ToastType.SUCCESS: 3.0,
    ToastType.INFO: 3.0,
    ToastType.WARNING: 3.0,
    ToastType.ERROR: 3.0,
    ToastType.CANCEL: 3.0,
}


class TaskStatus(Enum):
    """Lifecycle status of a tracked task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Toast:
    """An ephemeral notification message."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    message: str = ""
    type: ToastType = ToastType.INFO
    created_at: float = field(default_factory=time.time)
    timeout: Optional[float] = None
    count: int = 1

    def effective_timeout(self) -> Optional[float]:
        """Return the timeout, falling back to the type default."""
        if self.timeout is not None:
            return self.timeout
        return TOAST_TIMEOUT_DEFAULTS.get(self.type)


@dataclass(frozen=True)
class TaskMilestone:
    """A discrete named step in a task's execution."""

    message: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TrackedTask:
    """A long-running task being tracked in the progress panel."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    status: TaskStatus = TaskStatus.PENDING
    milestones: tuple[TaskMilestone, ...] = ()
    progress: Optional[float] = None
    total_steps: Optional[int] = None
    current_step: int = 0
    created_at: float = field(default_factory=time.time)
    error_message: Optional[str] = None
    completed_at: Optional[float] = None
    progress_detail: Optional[str] = None
