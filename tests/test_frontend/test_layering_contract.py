"""Guards for the modal layering contract.

pysepal's floating chrome (map, app bar, legend, task pill) must stay BELOW
Vuetify's overlays. Vuetify gives each overlay (menu, dialog and its scrim) its
z-index at runtime, from 2000 and stacked by opening order, so an app layer that
outranks them can only be beaten by pinning an overlay's z-index from CSS, which
overrides the stacking Vuetify computes. pysepal keeps its own layers below 200
instead.
"""

import re
from pathlib import Path

import pysepal.frontend.styles as ss
import pysepal.solara as solara_pkg

BASE_CSS = ss.CSS_DIR / "base.css"
MAP_APP_CSS = Path(solara_pkg.__file__).parent / "components" / "map_app" / "map_app.css"
LEGEND_VUE = Path(solara_pkg.__file__).parent / "components" / "Legend.vue"
NOTIFICATION_VUE = Path(solara_pkg.__file__).parent / "notifications" / "NotificationUI.vue"

APP_LAYER_CEILING = 200

# Selector -> the file whose rule sets its z-index. Each must stay under the
# ceiling so a modal covers it instead of it punching through.
APP_LAYERS = {
    ".full-screen-map > .leaflet-container": BASE_CSS,
    "header.v-app-bar": BASE_CSS,
    ".sepal-legend": LEGEND_VUE,
    ".pill-wrapper": NOTIFICATION_VUE,
    ".sepal-mapapp__drawer": MAP_APP_CSS,
    ".sepal-right-panel": MAP_APP_CSS,
}

# Rules that pin Vuetify's own modal elements (`.v-overlay` also matches its
# `__content` and `__scrim` children).
FORBIDDEN_PINS = (".v-overlay", ".dialog-container")


def _z_index_for(selector: str, path: Path) -> int:
    """Return the z-index declared in the rule block for ``selector``.

    Anchored to the start of a line so a `.vue` template's ``class="…"`` never
    shadows the stylesheet rule of the same name.
    """
    text = path.read_text()
    rule = re.search(
        rf"^{re.escape(selector)}\s*\{{([^}}]*)\}}",
        text,
        re.MULTILINE,
    )
    assert rule, f"no CSS rule for {selector} in {path.name}"
    match = re.search(r"z-index:\s*(\d+)", rule.group(1))
    assert match, f"{selector} in {path.name} declares no z-index"
    return int(match.group(1))


def test_app_layers_stay_below_the_vuetify_modal_baseline():
    """Floating chrome must sit under the overlays, so modals cover it natively."""
    for selector, path in APP_LAYERS.items():
        z = _z_index_for(selector, path)
        assert z < APP_LAYER_CEILING, (
            f"{selector} ({path.name}) is at z-index {z}, above pysepal's "
            f"{APP_LAYER_CEILING} ceiling. Renumber it below instead of "
            f"pinning Vuetify's layers -- see the contract in base.css."
        )


def _rules(text: str):
    """Yield ``(selector, body)`` for each CSS rule, ignoring comments.

    Comments are stripped first: a prose mention of ``.v-overlay`` would
    otherwise be read as a selector and swallow the next rule's body.
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        yield match.group(1).strip(), match.group(2)


def test_no_stylesheet_pins_the_vuetify_modal_z_index():
    """Pinning the scrim or the dialog breaks click-outside-to-close."""
    for path in (BASE_CSS, MAP_APP_CSS, LEGEND_VUE, NOTIFICATION_VUE):
        for selector, body in _rules(path.read_text()):
            if not any(pin in selector for pin in FORBIDDEN_PINS):
                continue
            assert "z-index" not in body, (
                f"{path.name} pins a z-index on '{selector}'. Vuetify stacks "
                f"its overlays at runtime; overriding one breaks that order."
            )
