"""A button that cycles the theme between dark, light and the browser's choice."""

from typing import Optional

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara

from pysepal.solara.theme import ThemeState, resolve_theme_state

from .bridges import ColorSchemeBridge

MODES = ("dark", "light", "auto")

ICONS = {"dark": "mdi-weather-night", "light": "mdi-white-balance-sunny", "auto": "mdi-auto-fix"}


def next_mode(mode: str, enable_auto: bool = True) -> str:
    """Return the mode that follows ``mode`` in the dark, light, auto cycle."""
    cycle = MODES if enable_auto else MODES[:2]
    if mode not in cycle:
        return cycle[0]
    return cycle[(cycle.index(mode) + 1) % len(cycle)]


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


@solara.component
def ThemeToggle(theme_state: Optional[ThemeState] = None, enable_auto: bool = True):
    """Cycle the theme between dark, light and auto, and apply it to the page.

    The mode lives on ``theme_state`` (the current scope's by default); the
    toggle resolves ``auto`` from the browser's colour-scheme preference, writes
    the result to ``theme_state.dark`` and to Solara's theme, and remembers the
    mode in the browser for the next visit.

    Args:
        theme_state: The theme state to drive; defaults to the current scope's.
        enable_auto: Whether the cycle includes ``auto``.
    """
    state = resolve_theme_state(theme_state)
    mode = use_theme_mode(state)
    prefers_dark, set_prefers_dark = solara.use_state(False)
    adopted = solara.use_ref(False)

    dark = prefers_dark if mode == "auto" else mode == "dark"

    def apply():
        state.set_dark(dark)
        solara.lab.theme.dark = dark

    solara.use_effect(apply, [dark, id(state)])

    def adopt(stored: str):
        if adopted.current:
            return
        adopted.current = True
        if stored in MODES and (enable_auto or stored != "auto"):
            state.set_mode(stored)

    with rv.Html(tag="span", class_="sepal-theme-toggle") as main:
        ColorSchemeBridge(
            mode=mode, dark=dark, event_prefers_dark=set_prefers_dark, event_stored_mode=adopt
        )
        btn = rv.Btn(
            icon=True,
            children=[rv.Icon(children=[ICONS[mode]], size="small")],
            variant="text",
        )
    ipyvue.use_event(btn, "click", lambda *_: state.set_mode(next_mode(mode, enable_auto)))
    return main
