"""Template contract tests for the Vue-backed notification UI."""

import re
from pathlib import Path

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


def _computed_body(name: str, content: str) -> str:
    """Extract the body of a `computed: { ... }` property by name."""
    match = re.search(
        rf"{re.escape(name)}\(\)\s*\{{(?P<body>.*?)\n\s{{4}}\}},",
        content,
        re.DOTALL,
    )
    assert match, f"Missing computed property {name}"
    return match.group("body")


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


def test_pill_ring_is_determinate_when_progress_known():
    """The pill spinner binds to task progress instead of spinning forever.

    Tasks that publish ``progress`` (a download) get a determinate ring;
    tasks that never do (a validation pass) keep the indeterminate spinner
    via the ``:indeterminate`` binding — the bare hardcoded attribute must go.
    """
    content = _TEMPLATE_PATH.read_text()
    assert ":indeterminate=" in content, "spinner must bind indeterminate to progress"
    assert re.search(
        r"<v-progress-circular[^>]*:value=", content, re.DOTALL
    ), "spinner must bind :value to task progress"
    assert not re.search(
        r"<v-progress-circular\s+indeterminate\b", content, re.DOTALL
    ), "hardcoded indeterminate spinner still present"


def test_pill_percentage_requires_known_progress():
    """The leading percentage only appears once progress is known.

    A task can carry a ``detail`` while still indeterminate (no numeric
    ``value`` yet, e.g. a wait reason) — the pill must show that detail
    without a bogus percentage in front of it.
    """
    content = _TEMPLATE_PATH.read_text()
    pct_body = _computed_body("pillPct", content)
    assert re.search(
        r"pillProgress\s*==\s*null", pct_body
    ), "pillPct must return null while progress is unknown"


def test_pill_text_alternates_with_progress_detail():
    """The pill alternates between the task title and its progress detail.

    ``progressDetail`` carries the current item's own progress string; a
    frame timer swaps ``pillText`` between the title and the detail. A
    detail is shown whenever it is set, even on an indeterminate task
    (``progress == null``, e.g. a wait reason) — only the leading
    percentage needs a known ``progress`` value (see the test above).
    Tasks without a detail never alternate.
    """
    content = _TEMPLATE_PATH.read_text()
    assert "progressDetail" in content, "progressDetail prop not consumed"
    assert re.search(r"pillFrameB|frameB", content), "no alternation frame state in template"
    assert re.search(
        r"this\._pillFrameTimer\s*=\s*setInterval\(.*?,\s*2500\);", content, re.DOTALL
    ), "alternation timer must fire every 2500ms"
    assert (
        "clearInterval(this._pillFrameTimer)" in content
    ), "frame timer must be cleared on destroy"
    assert (
        "this.pillFrameB ? t.progressDetail : t.title" in content
    ), "frame B must show the detail, frame A the title"

    detail_body = _computed_body("pillHasDetail", content)
    detail_code = re.sub(r"//[^\n]*", "", detail_body)  # drop line comments
    assert "progressDetail" in detail_code, "detail visibility must check progressDetail"
    assert "t.progress" not in detail_code.replace("t.progressDetail", ""), (
        "a detail must be shown whenever it is set, even on an indeterminate "
        "(progress == null) task — the code must not also gate on t.progress"
    )


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
