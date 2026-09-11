"""Utility functions for working with GEE interfaces in Solara applications.

This module provides convenient helper functions to access the current
GEE interface and SepalClient without having to manage sessions manually.
"""

import logging
from typing import Optional

from pysepal_api import SepalClient

from pysepal._runtime_context import current_scope_id
from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.session_info import SessionInfo, SessionsOverview

from .session_manager import SessionManager

logger = logging.getLogger(__name__)


def get_current_gee_interface() -> GEEInterface:
    """Returns the GEE interface for the current runtime.

    Under an app-launcher Solara server every connection gets its own
    interface, built from that connection's SEPAL headers. A SEPAL sandbox,
    Voila, plain Jupyter and plain scripts share one process-wide interface
    built from the machine's own credentials -- which in those runtimes belong
    to exactly one user.

    Returns:
        The interface for this runtime.

    Raises:
        SepalSessionError: A per-connection runtime has no session, i.e. the
            Page component is missing ``@with_sepal_sessions``.
    """
    return SessionManager().get_gee_interface()


def get_current_sepal_client(module_name: Optional[str] = None) -> Optional[SepalClient]:
    """Returns a SepalClient for the current runtime's session.

    One session holds one client per module name; without ``module_name`` you
    get the client of the route currently rendering (the ``module_name`` of the
    innermost ``@with_sepal_sessions`` entered).

    Args:
        module_name: Return the client for this module instead of the active one.

    Returns:
        The client, or None when there is no session, no such module client, or
        no SEPAL identity for this process (a notebook or script outside a
        SEPAL sandbox, where file I/O goes to the local filesystem).
    """
    return SessionManager().get_sepal_client(module_name=module_name)


def get_current_drive_interface() -> GDriveInterface:
    """Returns the Drive interface for the current runtime.

    Resolved exactly as :func:`get_current_gee_interface`.

    Returns:
        The interface for this runtime.

    Raises:
        SepalSessionError: A per-connection runtime has no session, i.e. the
            Page component is missing ``@with_sepal_sessions``.
    """
    return SessionManager().get_drive_interface()


def get_current_session_info() -> SessionInfo:
    """Return the current runtime scope's session status.

    Never raises. With no manager built yet, the scope id comes straight from
    the runtime, since there is no session to consult; once a manager exists,
    resolution is delegated to it so a scope that can't be resolved reports
    the process scope's id without reading its session -- see
    :meth:`~pysepal.solara.session_manager.SessionManager.get_session_info`.
    Deliberately does not instantiate ``SessionManager``: constructing it
    would flip ``is_initialized()`` on for the whole process as a side effect.
    """
    if not SessionManager.is_initialized():
        logger.debug("Session manager not initialized; reporting an empty session")
        return SessionInfo(scope_id=current_scope_id())

    return SessionManager().get_session_info()


def get_sessions_overview() -> SessionsOverview:
    """Return every session the process holds.

    Never raises. Delegates to :meth:`SessionManager.sessions_overview`
    rather than resolving on its own -- same shape as
    :func:`get_current_session_info`.
    """
    if not SessionManager.is_initialized():
        return SessionsOverview()

    return SessionManager().sessions_overview()
