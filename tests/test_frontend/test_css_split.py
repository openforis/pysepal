"""Guards for the shared/base CSS split.

pysepal ships one shared stylesheet (``frontend/css/base.css``) consumed by
BOTH runtimes: the ipyvuetify/Voila runtime (injected by
``frontend.styles.get_custom_css``) and the Solara runtime (merged in by
``asset_merger``). Only rules that must differ per runtime live in the thin
override files (``frontend/css/custom.css`` for Voila,
``solara/common/assets/custom.css`` for Solara).

These tests pin the split so the two sheets cannot silently drift apart again
(the historical failure mode: PR #968 forked a copy, later one-sided edits
diverged them, and parity had to be chased by hand).
"""

from pathlib import Path

import pysepal.frontend.styles as ss
import pysepal.solara as solara_pkg
from pysepal.solara.asset_merger import create_merged_assets_directory

BASE_CSS = ss.CSS_DIR / "base.css"
SOLARA_COMMON_ASSETS = Path(solara_pkg.__file__).parent / "common" / "assets"

# Representative rules that MUST be present in both runtimes (they live in base).
SHARED_SELECTORS = [
    ".leaflet-center",
    ".leaflet-pm-toolbar",  # geoman toolbar block
    ".right-panel .drawer-top .v-sheet",
    "header.v-app-bar",
    ".solara-markdown.jp-RenderedHTMLCommon",
]

# Deliberately Voila-only. `.v-menu__content` z-index was forked off for Solara
# in PR #968; `main.v-content` was only ever in the Voila sheet. None of these
# may leak into the shared base or the Solara sheet.
VOILA_ONLY_MARKERS = ["z-index: 902", "main.v-content"]


def _voila_css() -> str:
    """Effective stylesheet injected under ipyvuetify/Voila."""
    return ss.get_custom_css()


def _solara_css() -> str:
    """Effective stylesheet served under Solara (base merged with overrides)."""
    merged = create_merged_assets_directory(SOLARA_COMMON_ASSETS, [], base_css_files=[BASE_CSS])
    return (merged / "custom.css").read_text()


def test_base_css_holds_shared_rules_without_runtime_overrides() -> None:
    base = BASE_CSS.read_text()
    for selector in SHARED_SELECTORS:
        assert selector in base, f"shared rule {selector!r} missing from base.css"
    for marker in VOILA_ONLY_MARKERS:
        assert marker not in base, f"runtime-only rule {marker!r} leaked into base.css"


def test_voila_stylesheet_includes_base_and_voila_only_rules() -> None:
    css = _voila_css()
    for selector in SHARED_SELECTORS:
        assert selector in css, f"Voila sheet dropped shared rule {selector!r}"
    for marker in VOILA_ONLY_MARKERS:
        assert marker in css, f"Voila sheet dropped its own rule {marker!r}"


def test_solara_stylesheet_includes_base_but_excludes_voila_only_rules() -> None:
    css = _solara_css()
    for selector in SHARED_SELECTORS:
        assert selector in css, f"Solara sheet dropped shared rule {selector!r}"
    for marker in VOILA_ONLY_MARKERS:
        assert marker not in css, f"Voila-only rule {marker!r} leaked into Solara sheet"


def test_markdown_color_rule_is_shared_once() -> None:
    """Markdown takes its container's color (e.g. an alert's) in both runtimes (#1094)."""
    rule = ".solara-markdown.jp-RenderedHTMLCommon,"
    assert BASE_CSS.read_text().count(rule) == 1
    assert rule not in (ss.CSS_DIR / "custom.css").read_text()
    assert rule not in (SOLARA_COMMON_ASSETS / "custom.css").read_text()
    for css in (_voila_css(), _solara_css()):
        assert css.count(rule) == 1
