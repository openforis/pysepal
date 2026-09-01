"""One scope-keyed registry, one no-runtime policy."""

import threading
from unittest.mock import patch

import pytest

from pysepal import _scope_registry as scope_registry
from pysepal.solara.runtime_context import (
    PROCESS_SCOPE,
    UnsupportedSolaraRuntimeError,
    resolve_scope_id,
)
from pysepal.solara.scope_registry import ScopeRegistry


@pytest.fixture
def registry() -> ScopeRegistry:
    return ScopeRegistry("test")


def test_no_runtime_resolves_to_the_process_scope(registry):
    with patch.object(scope_registry, "current_scope_id", return_value=PROCESS_SCOPE):
        registry.set("v")
        assert registry.get() == "v"
        assert registry.scope_ids() == (PROCESS_SCOPE,)


def test_get_or_create_runs_the_factory_once_per_scope(registry):
    calls = []
    registry.get_or_create(lambda: calls.append(1) or "a", scope_id="s1")
    registry.get_or_create(lambda: calls.append(1) or "b", scope_id="s1")
    assert len(calls) == 1
    assert registry.get("s1") == "a"


def test_scopes_are_isolated(registry):
    registry.set("a", scope_id="s1")
    registry.set("b", scope_id="s2")
    assert registry.get("s1") == "a"
    assert registry.get("s2") == "b"


def test_pop_returns_and_removes(registry):
    registry.set("a", scope_id="s1")
    assert registry.pop("s1") == "a"
    assert registry.get("s1") is None
    assert registry.pop("s1") is None


def test_scope_lock_is_stable_per_scope(registry):
    assert registry.scope_lock("s1") is registry.scope_lock("s1")
    assert registry.scope_lock("s1") is not registry.scope_lock("s2")
    assert isinstance(registry.scope_lock("s1"), type(threading.Lock()))


def test_scope_lock_resolves_the_scope_like_every_other_method():
    """A forgotten ``scope_id`` must not key a lock under None.

    Strictness has to be uniform on a credential store: one method that
    resolves differently from its neighbours is how the next caller ends up
    holding a lock for a scope it is not reading.
    """
    strict = ScopeRegistry("test", resolver=resolve_scope_id)
    with pytest.raises(UnsupportedSolaraRuntimeError):
        strict.scope_lock()

    lenient = ScopeRegistry("test")
    with patch.object(scope_registry, "current_scope_id", return_value=PROCESS_SCOPE):
        assert lenient.scope_lock() is lenient.scope_lock(PROCESS_SCOPE)


def test_scope_lock_survives_pop():
    """A popped scope's lock stays stable.

    Handing out a fresh lock for a scope a thread already holds one for lets
    two threads into the critical section at once (A6 review IMPORTANT#1).
    """
    registry = ScopeRegistry("test")
    lock = registry.scope_lock("s1")
    registry.set("a", scope_id="s1")
    registry.pop("s1")
    assert registry.scope_lock("s1") is lock


def test_scope_lock_survives_clear():
    """Same invariant as pop(): clear() must not orphan a lock a thread might be waiting on."""
    registry = ScopeRegistry("test")
    lock = registry.scope_lock("s1")
    registry.set("a", scope_id="s1")
    registry.clear()
    assert registry.scope_lock("s1") is lock


def test_strict_resolver_raises_instead_of_falling_back_to_the_process_scope():
    """A registry built for a credential store must not silently resolve to PROCESS_SCOPE.

    ``resolve_scope_id`` is the strict resolver: it raises when no
    per-connection runtime exists, instead of ``current_scope_id``'s
    fallback. A registry configured with it (as SessionManager will be, C12)
    must propagate that raise from ``resolve(None)`` rather than swallow it
    into the shared scope.
    """
    registry = ScopeRegistry("test", resolver=resolve_scope_id)
    with pytest.raises(UnsupportedSolaraRuntimeError):
        registry.resolve()
