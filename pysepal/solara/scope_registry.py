"""Deprecated import path for :class:`pysepal._scope_registry.ScopeRegistry`.

A name patched through this module does not reach the code that defines it --
patch :mod:`pysepal._scope_registry` instead.
"""

from pysepal._scope_registry import (  # noqa: F401 - backward compatibility
    ScopeRegistry,
    current_scope_id,
)
