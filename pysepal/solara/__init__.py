"""Solara integration for pysepal.

Session management for the SEPAL platform, scope-keyed UI state, notifications
and the decorators that tie them to a Solara or Voila render. This is the
public surface: everything an app should import lives here, and everything
else is internal.
"""

from .decorators import with_sepal_sessions
from .dev_auth import prime_dev_auth
from .errors import (
    MissingSepalHeadersError,
    SepalSessionError,
    SessionScopeClosedError,
)
from .notifications import (
    NotificationProvider,
    notify,
    track_task,
    use_notifications,
)
from .runtime_context import (
    PROCESS_SCOPE,
    UnsupportedSolaraRuntimeError,
    current_scope_id,
    resolve_scope_id,
)
from .session_info import SessionInfo, SessionsOverview
from .session_manager import SessionManager, setup_sessions
from .setup import setup_solara_server, setup_theme_colors
from .theme import (
    ThemeState,
    get_current_theme_state,
    resolve_theme_state,
    use_theme_dark,
)
from .ui_state import clear_scoped_state, get_scoped_state, has_scoped_state
from .utils import (
    get_current_drive_interface,
    get_current_gee_interface,
    get_current_sepal_client,
    get_current_session_info,
    get_sessions_overview,
)

__all__ = [
    "MissingSepalHeadersError",
    "NotificationProvider",
    "PROCESS_SCOPE",
    "SepalSessionError",
    "SessionInfo",
    "SessionManager",
    "SessionScopeClosedError",
    "SessionsOverview",
    "ThemeState",
    "UnsupportedSolaraRuntimeError",
    "clear_scoped_state",
    "current_scope_id",
    "get_current_drive_interface",
    "get_current_gee_interface",
    "get_current_sepal_client",
    "get_current_session_info",
    "get_current_theme_state",
    "get_scoped_state",
    "get_sessions_overview",
    "has_scoped_state",
    "notify",
    "prime_dev_auth",
    "resolve_scope_id",
    "resolve_theme_state",
    "setup_sessions",
    "setup_solara_server",
    "setup_theme_colors",
    "track_task",
    "use_notifications",
    "use_theme_dark",
    "with_sepal_sessions",
]
