"""Tests for NotificationProvider helpers."""

from unittest.mock import patch

import pytest

from pysepal import _scope_registry as scope_registry
from pysepal.solara.notifications.bus import (
    NotificationBus,
    _refcounts,
    _registry,
    cleanup_bus,
    get_current_bus,
)
from pysepal.solara.notifications.provider import _get_or_create_current_bus


@pytest.fixture
def clean_bus_registry():
    _registry.clear()
    _refcounts.clear()
    yield
    _registry.clear()
    _refcounts.clear()


def test_every_mount_delegates_to_create_bus(clean_bus_registry):
    """The helper must not short-circuit when a bus already exists.

    ``create_bus`` is itself get-or-create, and it is what takes the reference;
    reusing a bus without going through it is the drop the next test covers.
    """
    sentinel = object()
    with patch.object(scope_registry, "current_scope_id", return_value="k1"), patch(
        "pysepal.solara.notifications.provider.create_bus",
        return_value=sentinel,
    ) as create_bus:
        _registry.set(NotificationBus(), scope_id="k1")
        assert _get_or_create_current_bus() is sentinel
        create_bus.assert_called_once_with()


def test_a_second_provider_mount_takes_its_own_reference(clean_bus_registry):
    """A double-mount must survive the first unmount.

    Every mount goes through this helper exactly once (``use_memo``), and every
    mount registers its own ``cleanup_bus`` effect. A second mount that does not
    take a reference lets the first unmount tear down a bus the second is still
    publishing to, silently stopping its notifications.
    """
    with patch.object(scope_registry, "current_scope_id", return_value="k1"):
        first = _get_or_create_current_bus()  # mount A
        assert _get_or_create_current_bus() is first  # mount B

        cleanup_bus()  # A unmounts; B is still live
        assert get_current_bus() is first

        cleanup_bus()  # B unmounts
        assert get_current_bus() is None


def test_provider_helper_creates_bus_with_voila_runtime_id(clean_bus_registry):
    with patch.object(
        scope_registry,
        "current_scope_id",
        return_value="voila:provider-kernel",
    ):
        bus = _get_or_create_current_bus()
        assert _get_or_create_current_bus() is bus
