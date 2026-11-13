"""A headless widget through which the MapApp shell talks to the browser page.

Python cannot read the window size nor write on ``document.documentElement``;
this template does it for the shell. It is plain Vue with no Vuetify tags.
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

