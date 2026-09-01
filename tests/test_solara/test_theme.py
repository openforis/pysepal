"""Tests for scope-keyed theme-state resolution."""

import pytest

import pysepal.solara.theme as theme_mod
from pysepal import _scope_registry as scope_registry
from pysepal.solara.runtime_context import UnsupportedSolaraRuntimeError
from pysepal.solara.theme import (
    ThemeState,
    get_current_theme_state,
    resolve_theme_state,
)


def test_resolve_returns_explicit_theme_state():
    """An explicitly provided theme_state wins over any scope lookup."""
    ts = ThemeState(mode="dark")
    assert resolve_theme_state(ts) is ts


def test_resolve_uses_current_theme_state_when_available(monkeypatch):
    """With no explicit state, the current scope's theme_state is returned."""
    scoped_ts = ThemeState(mode="light")
    monkeypatch.setattr(theme_mod, "get_current_theme_state", lambda: scoped_ts)
    assert resolve_theme_state() is scoped_ts


def test_resolve_theme_state_does_not_swallow_errors(monkeypatch):
    """A guard that only exists for monkeypatched symbols hides real failures."""

    def _boom():
        raise UnsupportedSolaraRuntimeError("no runtime")

    monkeypatch.setattr(theme_mod, "get_current_theme_state", _boom)
    with pytest.raises(UnsupportedSolaraRuntimeError):
        resolve_theme_state()


def test_current_theme_state_is_stable_per_scope(monkeypatch):
    """Two reads in the same scope return the same ThemeState instance."""
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    assert get_current_theme_state() is get_current_theme_state()


def test_current_theme_state_is_isolated_per_scope(monkeypatch):
    """Two connections must not share a theme; that was the process-global bug."""
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    first = get_current_theme_state()
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-b")
    assert get_current_theme_state() is not first


def test_current_theme_state_never_raises_without_a_session(monkeypatch):
    """A Solara scope with headers but no SEPAL session must still get a theme.

    This used to raise "Session manager is active but no theme state exists".
    Theme is UI state; it has no business failing on an auth condition.
    """
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    assert isinstance(get_current_theme_state(), ThemeState)
