"""Construction smoke checks for NotificationProvider in a Voila-like runtime."""

from unittest.mock import patch

import solara

from pysepal import _scope_registry as scope_registry
from pysepal.solara.notifications import NotificationProvider
from pysepal.solara.notifications.bus import _refcounts, _registry


@solara.component
def _Page():
    NotificationProvider()


def test_notification_provider_constructs_in_voila_like_runtime():
    _registry.clear()
    _refcounts.clear()
    try:
        with patch.object(
            scope_registry,
            "current_scope_id",
            return_value="voila:render-kernel",
        ):
            solara.render(_Page(), handle_error=False)
    finally:
        _registry.clear()
        _refcounts.clear()
