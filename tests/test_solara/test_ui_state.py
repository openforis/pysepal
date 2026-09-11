"""Tests for the scope-keyed UI-state registry."""

from unittest.mock import patch

from pysepal import _scope_registry as scope_registry
from pysepal.solara import ui_state


def test_same_scope_reuses_the_same_instance():
    with patch.object(scope_registry, "current_scope_id", return_value="kernel-a"):
        first = ui_state.get_scoped_state("theme_state", dict)
        second = ui_state.get_scoped_state("theme_state", dict)
    assert first is second


def test_different_scopes_get_different_instances():
    with patch.object(scope_registry, "current_scope_id", return_value="kernel-a"):
        a = ui_state.get_scoped_state("theme_state", dict)
    with patch.object(scope_registry, "current_scope_id", return_value="kernel-b"):
        b = ui_state.get_scoped_state("theme_state", dict)
    assert a is not b


def test_explicit_scope_id_bypasses_the_resolver():
    with patch.object(
        scope_registry, "current_scope_id", side_effect=AssertionError("must not resolve")
    ):
        state = ui_state.get_scoped_state("theme_state", dict, scope_id="kernel-a")
    assert state == {}


def test_unresolvable_runtime_falls_back_to_the_process_scope():
    """Scripts and pytest have no runtime id; UI state must still be available."""
    with patch.object(scope_registry, "current_scope_id", return_value=ui_state.PROCESS_SCOPE):
        state = ui_state.get_scoped_state("theme_state", dict)
    assert state is ui_state.get_scoped_state("theme_state", dict, scope_id="process")


def test_has_scoped_state_never_creates():
    assert ui_state.has_scoped_state("theme_state", "kernel-a") is False
    ui_state.get_scoped_state("theme_state", dict, scope_id="kernel-a")
    assert ui_state.has_scoped_state("theme_state", "kernel-a") is True


def test_clear_scoped_state_drops_only_that_scope():
    a = ui_state.get_scoped_state("theme_state", dict, scope_id="kernel-a")
    ui_state.get_scoped_state("theme_state", dict, scope_id="kernel-b")

    ui_state.clear_scoped_state("kernel-a")

    assert ui_state.has_scoped_state("theme_state", "kernel-a") is False
    assert ui_state.has_scoped_state("theme_state", "kernel-b") is True
    assert ui_state.get_scoped_state("theme_state", dict, scope_id="kernel-a") is not a
