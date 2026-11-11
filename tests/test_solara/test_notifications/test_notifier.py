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


def test_rerunning_a_failed_task_closes_its_error_toast(bus, notifier):
    with pytest.raises(RuntimeError):
        with notifier.track("Processing"):
            raise RuntimeError("boom")
    assert [t.type for t in bus.toasts.value] == [ToastType.ERROR]

    notifier.track("Processing")

    assert bus.toasts.value == []
