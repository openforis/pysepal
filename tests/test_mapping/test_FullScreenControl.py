"""Test the FullScreen Control."""

from pysepal import mapping as sm

# Vuetify 3 renders a Font Awesome name as is only behind the class: prefix
PREFIX = "class:"


def test_init() -> None:
    """Init a FullScreen Control."""
    # check that the map start with no info
    map_ = sm.SepalMap()

    # add a fullscreenControl
    control = sm.FullScreenControl(map_)
    map_.add(control)

    assert isinstance(control, sm.FullScreenControl)
    assert control in map_.controls
    assert control.zoomed is False
    assert f"{PREFIX}fa-solid fa-expand" in control.w_btn.children[0].children

    return


def test_toggle_fullscreen() -> None:
    """Check we can toggle the fullsxreen state."""
    map_ = sm.SepalMap()
    control = sm.FullScreenControl(map_)
    map_.add(control)

    # trigger the click
    # I cannot test the javascript but i can test everything else
    control.toggle_fullscreen(None, None, None)

    assert control.zoomed is True
    assert f"{PREFIX}fa-solid fa-compress" in control.w_btn.children[0].children

    # click again to reset to initial state
    control.toggle_fullscreen(None, None, None)

    assert control.zoomed is False
    assert f"{PREFIX}fa-solid fa-expand" in control.w_btn.children[0].children

    return
