"""Scope-keyed UI state for pysepal Solara and Voila apps.

UI preferences (theme, locale) are per-connection state with no authentication
in their resolution path: a Voila page, a plain notebook or a script must hold
a theme without a SEPAL session existing. Keyed by
:func:`pysepal._runtime_context.current_scope_id`, which falls back to
the process scope, so every getter built on this is total.
"""

from typing import Any, Callable, Dict, Optional, TypeVar

from pysepal._runtime_context import PROCESS_SCOPE, current_scope_id
from pysepal._scope_registry import ScopeRegistry

__all__ = [
    "PROCESS_SCOPE",
    "clear_scoped_state",
    "current_scope_id",
    "get_scoped_state",
    "has_scoped_state",
]

T = TypeVar("T")

_registry: ScopeRegistry[Dict[str, Any]] = ScopeRegistry("UI state")


def get_scoped_state(name: str, factory: Callable[[], T], scope_id: Optional[str] = None) -> T:
    """Return the ``name`` state for a scope, creating it on miss.

    Args:
        name: Key of the state within the scope, e.g. ``"theme_state"``.
        factory: Zero-argument callable building the state on first access.
        scope_id: Scope to read from; defaults to the current one.

    Returns:
        The stored state instance.
    """
    scope = _registry.resolve(scope_id)
    with _registry.scope_lock(scope):
        states = _registry.get_or_create(dict, scope_id=scope)
        if name not in states:
            states[name] = factory()
        return states[name]


def has_scoped_state(name: str, scope_id: Optional[str] = None) -> bool:
    """Whether ``name`` already exists for a scope, without creating it.

    Args:
        name: Key of the state within the scope.
        scope_id: Scope to inspect; defaults to the current one.

    Returns:
        True when the state exists.
    """
    scope = _registry.resolve(scope_id)
    with _registry.scope_lock(scope):
        states = _registry.get(scope)
        return states is not None and name in states


def clear_scoped_state(scope_id: Optional[str] = None) -> None:
    """Drop every UI state held for a scope.

    Args:
        scope_id: Scope to clear; defaults to the current one.
    """
    scope = _registry.resolve(scope_id)
    with _registry.scope_lock(scope):
        _registry.pop(scope)
