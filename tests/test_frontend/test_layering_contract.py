"""Guards for the modal layering contract.

pysepal's floating chrome (map, app bar, legend, task pill) must stay BELOW
Vuetify's modal baseline. Vuetify derives a dialog's z-index at runtime -- the
``stackable`` mixin reads computed z-indexes off the DOM -- so any app layer
that outranks it has to be beaten with ``!important``, which desynchronises that
bookkeeping and silently breaks click-outside-to-close.

The historical failure mode: the fullscreen map sat at 800, above Vuetify's
~201 scrim, so an outside click landed on the map and ``click:outside`` never
fired. Every workaround that pinned ``.v-overlay`` or ``.v-dialog__content``
from CSS traded that bug for a worse one (the dialog rendering behind its own
scrim). The fix was to renumber the app's own layers underneath instead.
"""

import re
from pathlib import Path

import pysepal.frontend.styles as ss
import pysepal.sepalwidgets as sw
import pysepal.solara as solara_pkg

BASE_CSS = ss.CSS_DIR / "base.css"
MAP_APP_VUE = Path(sw.__file__).parent / "vue" / "MapApp.vue"
MAP_APP_CSS = Path(solara_pkg.__file__).parent / "components" / "map_app" / "map_app.css"
LEGEND_VUE = Path(solara_pkg.__file__).parent / "components" / "Legend.vue"
NOTIFICATION_VUE = Path(solara_pkg.__file__).parent / "notifications" / "NotificationUI.vue"

VUETIFY_OVERLAY_Z_INDEX = 201

# Selector -> the file whose rule sets its z-index. Each must stay under the
# scrim so a modal covers it instead of it punching through.
APP_LAYERS = {
    ".full-screen-map > .leaflet-container": BASE_CSS,
    "header.v-app-bar": BASE_CSS,
    ".sepal-legend": LEGEND_VUE,
    ".pill-wrapper": NOTIFICATION_VUE,
    ".sepal-mapapp__drawer": MAP_APP_CSS,
    ".sepal-right-panel": MAP_APP_CSS,
}

# Rules that pin Vuetify's own modal elements. `.v-overlay__scrim` is exempt:
# it is a child of `.v-overlay`, which is its own stacking context, so a
# z-index there cannot lift it out and is merely inert.
FORBIDDEN_PINS = (".v-overlay", ".v-dialog__content", ".dialog-container")


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
    """Floating chrome must sit under the scrim, so modals cover it natively."""
    for selector, path in APP_LAYERS.items():
        z = _z_index_for(selector, path)
        assert z < VUETIFY_OVERLAY_Z_INDEX, (
            f"{selector} ({path.name}) is at z-index {z}, above Vuetify's "
            f"{VUETIFY_OVERLAY_Z_INDEX} scrim. Renumber it below instead of "
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
    for path in (BASE_CSS, MAP_APP_VUE, MAP_APP_CSS, LEGEND_VUE, NOTIFICATION_VUE):
        for selector, body in _rules(path.read_text()):
            if not any(pin in selector for pin in FORBIDDEN_PINS):
                continue
            assert "z-index" not in body, (
                f"{path.name} pins a z-index on '{selector}'. Vuetify computes "
                f"dialog stacking at runtime; overriding it desynchronises the "
                f"stackable mixin and click-outside stops firing."
            )
