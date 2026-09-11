"""Deprecated import path for the scope-keyed UI state helpers.

The implementation is :mod:`pysepal._ui_state`. ``_registry`` is re-exported
because the Solara test suite clears it through this path. A name patched
through this module does not reach the code that defines it -- patch
:mod:`pysepal._ui_state` instead.
"""

from pysepal._ui_state import (  # noqa: F401 - backward compatibility
    PROCESS_SCOPE,
    ScopeRegistry,
    _registry,
    clear_scoped_state,
    current_scope_id,
    get_scoped_state,
    has_scoped_state,
)
