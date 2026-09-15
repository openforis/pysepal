"""Solara hook: use_notifications()."""

import logging
from typing import Optional, Union

import solara

from pysepal.solara.errors import NotificationProviderError

from .bus import NotificationBus, get_current_bus
from .notifier import NoopNotifier, Notifier

logger = logging.getLogger(__name__)


def use_notifications_from_bus(
    bus: Optional[NotificationBus],
    required: bool = True,
) -> Union[Notifier, NoopNotifier]:
    """Resolve a Notifier from a bus (testable without Solara context).

    Args:
        bus: The scope's bus, or None when no provider is mounted.
        required: Whether a missing provider is an error.

    Returns:
        A Notifier, or a NoopNotifier when no provider is mounted and
        ``required`` is False.

    Raises:
        NotificationProviderError: No provider is mounted and one is required.
    """
    if bus is not None:
        return Notifier(bus)
    if required:
        raise NotificationProviderError(
            "No NotificationProvider is mounted, so nothing this component "
            "reports can reach the user. Mount NotificationProvider() once at "
            "the app root. A component that also renders standalone should ask "
            "for use_notifications(required=False) and surface feedback itself."
        )
    return NoopNotifier()


def use_notifications(required: bool = True) -> Union[Notifier, NoopNotifier]:
    """Solara hook: return a Notifier bound to the current kernel's bus.

    Must be called inside a Solara component function.

    Args:
        required: Whether a missing provider is an error. Pass False only from
            a component that is published for reuse and reports feedback itself.

    Returns:
        A Notifier, or a NoopNotifier when no provider is mounted and
        ``required`` is False.

    Raises:
        NotificationProviderError: No provider is mounted and one is required.
    """
    bus = get_current_bus()
    return solara.use_memo(lambda: use_notifications_from_bus(bus, required), [bus, required])
