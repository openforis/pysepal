"""Solara hook: use_notifications()."""

import logging
import warnings
from typing import Optional, Union

import solara

from .bus import NotificationBus, get_current_bus
from .notifier import NoopNotifier, Notifier

logger = logging.getLogger(__name__)


def use_notifications_from_bus(
    bus: Optional[NotificationBus],
) -> Union[Notifier, NoopNotifier]:
    """Resolve a Notifier from a bus (testable without Solara context)."""
    if bus is None:
        # Loud, and once per call site: the provider is mounted for the life of
        # the app, so a missing bus is misconfiguration rather than a transient.
        # Staying quiet here silences the error channel itself -- every
        # ``.error()`` the app reports goes nowhere and it looks like nothing
        # ever fails.
        warnings.warn(
            "No NotificationProvider is mounted, so notifications are dropped. "
            "Mount NotificationProvider() once at the app root, above the "
            "components that call use_notifications().",
            UserWarning,
            stacklevel=3,
        )
        return NoopNotifier()
    return Notifier(bus)


def use_notifications() -> Union[Notifier, NoopNotifier]:
    """Solara hook: returns a Notifier bound to the current kernel's bus.

    Must be called inside a Solara component function.
    If no NotificationProvider is mounted, returns a NoopNotifier.
    """
    bus = get_current_bus()
    return solara.use_memo(lambda: use_notifications_from_bus(bus), [bus])
