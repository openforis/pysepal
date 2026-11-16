"""Template contract tests for the Vue-backed notification UI."""

import re
from pathlib import Path

import pytest

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "pysepal"
    / "solara"
    / "notifications"
    / "NotificationUI.vue"
)


def _rule_body(selector: str) -> str:
    content = _TEMPLATE_PATH.read_text()
    match = re.search(
        rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\n\}}",
        content,
        re.DOTALL,
    )
    assert match, f"Missing CSS rule for {selector}"
    return match.group("body")


def _numeric_property(rule_body: str, name: str) -> int:
    match = re.search(rf"{re.escape(name)}:\s*(\d+);", rule_body)
    assert match, f"Missing numeric property {name}"
    return int(match.group(1))


_DIALOG_Z_INDEX = 202  # Vuetify 2 v-dialog__content default
_OVERLAY_Z_INDEX = 201  # Vuetify 2 v-overlay default


def test_toasts_sit_above_dialogs():
    """Keep the toast stack above Vuetify dialog/overlay defaults.

    Toasts are often *about* the dialog (errors, progress) so they must remain
    visible even when a modal is open — otherwise users miss critical feedback
    and assume the app is unresponsive.
    """
    toast_z = _numeric_property(_rule_body(".toast-stack"), "z-index")
    assert toast_z > _DIALOG_Z_INDEX, f"toast z-index {toast_z} not above dialog"


def test_pill_sits_below_the_modal_baseline():
    """Keep the pill/logger under Vuetify's scrim, unlike the toast stack.

    It used to share the toast tier, which floated the logger panel over open
    modals. It now sits below the scrim so a modal dims it instead — and because
    every app layer above Vuetify's baseline has to be pinned with `!important`,
    which desynchronises the `stackable` mixin's runtime z-index bookkeeping and
    breaks click-outside-to-close. See the layering contract in
    ``pysepal/frontend/css/base.css``.
    """
    pill_z = _numeric_property(_rule_body(".pill-wrapper"), "z-index")
    assert pill_z < _OVERLAY_Z_INDEX, f"pill z-index {pill_z} not below the scrim"


def test_notification_pill_keeps_mapapp_right_offset_hook():
    """Preserve the MapApp-published CSS variable used for right-panel alignment."""
    pill_rule = _rule_body(".pill-wrapper")
    assert "var(--sepal-notification-right-offset, 0px)" in pill_rule


def test_pill_and_logger_font_sizes_are_px_for_cross_runtime_parity():
    """Pill/logger font sizes are absolute px, not em.

    `em` inherits the host font size, which differs between `solara run` and
    Voila's JupyterLab base — so the logger rendered at different sizes per
    runtime. Pinning px keeps them identical across runtimes; guard against a
    revert to em (the exact value may still be tuned).
    """
    for selector in (
        ".pill-container",
        ".pill-log-header",
        ".pill-log-body",
        ".pill-log-line",
    ):
        body = _rule_body(selector)
        assert re.search(r"font-size:\s*\d+px\b", body), f"{selector} font-size must be px"
        assert not re.search(
            r"font-size:\s*[\d.]+em\b", body
        ), f"{selector} font-size must not be em (breaks cross-runtime parity)"


def test_theme_is_driven_by_prop_not_dom_scan():
    """Theme flows in as the reactive ``is_dark`` prop, not a DOM scan.

    The widget used to scrape ``.v-application`` theme classes and watch the DOM
    with a MutationObserver because it had no reliable theme signal. The
    scope-keyed ``ThemeState`` (via ``use_theme_dark``) is that signal, so the
    prop replaces all of that machinery — none of it should remain.
    """
    content = _TEMPLATE_PATH.read_text()

    # Theme comes in as a prop, bound on the root wrapper.
    assert re.search(r"is_dark:\s*\{", content), "is_dark prop not declared"
    assert "'theme-dark': is_dark" in content
    assert "'theme-light': !is_dark" in content

    # None of the old DOM-scraping machinery survives.
    assert "querySelectorAll" not in content, "DOM theme scan still present"
    assert "MutationObserver" not in content, "theme MutationObserver still present"
    assert "themeVersion" not in content, "themeVersion reactivity hack still present"


def test_a_toast_that_stays_open_shows_a_close_button():
    """A toast with no timeout only closes on a click, so it must show where to click."""
    content = _TEMPLATE_PATH.read_text()
    alert = re.search(r"<v-alert\b(?P<attrs>.*?)>", content, re.DOTALL)
    assert alert, "Missing the toast v-alert"
    assert ':dismissible="!toast.timeout"' in alert.group("attrs")


# The pre-4.2 toast palette. The theme colours do not fit toasts: the light
# theme's success is Vuetify's #4CAF50, not the SEPAL green, and the dark theme's
# info is a light grey that white text cannot be read on.
_TOAST_PALETTE = {
    ("light", "success"): "rgba(91, 182, 36, 0.9)",
    ("light", "info"): "rgba(33, 150, 243, 0.9)",
    ("light", "warning"): "rgba(251, 140, 0, 0.9)",
    ("light", "error"): "rgba(255, 82, 82, 0.92)",
    ("dark", "success"): "rgba(63, 128, 42, 0.9)",
    ("dark", "info"): "rgba(21, 101, 192, 0.9)",
    ("dark", "warning"): "rgba(230, 120, 0, 0.9)",
    ("dark", "error"): "rgba(166, 50, 40, 0.92)",
}


def _toast_background(theme: str, kind: str) -> str:
    content = _TEMPLATE_PATH.read_text()
    selector = rf"\.theme-{theme} > \.toast-stack \.toast-alert\.toast-{kind}\b"
    match = re.search(rf"{selector}[^{{]*\{{(?P<body>[^}}]*)\}}", content)
    assert match, f"Missing the {theme} {kind} toast rule"
    background = re.search(r"background-color:\s*([^;]+?)\s*!important;", match.group("body"))
    assert background, f"The {theme} {kind} toast rule sets no background"
    return background.group(1)


@pytest.mark.parametrize(("theme", "kind"), list(_TOAST_PALETTE))
def test_toasts_keep_the_sepal_palette(theme, kind):
    assert _toast_background(theme, kind) == _TOAST_PALETTE[(theme, kind)]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_cancel_toast_is_painted_as_an_info_toast(theme):
    assert _toast_background(theme, "cancel") == _toast_background(theme, "info")


def test_every_toast_is_a_filled_alert():
    """A cancel toast differs from an info toast by its icon only, not by its style."""
    content = _TEMPLATE_PATH.read_text()
    attrs = re.search(r"<v-alert\b(?P<attrs>.*?)>", content, re.DOTALL).group("attrs")
    assert ":text=" not in attrs
    assert re.search(r"^\s*dark\s*$", attrs, re.MULTILINE)
    assert "mdi-cancel" in attrs
