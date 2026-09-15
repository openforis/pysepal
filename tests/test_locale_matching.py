"""The one locale algorithm: normalisation and offered-code matching."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import pysepal
from pysepal._locale import match_offered_locale, normalize_locale

FIXTURE = Path(__file__).parent / "fixtures" / "locale_matching.json"
CASES = json.loads(FIXTURE.read_text())
VUE = Path(pysepal.__file__).parent / "sepalwidgets" / "vue" / "LocaleSelect.vue"
HARNESS = Path(__file__).parent / "js" / "locale_parity.mjs"


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
        ["node", str(HARNESS), str(VUE), str(FIXTURE)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(run.stdout) == [case["expected"] for case in CASES]
