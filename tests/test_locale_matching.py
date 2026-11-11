"""The one locale algorithm, and the selector widget that carries its browser copy."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import solara

import pysepal
from pysepal._locale import match_offered_locale, normalize_locale
from pysepal.i18n import current_locale, set_locale
from pysepal.solara.components._locale_widget import VUE_DIR, LocaleSelectWidget
from pysepal.solara.components.locale_select import LocaleSelectComponent

FIXTURE = Path(__file__).parent / "fixtures" / "locale_matching.json"
CASES = json.loads(FIXTURE.read_text())
TEMPLATE = VUE_DIR / "LocaleSelect.vue"
HARNESS = Path(__file__).parent / "js" / "locale_parity.mjs"
LIFECYCLE = Path(__file__).parent / "js" / "locale_lifecycle.mjs"


def test_the_fixture_has_cases():
    """Guard the guard: an empty table would make the parametrised test vacuous."""
    assert len(CASES) >= 12


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c['candidate'] or 'empty'}")
def test_matching_follows_the_shared_table(case):
    assert match_offered_locale(case["candidate"], case["offered"]) == case["expected"]


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("pt_br", "pt-BR"),
        ("PT-BR", "pt-BR"),
        ("zh-hans-cn", "zh-Hans-CN"),
        ("EN", "en"),
        ("es-419", "es-419"),
        ("", ""),
    ],
)
def test_normalisation_is_canonical_bcp47(raw, canonical):
    assert normalize_locale(raw) == canonical


def test_the_offered_spelling_is_returned_not_the_canonical_one():
    """The returned code is a message directory name, so its spelling matters."""
    assert match_offered_locale("pt-br", ["pt_BR"]) == "pt_BR"


def test_the_first_offered_spelling_wins_a_normalisation_tie():
    assert match_offered_locale("pt-BR", ["pt_BR", "pt-br"]) == "pt_BR"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_vue_transcription_agrees_with_python():
    """The browser resolves a locale before Python can, so it needs its own copy."""
    run = subprocess.run(
        ["node", str(HARNESS), str(TEMPLATE), str(FIXTURE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(run.stdout) == [case["expected"] for case in CASES]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_resolution_persistence_and_remounts():
    """The markup must mark the selected row the way the script expects."""
    subprocess.run(
        ["node", str(LIFECYCLE), str(TEMPLATE)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_the_widget_sends_the_template_file():
    assert LocaleSelectWidget().template.template == TEMPLATE.read_text()


@pytest.mark.parametrize(
    "spelling", ["v-list-item-content", "v-list-item-action", "depressed", "headline", " left>"]
)
def test_markup_has_no_vuetify2_spellings(spelling):
    """Python cannot catch these: Vuetify 3 drops unknown props, removed components only warn."""
    assert spelling not in TEMPLATE.read_text().split("<script>")[0]


def test_the_selector_does_not_import_the_legacy_widgets():
    code = (
        "import sys, pysepal.solara.components.locale_select; "
        "print([m for m in sys.modules if m.split('.')[:2] == ['pysepal', 'sepalwidgets']])"
    )
    package_root = str(Path(pysepal.__file__).parents[1])
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([package_root, os.environ.get("PYTHONPATH", "")]),
    }
    run = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
    )
    assert run.stdout.strip().splitlines()[-1] == "[]"


def test_the_component_renders_the_widget_and_writes_the_locale():
    set_locale("en")
    widget, rc = solara.render_fixed(
        LocaleSelectComponent(locales=["en", "fr", "es"]), handle_error=False
    )
    try:
        assert isinstance(widget, LocaleSelectWidget)
        assert [record["code"] for record in widget.available_locales] == ["en", "fr", "es"]
        assert widget.value == current_locale() == "en"
        widget.value = "fr"
        assert current_locale() == "fr"
    finally:
        rc.close()
        set_locale("en")
