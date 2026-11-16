"""Tests for Notifier (toast publishing) and TaskTracker (context manager)."""

import asyncio

import pytest

from pysepal.solara.notifications.bus import NotificationBus
from pysepal.solara.notifications.notifier import Notifier
from pysepal.solara.notifications.state import TaskStatus, ToastType


@pytest.fixture
def bus():
    return NotificationBus()


@pytest.fixture
def notifier(bus):
    return Notifier(bus)


@pytest.mark.parametrize(
    "method,expected_type",
    [
        ("success", ToastType.SUCCESS),
        ("error", ToastType.ERROR),
        ("warning", ToastType.WARNING),
        ("info", ToastType.INFO),
    ],
)
def test_notifier_toast_types(bus, notifier, method, expected_type):
    getattr(notifier, method)("msg")
    assert bus.toasts.value[0].type == expected_type


def test_notifier_dismiss(bus, notifier):
    notifier.success("msg")
    notifier.dismiss(bus.toasts.value[0].id)
    assert len(bus.toasts.value) == 0


def test_track_lifecycle(bus, notifier):
    with notifier.track("Processing", total_steps=3) as task:
        assert bus.tasks.value[0].status == TaskStatus.RUNNING
        assert bus.tasks.value[0].total_steps == 3
        task.step("Step 1")
        task.step("Step 2")
        task.set_progress(0.5)
    t = bus.tasks.value[0]
    assert t.status == TaskStatus.COMPLETED
    assert len(t.milestones) == 2
    assert t.current_step == 2
    assert t.progress == 0.5
    assert t.completed_at is not None


def test_set_progress_publishes_value_and_detail(bus, notifier):
    """Both reach the task and the browser payload; neither writes the log."""
    from pysepal.solara.notifications.notification_ui import (
        _serialize_tasks_from_list,
    )

    with notifier.track("Downloading") as task:
        task.set_progress(0.33, detail="tile 10/30")
        t = bus.tasks.value[0]
        data = _serialize_tasks_from_list(bus.tasks.value)
    assert (t.progress, t.progress_detail, t.milestones) == (0.33, "tile 10/30", ())
    assert (data[0]["progress"], data[0]["progressDetail"]) == (0.33, "tile 10/30")


def test_set_progress_without_detail_clears_stale_detail(bus, notifier):
    """A plain set_progress must not leave an outdated detail string behind."""
    with notifier.track("Downloading") as task:
        task.set_progress(0.33, detail="tile 10/30")
        task.set_progress(0.5)
        assert bus.tasks.value[0].progress_detail is None


def test_set_progress_none_resets_to_indeterminate(bus, notifier):
    """Per-item runs reset the ring between items by publishing None."""
    with notifier.track("Downloading") as task:
        task.set_progress(0.9, detail="tile 27/30")
        task.set_progress(None)
        t = bus.tasks.value[0]
        assert (t.progress, t.progress_detail) == (None, None)


def test_set_progress_none_with_detail_keeps_detail(bus, notifier):
    """An indeterminate task can still carry a detail (e.g. a wait reason)."""
    with notifier.track("Downloading") as task:
        task.set_progress(None, detail="waiting for memory")
        t = bus.tasks.value[0]
        assert (t.progress, t.progress_detail) == (None, "waiting for memory")


@pytest.mark.parametrize(
    "value,expected",
    [(1.5, 1.0), (-0.2, 0.0), (float("inf"), 1.0), (float("nan"), None), (1, 1.0)],
)
def test_set_progress_clamps_to_a_fraction(bus, notifier, value, expected):
    """Out-of-range values would show "150%"; NaN is invalid JSON on the wire."""
    with notifier.track("Downloading") as task:
        task.set_progress(value)
        assert bus.tasks.value[0].progress == expected


def test_step_clears_the_progress_detail(bus, notifier):
    """A step ends the item the detail described; a stale wait reason must not hide it."""
    with notifier.track("Downloading") as task:
        task.set_progress(None, detail="waiting…")
        task.step("Started")
        t = bus.tasks.value[0]
        assert (t.progress_detail, t.milestones[-1].message) == (None, "Started")


def test_track_explicit_fail(bus, notifier):
    with notifier.track("Processing") as task:
        task.fail("broke")
    t = bus.tasks.value[0]
    assert t.status == TaskStatus.FAILED
    assert t.error_message == "broke"
    assert t.completed_at is not None


def test_track_explicit_cancel(bus, notifier):
    with notifier.track("Processing") as task:
        task.cancel()
    assert bus.tasks.value[0].status == TaskStatus.CANCELLED
    assert bus.tasks.value[0].completed_at is not None


def test_track_exception_marks_failed_and_publishes_error_toast(bus, notifier):
    with pytest.raises(ValueError, match="boom"):
        with notifier.track("Processing") as task:
            task.step("Step 1")
            raise ValueError("boom")
    t = bus.tasks.value[0]
    assert t.status == TaskStatus.FAILED
    assert t.error_message == "boom"
    assert len(t.milestones) == 1
    assert len(bus.toasts.value) == 1
    assert bus.toasts.value[0].type == ToastType.ERROR


def test_track_cancelled_error_maps_to_cancelled_status(bus, notifier):
    with pytest.raises(asyncio.CancelledError):
        with notifier.track("Processing"):
            raise asyncio.CancelledError()
    assert bus.tasks.value[0].status == TaskStatus.CANCELLED
    assert len(bus.toasts.value) == 0


def test_track_exception_after_explicit_complete_overrides_to_failed(bus, notifier):
    with pytest.raises(RuntimeError):
        with notifier.track("Processing") as task:
            task.complete()
            raise RuntimeError("late error")
    assert bus.tasks.value[0].status == TaskStatus.FAILED
