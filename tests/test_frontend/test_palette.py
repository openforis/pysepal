"""Test that the pysepal palette reaches the theme on both ipyvuetify majors."""

import ipyvuetify as v
import pytest
from ipyvuetify.Themes import Themes

from pysepal._vuetify import IPYVUETIFY_V3
from pysepal.frontend import styles

v2_only = pytest.mark.skipif(IPYVUETIFY_V3, reason="Vuetify 2 colour model")
v3_only = pytest.mark.skipif(not IPYVUETIFY_V3, reason="Vuetify 3 colour model")


def test_palettes_carry_every_pysepal_colour() -> None:
    """Check that both palettes name the same 14 colours, including the contrasts."""
    assert set(styles.DARK_THEME) == set(styles.LIGHT_THEME) == set(styles.TYPES)
    assert styles.DARK_THEME["primary_contrast"] == "#bf8f2d"
    assert styles.LIGHT_THEME["error"] == "#FF5252"


@v2_only
def test_apply_palette_v2_writes_every_name() -> None:
    """Check that Vuetify 2 gets every colour as an attribute."""
    themes = Themes()
    styles.apply_palette(themes)

    for name, value in styles.DARK_THEME.items():
        assert getattr(themes.dark, name) == value
    for name, value in styles.LIGHT_THEME.items():
        assert getattr(themes.light, name) == value


@v2_only
def test_import_v2_swaps_in_the_pysepal_colour_model() -> None:
    """Check that Vuetify 2 still syncs the custom names through pysepal's model."""
    assert isinstance(v.theme.themes.dark, styles.ThemeColors)
    assert v.theme.themes.dark.menu == "#424242"


@v3_only
def test_apply_palette_v3_sets_surface_and_custom_colors() -> None:
    """Check the Vuetify 3 spelling: standard traits plus custom colours."""
    themes = Themes()
    styles.apply_palette(themes)

    dark = themes.dark
    assert dark.primary == "#76591e"
    assert dark.primary_darken_1 == "#76591e"
    assert dark.background == "#121212"
    assert dark.surface == "#1E1E1E"
    assert dark.custom_theme_colors["menu"] == "#424242"
    assert dark.custom_theme_colors["primary-contrast"] == "#bf8f2d"
    assert dark.custom_theme_colors["accent"] == "#272727"
    assert "primary" not in dark.custom_theme_colors

    assert themes.light.error == "#FF5252"
    assert themes.light.surface == "#FFFFFF"


@v3_only
def test_import_v3_keeps_the_ipyvuetify_colour_model() -> None:
    """Check that the Vuetify 2 shaped model never reaches a Vuetify 3 frontend."""
    assert not isinstance(v.theme.themes.dark, styles.ThemeColors)
    assert v.theme.themes.dark.custom_theme_colors["bg"] == "#121212"


def test_setup_theme_colors_does_not_raise() -> None:
    """Check that ``setup_theme_colors`` runs on the installed major."""
    import solara

    from pysepal.solara import setup_theme_colors

    setup_theme_colors()
    assert solara.lab.theme.themes.dark.primary == "#76591e"
