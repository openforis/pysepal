"""Scope-keyed theme state and Solara hooks."""

from __future__ import annotations

from typing import Optional

import solara
import solara.toestand
from traitlets import Bool, Enum, HasTraits

if not hasattr(solara.toestand, "KernelStoreFactory"):
    raise ImportError(
        "solara.toestand.KernelStoreFactory is missing. The theme is stored "
        "per virtual kernel through it, and solara's public reactive() hands "
        "every kernel the same default object: without it each connection "
        "would share one theme. Install a solara that provides it "
        "(pysepal pins solara>=1.60,<2)."
    )


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


#: One ``ThemeState`` per virtual kernel, built on first read and released with
#: the kernel that read it. A factory store, not ``solara.reactive(ThemeState())``:
#: that hands every kernel the *same* default instance.
_theme_store = solara.toestand.KernelStoreFactory(ThemeState)


def get_current_theme_state() -> ThemeState:
    """Return the theme state for the current runtime scope.

    Theme is UI state, not session state: it is created on first access, so a
    Solara connection, a Voila page, plain Jupyter, a script and pytest all get
    a real ``ThemeState``. There is no session lookup and no credential in this
    path, and this function never raises.

    The state belongs to the kernel that first read it and is released with it.
    That lifetime is the point: a ``ThemeState`` retains every widget observing
    its traitlets -- ``SepalMap`` binds a bound method and never unobserves on
    teardown -- so one kept past its connection keeps that connection's map
    alive for as long as the server runs. Outside a Solara server there is one
    kernel per process, so the process-wide fallback is still one connection's.

    A fresh state starts at ``mode="auto"``; it is no longer seeded from
    ``~/.sepal-ui-config``, which is process-global and therefore leaked one
    user's theme into every other session (issue #977).
    """
    return _theme_store.get()


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
