"""The map and its buttons build on the Vuetify 3 widgets."""

from pysepal import mapping as sm


def test_sepal_map_builds() -> None:
    """A map shows the zoom, scale and, when asked, fullscreen controls the widget draws."""
    m = sm.SepalMap(gee=False, fullscreen_control=True)

    assert m.state["controls"] == {
        "zoom": True,
        "fullscreen": True,
        "scale": True,
        "coordinates": False,
    }

    # the map btn shows an outlined small icon
    btn = sm.MapBtn("fa-solid fa-plus")
    assert btn.variant == "outlined"
    assert btn.children[0].size == "small"
    assert btn.hide() is btn and btn.viz is False

    m.close()
