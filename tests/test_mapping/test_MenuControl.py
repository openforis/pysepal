"""Test the Menu Control."""

import ipyvuetify as v
import pytest

from pysepal import mapping as sm
from pysepal._vuetify import IPYVUETIFY_V3

# the legacy Tile is nested by the menu, it is built on pysepal.sepalwidgets
legacy = pytest.mark.skipif(IPYVUETIFY_V3, reason="pysepal.sepalwidgets needs ipyvuetify 1")


@legacy
def test_init() -> None:
    """Init a menu control."""
    from pysepal import sepalwidgets as sw

    # create a tile
    tile = sw.Tile("toto", "tutu", inputs=[sw.Slider()], btn=sw.Btn(), alert=sw.Alert().show())

    # create the menu_control
    m = sm.SepalMap()
    tile_control = sm.MenuControl("tutu", tile)
    m.add(tile_control)

    # set some object in variables for easy access
    btn = tile_control.widget.v_slots[0]["children"]
    title = tile_control.widget.children[0].children[0]

    # assert all the styling
    assert tile_control in m.controls
    assert tile_control.position == "bottomright"
    assert btn.children[0] == "TUT"
    assert title.children[0] == "tutu"
    assert "ma-0" in tile.class_
    assert "pa-2" in tile.children[0].class_
    assert tile.children[0].raised is False
    assert tile.get_title() == ""
    assert tile.children[0].elevation == 0

    return


@pytest.mark.skipif(IPYVUETIFY_V3, reason="Vuetify 2 positions a menu with flags")
def test_update_position() -> None:
    """Update the position dynamically."""
    # create the widget
    menu_control = sm.MenuControl("fa-solid fa-folder", v.Card())

    assert menu_control.menu.top is True
    assert menu_control.menu.bottom is False
    assert menu_control.menu.left is True
    assert menu_control.menu.right is False

    # change the position
    menu_control.position = "topleft"

    assert menu_control.menu.top is False
    assert menu_control.menu.bottom is True
    assert menu_control.menu.left is False
    assert menu_control.menu.right is True

    return


@pytest.mark.skipif(not IPYVUETIFY_V3, reason="Vuetify 3 positions a menu with location")
def test_update_position_location() -> None:
    """Open the menu beside the btn, towards the centre of the map."""
    menu_control = sm.MenuControl("fa-solid fa-folder", v.Card())
    assert menu_control.menu.location == "left bottom"

    expected = {
        "topleft": "right top",
        "topright": "left top",
        "bottomleft": "right bottom",
        "bottomright": "left bottom",
    }
    for position, location in expected.items():
        menu_control.position = position
        assert menu_control.menu.location == location

    return


def test_menu_control_activator() -> None:
    """The btn opens the menu through the activator slot of the installed major."""
    card = v.Card()
    menu_control = sm.MenuControl("fa-solid fa-folder", card, card_title="title")
    slot = menu_control.menu.v_slots[0]
    btn = slot["children"]

    assert slot["name"] == "activator"
    assert slot["variable"] == "menu"
    assert isinstance(btn, sm.MapBtn)
    if IPYVUETIFY_V3:
        assert btn.v_bind == "menu.props"
        assert btn.v_on is None
        assert not menu_control.menu.has_trait("offset_x")
    else:
        assert btn.v_on == "menu.on"
        assert menu_control.menu.offset_x is True

    # the caller content sits below the title, in the card of the menu
    content = menu_control.menu.children[0].children
    assert content[0].children == ["title"]
    assert content[1] is card

    return


def test_close_others() -> None:
    """Check that other controls are closed when another of the same group is opened."""
    # add controls on the map
    m = sm.SepalMap()
    control_1 = sm.MenuControl("fa-solid fa-folder", v.Card(), m=m)
    control_2 = sm.MenuControl("fa-solid fa-folder", v.Card(), m=m)
    control_3 = sm.MenuControl("fa-solid fa-folder", v.Card())
    control_4 = sm.MenuControl("fa-solid fa-folder", v.Card(), m=m, group=1)
    m.add(control_1)
    m.add(control_2)
    m.add(control_3)
    m.add(control_4)

    # open the first one and then the second one
    control_1.menu.v_model = True
    control_2.menu.v_model = True
    control_3.menu.v_model = False

    # check the values
    assert control_1.menu.v_model is False
    assert control_2.menu.v_model is True
    assert control_3.menu.v_model is False
    assert control_4.menu.v_model is False

    # use the control that has no map
    control_3.menu.v_model = True

    assert control_1.menu.v_model is False
    assert control_2.menu.v_model is True
    assert control_3.menu.v_model is True
    assert control_4.menu.v_model is False

    # use the control that has no map
    control_3.menu.v_model = False
    control_2.menu.v_model = True
    control_4.menu.v_model = True

    assert control_1.menu.v_model is False
    assert control_2.menu.v_model is True
    assert control_3.menu.v_model is False
    assert control_4.menu.v_model is True

    return


def test_fullscreen() -> None:
    """Check if the fullscreen display of a menu."""
    # create the menu_control
    tile = v.Card(children=[v.Slider()])
    m = sm.SepalMap()
    tile_control = sm.MenuControl("tutu", tile, fullscreen=True)
    m.add(tile_control)

    # check the class as it's the only thing that changes
    card = tile_control.menu.children[0]
    assert "v-menu-fullscreen" in card.class_
    assert card.min_width is None
    assert card.max_width is None
    assert card.min_height is None
    assert card.max_height is None

    return


def test_activate() -> None:
    """Check that activating the menu changes the color of the button."""
    # create the menu_control
    tile = v.Card(children=[v.Slider()])
    m = sm.SepalMap()
    tile_control = sm.MenuControl("tutu", tile, fullscreen=True)
    m.add(tile_control)

    # use a variable that point to the btn style
    btn = tile_control.menu.v_slots[0]["children"]

    # open the controls
    tile_control.menu.v_model = True
    assert btn.style_ == "background: gray;"

    # close the controls
    tile_control.menu.v_model = False
    assert btn.style_ == ""

    return
