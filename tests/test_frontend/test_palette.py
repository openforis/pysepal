"""Test that the pysepal palette reaches the ipyvuetify theme."""

import ipyvuetify as v
from ipyvuetify.Themes import Themes

from pysepal.frontend import styles


def test_palettes_carry_every_pysepal_colour() -> None:
    """Check that both palettes name the same 14 colours, including the contrasts."""
    assert set(styles.DARK_THEME) == set(styles.LIGHT_THEME) == set(styles.TYPES)
    assert styles.DARK_THEME["primary_contrast"] == "#bf8f2d"
    assert styles.LIGHT_THEME["error"] == "#FF5252"


def test_apply_palette_sets_surface_and_custom_colors() -> None:
    """Check the spelling: standard traits plus custom colours."""
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


def test_import_applies_the_palette_to_the_global_theme() -> None:
    assert v.theme.themes.dark.custom_theme_colors["bg"] == "#121212"
    assert not hasattr(styles, "ThemeColors")


def test_setup_theme_colors_does_not_raise() -> None:
    """Check that ``setup_theme_colors`` writes the palette to Solara's theme."""
    import solara

    from pysepal.solara import setup_theme_colors

    setup_theme_colors()
    assert solara.lab.theme.themes.dark.primary == "#76591e"
