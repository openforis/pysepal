"""Tests for use_notifications hook and bus resolution."""

import logging

import pytest

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


def test_use_notifications_from_bus_returns_noop_without_bus():
    notifier = use_notifications_from_bus(None)
    assert isinstance(notifier, NoopNotifier)


def test_use_notifications_from_bus_publishes_to_bus():
    bus = NotificationBus()
    notifier = use_notifications_from_bus(bus)
    notifier.success("hello")
    assert len(bus.toasts.value) == 1
    assert bus.toasts.value[0].type == ToastType.SUCCESS


def test_resolving_without_a_bus_warns_that_no_provider_is_mounted():
    """A missing provider is misconfiguration, and it silences the error channel.

    Every ``.error()`` an app reports goes nowhere, so the app looks like
    nothing ever fails. That is the one thing this subsystem must not do
    quietly.
    """
    with pytest.warns(UserWarning, match="NotificationProvider"):
        use_notifications_from_bus(None)


def test_a_dropped_message_still_reaches_the_log(caplog):
    """Dropping the provider must not drop the text of the message."""
    notifier = use_notifications_from_bus(None)
    with caplog.at_level(logging.WARNING, logger="pysepal.solara.notifications.notifier"):
        notifier.error("the export failed")

    assert "the export failed" in caplog.text


def test_a_dropped_task_still_reaches_the_log(caplog):
    """A tracked task that reports nothing must still say so once."""
    notifier = use_notifications_from_bus(None)
    with caplog.at_level(logging.WARNING, logger="pysepal.solara.notifications.notifier"):
        with notifier.track("Exporting", total_steps=2) as task:
            task.step("Preparing")

    assert "Exporting" in caplog.text
