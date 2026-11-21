"""The map controls build on the Vuetify 3 widgets."""

import ipyleaflet as ipl

from pysepal import mapping as sm


def test_sepal_map_builds() -> None:
    """A map with its base controls builds, with ipyleaflet's own zoom and fullscreen."""
    m = sm.SepalMap(gee=False, fullscreen_control=True)

    controls = {type(c) for c in m.controls}
    assert {ipl.ZoomControl, ipl.FullScreenControl} <= controls

    # the map btn shows an outlined small icon
    btn = sm.MapBtn("fa-solid fa-plus")
    assert btn.variant == "outlined"
    assert btn.children[0].size == "small"
    assert btn.hide() is btn and btn.viz is False

    m.close()
