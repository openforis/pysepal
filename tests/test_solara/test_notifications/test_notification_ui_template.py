"""Template contract tests for the Vue-backed notification UI."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pysepal._vuetify import IPYVUETIFY_V3

_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "pysepal"
    / "solara"
    / "notifications"
    / "NotificationUI.vue"
)

needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

# Builds a minimal Vue instance around a template's options: data, computed
# getters and methods, all bound to one object, as both Vue majors do. V2 and
# V3 are the shapes of `$vuetify.theme` on each major.
_VM_JS = """
const module = { exports: {} };
__SCRIPT__
const options = module.exports;
function makeVm(overrides) {
  const vm = Object.assign({}, options.data ? options.data() : {}, overrides);
  for (const [name, fn] of Object.entries(options.methods || {})) {
    if (!(name in overrides)) vm[name] = fn.bind(vm);
  }
  for (const [name, fn] of Object.entries(options.computed || {})) {
    Object.defineProperty(vm, name, { get: () => fn.call(vm) });
  }
  return vm;
}
const V2 = { theme: { dark: false } };
const V3 = { theme: { global: { current: { dark: false } } } };
const result = (() => { __BODY__ })();
process.stdout.write(JSON.stringify(result === undefined ? null : result));
"""


def _template() -> str:
    return _TEMPLATE_PATH.read_text()


def run_vue_script(template: Path, body: str):
    """Run JS ``body`` in node against the ``<script>`` of a ``.vue`` file.

    ``body`` sees ``options`` (the exported component), ``makeVm(overrides)`` and
    the ``V2``/``V3`` theme shapes, and returns a JSON-serialisable value.
    """
    script = re.search(r"<script>(.*?)</script>", template.read_text(), re.DOTALL).group(1)
    script = script.replace("export default", "module.exports =", 1)
    program = _VM_JS.replace("__SCRIPT__", script).replace("__BODY__", body)
    run = subprocess.run(["node", "-e", program], capture_output=True, text=True, check=True)
    return json.loads(run.stdout)


def _run_script(body: str):
    return run_vue_script(_TEMPLATE_PATH, body)


def _rule_body(selector: str) -> str:
    content = _template()
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


# The z-index of an open dialog's content and of its scrim: Vuetify 2 pins them
# at 202 and 201, Vuetify 3 puts both in a v-overlay at 2000.
_DIALOG_Z_INDEX = 2000 if IPYVUETIFY_V3 else 202
_OVERLAY_Z_INDEX = 2000 if IPYVUETIFY_V3 else 201


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
    """Theme flows in as the reactive ``is_dark`` trait, not a DOM scan.

    The widget used to scrape ``.v-application`` theme classes and watch the DOM
    with a MutationObserver because it had no reliable theme signal. The
    scope-keyed ``ThemeState`` (via ``use_theme_dark``) is that signal, so the
    trait replaces all of that machinery — none of it should remain.
    """
    content = _template()

    # Theme comes in as a trait, bound on the root wrapper.
    source = (_TEMPLATE_PATH.parent / "notification_ui.py").read_text()
    assert re.search(r"\bis_dark: bool\b", source), "is_dark trait not declared"
    assert "'theme-dark': is_dark" in content
    assert "'theme-light': !is_dark" in content

    # None of the old DOM-scraping machinery survives.
    assert "querySelectorAll" not in content, "DOM theme scan still present"
    assert "MutationObserver" not in content, "theme MutationObserver still present"
    assert "themeVersion" not in content, "themeVersion reactivity hack still present"


def test_template_has_no_vue2_only_syntax():
    """Vue 3 rejects or deprecates these, and the template must render on both majors.

    ``.native`` turns into a key filter that drops every click, ``>>>`` warns on
    every compile, and a ``props`` block duplicates the traits ipyvue already
    provides as data, which Vue 3 reports for each one.
    """
    content = _template()
    assert not re.search(r"\.native\b\s*=", content)
    assert ">>>" not in content
    assert "/deep/" not in content
    assert not re.search(r"^\s*props:", content, re.MULTILINE)


def test_deep_selectors_stand_in_rules_of_their_own():
    """A ``:deep()`` selector must not share a rule with a plain one.

    ipyvue 1 injects the style uncompiled, so on Vuetify 2 the browser drops any
    rule whose selector list holds ``:deep()``; a plain selector next to it would
    be dropped too.
    """
    style = re.search(r"<style[^>]*>(.*)</style>", _template(), re.DOTALL).group(1)
    style = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)
    for selector_list in re.findall(r"([^{}]+)\{", style):
        selectors = [s.strip() for s in selector_list.split(",")]
        if any(":deep(" in s for s in selectors):
            assert all(":deep(" in s for s in selectors), selector_list.strip()


def test_toast_clicks_are_caught_on_the_stack():
    """The stack, a plain element, takes the click on both majors.

    Vuetify 2's v-alert does not forward a click, and Vue 3 has no ``.native``
    to reach its root, so each toast carries its id for the stack's handler.
    """
    content = _template()
    assert re.search(r'class="toast-stack"\s+@click="_onToastClick"', content)
    alert = re.search(r"<v-alert\b(?P<attrs>.*?)>", content, re.DOTALL).group("attrs")
    assert ':data-toast-id="toast.id"' in alert
    assert "@click" not in alert


@needs_node
def test_a_click_inside_a_toast_dismisses_that_toast():
    dismissed = _run_script(
        """
        const dismissed = [];
        const vm = makeVm({ $vuetify: V3, _dismissToast: (id) => dismissed.push(id) });
        const inside = { closest: () => ({ getAttribute: () => "toast-1" }) };
        const outside = { closest: () => null };
        vm._onToastClick({ target: inside });
        vm._onToastClick({ target: outside });
        return dismissed;
    """
    )
    assert dismissed == ["toast-1"]


@needs_node
def test_a_toast_that_stays_open_shows_a_close_button():
    """A toast with no timeout only closes on a click, so it must show where to click."""
    alert = re.search(r"<v-alert\b(?P<attrs>.*?)>", _template(), re.DOTALL)
    assert alert, "Missing the toast v-alert"
    assert 'v-bind="alertProps(toast)"' in alert.group("attrs")

    props = _run_script(
        """
        const out = {};
        for (const [major, vuetify] of Object.entries({ v2: V2, v3: V3 })) {
          const vm = makeVm({ $vuetify: vuetify });
          out[major] = [null, 5].map((timeout) => vm.alertProps({ kind: "error", timeout }));
        }
        return out;
    """
    )
    assert [p["dismissible"] for p in props["v2"]] == [True, False]
    assert [p["closable"] for p in props["v3"]] == [True, False]


@needs_node
def test_alert_props_are_spelled_for_each_major():
    """Vuetify 2 keeps its exact props; Vuetify 3 gets their equivalents.

    On Vuetify 3 ``text`` is the alert's content, so the old boolean would print
    "true" in the cancel toast; the tint is the ``tonal`` variant there.
    """
    props = _run_script(
        """
        const out = {};
        for (const [major, vuetify] of Object.entries({ v2: V2, v3: V3 })) {
          const vm = makeVm({ $vuetify: vuetify });
          out[major] = {
            cancel: vm.alertProps({ kind: "cancel", timeout: 3 }),
            success: vm.alertProps({ kind: "success", timeout: 3 }),
          };
        }
        return out;
    """
    )
    assert props["v2"] == {
        "cancel": {"text": True, "value": True, "dismissible": False, "dense": True, "dark": False},
        "success": {
            "text": False,
            "value": True,
            "dismissible": False,
            "dense": True,
            "dark": True,
        },
    }
    assert props["v3"] == {
        "cancel": {"variant": "tonal", "closable": False, "density": "compact"},
        "success": {"variant": "flat", "closable": False, "density": "compact"},
    }


@needs_node
def test_logger_icons_and_close_button_keep_their_vuetify_2_size():
    sizes = _run_script(
        """
        const out = {};
        for (const [major, vuetify] of Object.entries({ v2: V2, v3: V3 })) {
          const vm = makeVm({ $vuetify: vuetify });
          out[major] = { icon: vm.iconSize("small"), close: vm.logCloseBtnProps };
        }
        return out;
    """
    )
    assert sizes["v2"] == {"icon": {"small": True}, "close": {"x-small": True}}
    assert sizes["v3"] == {
        "icon": {"size": 16},
        "close": {"size": "x-small", "density": "comfortable", "variant": "text"},
    }


@needs_node
def test_dismiss_timers_are_cleared_when_either_vue_unmounts_the_ui():
    """Vue 2 calls ``beforeDestroy`` and Vue 3 ``beforeUnmount``; both stop the timers."""
    cleared = _run_script(
        """
        const cleared = {};
        for (const hook of ["beforeDestroy", "beforeUnmount"]) {
          const ids = [];
          const real = global.clearTimeout;
          global.clearTimeout = (id) => ids.push(id);
          const vm = makeVm({ $vuetify: V3 });
          vm.dismissTimers = { a: 11, b: 12 };
          options[hook].call(vm);
          global.clearTimeout = real;
          cleared[hook] = ids;
        }
        return cleared;
    """
    )
    assert cleared == {"beforeDestroy": [11, 12], "beforeUnmount": [11, 12]}
