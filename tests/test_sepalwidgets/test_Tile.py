"""Test the different Tile widgets."""

from pathlib import Path

import ipyvuetify as v

from pysepal import sepalwidgets as sw
from pysepal.sepalwidgets.vue_app import ThemeToggle


def test_init() -> None:
    """Check the widget init."""
    # default init
    id_ = "id"
    title = "title"
    tile = sw.Tile(id_, title)

    assert isinstance(tile, sw.Tile)
    assert tile.children[0].children[0].children[0] == title
    assert len(tile.children[0].children) == 2

    # exhaustive
    btn = sw.Btn()
    alert = sw.Alert()
    tile = sw.Tile(id_, title, [""], btn, alert)
    assert isinstance(tile, sw.Tile)
    assert len(tile.children[0].children) == 4

    return


def test_set_content() -> None:
    """Check content can be set from a method."""
    id_ = "id"
    title = "title"
    tile = sw.Tile(id_, title, alert=sw.Alert(), btn=sw.Btn())

    input_ = v.Slider()

    res = tile.set_content([input_])

    assert res == tile
    assert tile.children[0].children[0].children[0] == title
    assert tile.children[0].children[1].children[0] == input_

    return


def test_set_title() -> None:
    """Check title can be set from a method."""
    id_ = "id"
    title = "title"
    input_ = v.Slider()
    tile = sw.Tile(id_, title, [input_])

    # add a title
    title2 = "title2"
    res = tile.set_title(title2)

    assert res == tile
    assert tile.children[0].children[0].children[0] == title2
    assert tile.children[0].children[1].children[0] == input_

    # remove a title
    res = tile.set_title()
    assert res == tile
    assert tile.children[0].children[0].children[0] == input_

    # add a title after removing it
    res = tile.set_title(title2)
    assert tile.children[0].children[0].children[0] == title2
    assert tile.children[0].children[1].children[0] == input_

    return


def test_nest() -> None:
    """Check tile can be nested."""
    id_ = "id"
    title = "title"
    input_ = v.Slider()
    tile = sw.Tile(id_, title, [input_])

    # nest the tile
    res = tile.nest()

    assert res == tile
    assert tile._metadata["mount_id"] == "nested_tile"
    assert tile.children[0].elevation == 0
    assert len(tile.children[0].children) == 1

    return


def test_hide() -> None:
    """Check TIle can be hidden."""
    id_ = "id"
    title = "title"
    tile = sw.Tile(id_, title)

    res = tile.hide()

    assert res == tile
    assert tile.viz is False
    assert "d-inline" not in tile.class_

    return


def test_show() -> None:
    """Check Tile can be shown."""
    id_ = "id"
    title = "title"
    tile = sw.Tile(id_, title).hide()

    res = tile.show()

    assert res == tile
    assert tile.viz is True
    assert "d-inline" in tile.class_

    return


def test_toggle_inputs() -> None:
    """Check inputs can be shown alternatively."""
    inputs = []
    for i in range(5):
        inputs.append(v.Slider())

    input_2_show = v.Slider()
    inputs.append(input_2_show)

    id_ = "id"
    title = "title"
    tile = sw.Tile(id_, title, inputs)

    res = tile.toggle_inputs([input_2_show], inputs)

    assert res == tile

    for input_ in inputs:
        if input_ == input_2_show:
            assert "d-none" not in str(input_.class_)
        else:
            assert "d-none" in input_.class_

    return


def test_get_id() -> None:
    """Check id can be retrieved."""
    id_ = "id"
    tile = sw.Tile(id_, "title", [""])

    assert tile.get_id() == id_

    return


def test_tile_about() -> None:
    """Check the init of the special cased About Tile."""
    pathname = Path(__file__).parents[2] / "CODE_OF_CONDUCT.md"

    tile = sw.TileAbout(pathname)

    assert isinstance(tile, sw.TileAbout)
    assert tile._metadata["mount_id"] == "about_tile"

    # check with str path
    tile = sw.TileAbout(str(pathname))

    assert isinstance(tile, sw.TileAbout)
    assert tile._metadata["mount_id"] == "about_tile"

    return


def test_tile_disclaimer() -> None:
    """Check init of the special cased Disclaimer tile."""
    tile = sw.TileDisclaimer()

    assert isinstance(tile, sw.TileDisclaimer)
    assert tile._metadata["mount_id"] == "about_tile"

    return


def test_a_closed_disclaimer_stops_following_its_theme_toggle() -> None:
    """The toggle keeps the bound method, and that holds the tile."""
    theme_toggle = ThemeToggle()
    tile = sw.TileDisclaimer(theme_toggle=theme_toggle)

    tile.close()

    observers = theme_toggle._trait_notifiers.get("dark", {}).get("change", [])
    assert not [h for h in observers if getattr(h, "__self__", None) is tile]
