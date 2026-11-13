"""A button that cycles the theme between dark, light and the browser's choice."""

from typing import Callable, Optional

import solara

from pysepal.solara.theme import ThemeState, resolve_theme_state

MODES = ("dark", "light", "auto")


def use_theme_mode(theme_state: ThemeState) -> str:
    """Return the theme mode of ``theme_state`` and re-render when it changes."""
    mode, set_mode = solara.use_state(theme_state.mode)

    def observe():
        def handler(change):
            set_mode(change["new"])

        set_mode(theme_state.mode)
        theme_state.observe(handler, "mode")
        return lambda: theme_state.unobserve(handler, "mode")

    solara.use_effect(observe, [id(theme_state)])
    return mode


@solara.component_vue("ThemeToggle.vue")
def ThemeToggleButton(
    mode: str,
    enable_auto: bool = True,
    event_set_mode: Optional[Callable[[str], None]] = None,
    event_set_dark: Optional[Callable[[bool], None]] = None,
):
    """The button, and the part of the theme only the browser can do.

    It cycles ``mode``, resolves ``auto`` from the colour-scheme preference
    (following it while the page is open), applies the theme to the page and
    remembers the mode for the next visit.

    Args:
        mode: The theme mode: ``"dark"``, ``"light"`` or ``"auto"``.
        enable_auto: Whether the cycle includes ``auto``.
        event_set_mode: Called with the next mode on a click, and once on mount
            with the mode stored by an earlier visit.
        event_set_dark: Called with whether the page is dark, each time that is
            resolved.
    """


@solara.component
def ThemeToggle(theme_state: Optional[ThemeState] = None, enable_auto: bool = True):
    """Cycle the theme between dark, light and auto, and apply it to the page.

    The mode lives on ``theme_state`` (the current scope's by default). The
    browser resolves it, and the toggle writes the result to ``theme_state.dark``
    and to Solara's theme.

    Args:
        theme_state: The theme state to drive; defaults to the current scope's.
        enable_auto: Whether the cycle includes ``auto``.
    """
    state = resolve_theme_state(theme_state)
    mode = use_theme_mode(state)

    def set_mode(new: str):
        if new in MODES and (enable_auto or new != "auto"):
            state.set_mode(new)

    def set_dark(dark: bool):
        state.set_dark(dark)
        solara.lab.theme.dark = bool(dark)

    return ThemeToggleButton(
        mode=mode, enable_auto=enable_auto, event_set_mode=set_mode, event_set_dark=set_dark
    )
