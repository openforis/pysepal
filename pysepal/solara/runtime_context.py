"""Deprecated import path for the runtime scope resolvers.

The implementation is :mod:`pysepal._runtime_context`, which sits above
:mod:`pysepal.solara` so that a message catalogue can resolve a scope without
importing session management and notifications. These are the same objects,
so identity comparisons across the two paths still hold. A name patched
through this module does not reach the code that defines it -- patch
:mod:`pysepal._runtime_context` instead.
"""

from pysepal._runtime_context import (  # noqa: F401 - backward compatibility
    PROCESS_SCOPE,
    UnsupportedSolaraRuntimeError,
    current_scope_id,
    resolve_scope_id,
)
