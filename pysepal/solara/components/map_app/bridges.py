"""Headless widgets through which the MapApp shell talks to the browser page.

Python cannot read the window size or the colour-scheme preference, nor write on
``document.documentElement``; these two templates do it for the shell. They are
plain Vue with no Vuetify tags, so they run unchanged on both ipyvuetify majors.
"""

from typing import Callable, Dict, Optional

import solara


@solara.component_vue("ViewportBridge.vue")
def ViewportBridge(
    css_vars: Dict[str, str],
    body_class: str = "",
    event_window_size: Optional[Callable[[dict], None]] = None,
):
    """Publish layout variables on the page root and report the window size.

    Args:
        css_vars: CSS custom properties set on ``document.documentElement`` and
            removed when the bridge unmounts. Floating components outside the
            shell (legend, notifications) read them to stay clear of the panels.
        body_class: A class kept on ``document.body`` while it is not empty.
        event_window_size: Called with ``{"w": int, "h": int}`` on mount and on
            every window resize.
    """


@solara.component_vue("ColorSchemeBridge.vue")
def ColorSchemeBridge(
    mode: str = "",
    event_prefers_dark: Optional[Callable[[bool], None]] = None,
    event_stored_mode: Optional[Callable[[str], None]] = None,
):
    """Report the browser's colour-scheme preference and remember the theme mode.

    Args:
        mode: The theme mode to store in the browser (``"dark"``, ``"light"`` or
            ``"auto"``); empty stores nothing.
        event_prefers_dark: Called with the ``prefers-color-scheme: dark`` match
            on mount and whenever the preference changes.
        event_stored_mode: Called once on mount with the mode stored by an
            earlier visit, if there is one.
    """
