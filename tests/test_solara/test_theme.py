"""Tests for per-kernel theme-state resolution."""

import gc
import weakref

import pytest

import pysepal.solara.theme as theme_mod
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


def test_one_kernel_reads_the_same_theme_twice(kernel_contexts):
    """Two reads in the same kernel return the same ThemeState instance."""
    with kernel_contexts():
        assert get_current_theme_state() is get_current_theme_state()


def test_two_kernels_do_not_share_a_theme(kernel_contexts):
    """Two connections must not share a theme; that was the process-global bug."""
    with kernel_contexts():
        first = get_current_theme_state()
    with kernel_contexts():
        assert get_current_theme_state() is not first


def test_a_theme_is_available_without_a_kernel():
    """A script, a notebook and pytest have no kernel and still need a theme."""
    assert isinstance(get_current_theme_state(), ThemeState)


def test_pysepal_keeps_no_reference_to_a_closed_kernels_theme(kernel_contexts):
    """A theme retains every widget that observes it.

    ``SepalMap._bind_theme_source`` observes ``dark`` with a bound method and
    unobserves only when it rebinds to another source, never on teardown. A
    theme the process keeps after its kernel is gone therefore keeps that
    connection's map -- layers and Earth Engine objects included -- reachable
    for the lifetime of the server.
    """
    context = kernel_contexts()
    with context:
        state = get_current_theme_state()
    reference = weakref.ref(state)
    del state

    context.close()
    # Stands in for the context itself being collected: ``user_dicts`` is the
    # kernel's own storage and goes with it. Whatever still holds the theme
    # after this line is held by pysepal, not by solara.
    context.user_dicts.clear()
    gc.collect()

    assert reference() is None
