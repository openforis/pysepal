"""Errors raised by pysepal.solara: sessions, and the notification provider.

Defined here, and only here. ``session_manager`` imports
``MissingSepalHeadersError`` and ``SessionScopeClosedError`` in order to raise
them, but its ``__all__`` does not advertise them -- import from
``pysepal.solara.errors``.
"""


class SepalSessionError(RuntimeError):
    """Base error for SEPAL session creation problems."""


class MissingSepalHeadersError(SepalSessionError):
    """Raised when the current runtime carries no SEPAL authentication headers."""


class SessionScopeClosedError(SepalSessionError):
    """Raised when a session is requested for a scope that was already cleaned up."""


class NotificationProviderError(RuntimeError):
    """Raised when a component notifies with no NotificationProvider mounted.

    A bug in the app, not a runtime condition: degrading quietly switches the
    error channel off. Components published for reuse opt out with
    ``use_notifications(required=False)``.
    """
