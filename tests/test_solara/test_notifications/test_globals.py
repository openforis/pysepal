"""Tests for global notify() and track_task() functions."""

import logging
from unittest.mock import patch

import pytest

from pysepal import _scope_registry as scope_registry
from pysepal.solara.notifications.bus import _refcounts, _registry
from pysepal.solara.notifications.state import TaskStatus, ToastType


@pytest.fixture
def clean_buses():
    _registry.clear()
    _refcounts.clear()
    yield
    _registry.clear()
    _refcounts.clear()


@patch.object(scope_registry, "current_scope_id", return_value="k1")
def test_notify_publishes_toast_and_defaults_to_info(mock_scope, clean_buses):
    from pysepal.solara.notifications.bus import create_bus
    from pysepal.solara.notifications.globals import notify

    bus = create_bus()
    notify("hello", type_="success")
    notify("plain")

    assert [t.message for t in bus.toasts.value] == ["hello", "plain"]
    assert bus.toasts.value[0].type == ToastType.SUCCESS
    assert bus.toasts.value[1].type == ToastType.INFO


def test_notify_without_provider_logs_warning(caplog, clean_buses):
    from pysepal.solara.notifications.globals import notify

    with caplog.at_level(logging.WARNING):
        notify("hello", type_="error")
    assert "NotificationProvider" in caplog.text


@patch.object(scope_registry, "current_scope_id", return_value="k1")
def test_track_task_context_manager(mock_scope, clean_buses):
    from pysepal.solara.notifications.bus import create_bus
    from pysepal.solara.notifications.globals import track_task

    bus = create_bus()
    with track_task("Processing", total_steps=2) as task:
        task.step("Step 1")
        task.set_progress(0.5)
    assert len(bus.tasks.value) == 1
    assert bus.tasks.value[0].status == TaskStatus.COMPLETED


def test_track_task_without_provider_is_noop(clean_buses):
    from pysepal.solara.notifications.globals import track_task

    # Should not raise
    with track_task("Processing") as task:
        task.step("Step 1")
