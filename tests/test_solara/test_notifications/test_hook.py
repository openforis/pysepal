"""Tests for use_notifications hook and bus resolution."""

import logging

import pytest

from pysepal.solara.errors import NotificationProviderError
from pysepal.solara.notifications.bus import (
    NotificationBus,
)
from pysepal.solara.notifications.hook import use_notifications_from_bus
from pysepal.solara.notifications.notifier import NoopNotifier, Notifier
from pysepal.solara.notifications.state import ToastType


def test_use_notifications_from_bus_returns_notifier_with_bus():
    bus = NotificationBus()
    notifier = use_notifications_from_bus(bus)
    assert isinstance(notifier, Notifier)


def test_resolving_without_a_bus_is_an_error():
    """A missing provider is a bug in the app; it must not degrade quietly."""
    with pytest.raises(NotificationProviderError, match="NotificationProvider"):
        use_notifications_from_bus(None)


def test_a_component_can_declare_that_it_runs_without_a_provider():
    """Components published for reuse render standalone; opting out is explicit."""
    notifier = use_notifications_from_bus(None, required=False)
    assert isinstance(notifier, NoopNotifier)


def test_use_notifications_from_bus_publishes_to_bus():
    bus = NotificationBus()
    notifier = use_notifications_from_bus(bus)
    notifier.success("hello")
    assert len(bus.toasts.value) == 1
    assert bus.toasts.value[0].type == ToastType.SUCCESS


def test_a_dropped_message_still_reaches_the_log(caplog):
    """Dropping the provider must not drop the text of the message."""
    notifier = use_notifications_from_bus(None, required=False)
    with caplog.at_level(logging.WARNING, logger="pysepal.solara.notifications.notifier"):
        notifier.error("the export failed")

    assert "the export failed" in caplog.text


def test_a_dropped_task_still_reaches_the_log(caplog):
    """A tracked task that reports nothing must still say so once."""
    notifier = use_notifications_from_bus(None, required=False)
    with caplog.at_level(logging.WARNING, logger="pysepal.solara.notifications.notifier"):
        with notifier.track("Exporting", total_steps=2) as task:
            task.step("Preparing")

    assert "Exporting" in caplog.text
