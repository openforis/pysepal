"""Scope-keyed theme state and Solara hooks."""

from __future__ import annotations

from typing import Optional

import solara
from traitlets import Bool, Enum, HasTraits

from pysepal._ui_state import get_scoped_state


class ThemeState(HasTraits):
    """Theme preference and resolved dark/light state, keyed by runtime scope."""

    mode = Enum(values=["dark", "light", "auto"], default_value="auto")
    dark = Bool(False)

    def __init__(self, mode: str = "auto", dark: Optional[bool] = None, **kwargs):
        """Initialize with an initial mode and optional explicit dark value."""
        super().__init__(**kwargs)
        self.set_mode(mode)
        if dark is not None:
            self.set_dark(dark)

    def set_mode(self, mode: str) -> None:
        """Update theme preference and keep fixed modes aligned with `dark`."""
        self.mode = mode
        if mode == "dark":
            self.dark = True
        elif mode == "light":
            self.dark = False

    def set_dark(self, dark: bool) -> None:
        """Update the effective dark/light value."""
        self.dark = bool(dark)

    @staticmethod
    def mode_to_widget_dark(mode: str) -> Optional[bool]:
        """Map theme mode to ThemeToggle.dark semantics."""
        if mode == "auto":
            return None
        return mode == "dark"

    @staticmethod
    def widget_dark_to_mode(value: Optional[bool]) -> str:
        """Map ThemeToggle.dark semantics back to theme mode."""
        if value is None:
            return "auto"
        return "dark" if value else "light"


def get_current_theme_state() -> ThemeState:
    """Return the theme state for the current runtime scope.

    Theme is UI state, not session state: it is keyed by the runtime scope and
    created on first access, so a Solara connection, a Voila page, plain Jupyter,
    a script and pytest all get a real ``ThemeState``. There is no session lookup
    and no credential in this path, and this function never raises.

    A fresh state starts at ``mode="auto"``; it is no longer seeded from
    ``~/.sepal-ui-config``, which is process-global and therefore leaked one
    user's theme into every other session (issue #977).
    """
    return get_scoped_state("theme_state", ThemeState)


def resolve_theme_state(theme_state: Optional[ThemeState] = None) -> ThemeState:
    """Return a usable ThemeState.

    Precedence: an explicit ``theme_state``, else the current scope's, which
    :func:`get_current_theme_state` creates on demand for every runtime
    including scripts and pytest.

    Args:
        theme_state: An explicit state to use instead of the scope's.

    Returns:
        The theme state to render with.
    """
    return theme_state if theme_state is not None else get_current_theme_state()


def use_theme_dark(theme_state: Optional[ThemeState] = None) -> bool:
    """Reactively return the effective dark/light state for the current scope."""
    theme_state = theme_state or get_current_theme_state()
    dark, set_dark = solara.use_state(bool(theme_state.dark))

    def _observe():
        def handler(change):
            set_dark(bool(change["new"]))

        theme_state.observe(handler, "dark")
        return lambda: theme_state.unobserve(handler, "dark")

    solara.use_effect(_observe, [id(theme_state)])
    return dark
