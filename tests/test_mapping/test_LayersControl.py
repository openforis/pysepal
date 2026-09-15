"""Test the custom Layer Control."""

import ee
import pytest
from ipyleaflet import Map, Marker, PMTilesLayer

from pysepal import aoi
from pysepal import mapping as sm
from pysepal import sepalwidgets as sw
from pysepal.mapping.basemaps import basemap_tiles


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_init() -> None:
    """Check the init of a layer control on a standard map."""
    # create a map with 1 layer (the basemap)
    m = sm.SepalMap()
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    assert isinstance(layer_control.tile.children[0], sw.RadioGroup)

    layer_rows = layer_control.tile.get_children(klass=sm.LayerRow)
    base_rows = layer_control.tile.get_children(klass=sm.BaseRow)
    vector_rows = layer_control.tile.get_children(klass=sm.VectorRow)

    assert len(vector_rows) == 0
    assert len(layer_rows) == 0
    assert len(base_rows) == 1
    assert "SEPAL" in base_rows[0].children[0].children[0]

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_layer() -> None:
    """Check that adding a layer refresh the layer control."""
    m = sm.SepalMap()
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))

    # add layers
    min, max = 2010, 2014
    for year in range(min, max):
        layer = (
            ee.ImageCollection("NOAA/DMSP-OLS/NIGHTTIME_LIGHTS")
            .filter(ee.Filter.date(f"{year}-01-01", f"{year}-12-31"))
            .select("avg_vis")
        )
        m.add_ee_layer(layer, {}, f"{year}")
    layer_rows = layer_control.tile.get_children(klass=sm.LayerRow)

    for i, year in enumerate(range(max - 1, min + 1, -1)):
        assert layer_rows[i].children[0].children[0] == f"{year}"
        assert layer_rows[i].w_slider.v_model == 1
        assert layer_rows[i].w_checkbox.v_model is True

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_basemaps() -> None:
    """Check that multiple basempas can be displayed at the same time."""
    m = sm.SepalMap()
    m.add_basemap("HYBRID")
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))

    layer_rows = layer_control.tile.get_children(klass=sm.LayerRow)
    base_rows = layer_control.tile.get_children(klass=sm.BaseRow)

    assert len(layer_rows) == 0
    assert len(base_rows) == 2
    assert "SEPAL" in base_rows[0].children[0].children[0]
    assert "Google Satellite" in base_rows[1].children[0].children[0]

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_change_alpha() -> None:
    """Check that alpha channel can be changed."""
    m = sm.SepalMap()
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    data = (
        ee.ImageCollection("NOAA/DMSP-OLS/NIGHTTIME_LIGHTS")
        .filter(ee.Filter.date("2010-01-01", "2010-12-31"))
        .select("avg_vis")
    )
    m.add_ee_layer(data, {}, "2010")
    layer_row = layer_control.tile.get_children(klass=sm.LayerRow)[0]
    layer = m.find_layer("2010")

    # change the alpha from the slider
    layer_row.w_slider.v_model = 0.5
    assert layer.opacity == 0.5

    # change the alpha from the layer
    layer.opacity = 0.8
    assert layer_row.w_slider.v_model == 0.8

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_select() -> None:
    """Check that layers can be selected and deselected preserving the alpha value."""
    m = sm.SepalMap()
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    data = (
        ee.ImageCollection("NOAA/DMSP-OLS/NIGHTTIME_LIGHTS")
        .filter(ee.Filter.date("2010-01-01", "2010-12-31"))
        .select("avg_vis")
    )
    m.add_ee_layer(data, {}, "2010")
    layer_row = layer_control.tile.get_children(klass=sm.LayerRow)[0]
    layer_row.w_slider.v_model = 0.5
    layer = m.find_layer("2010")

    # make it invisible
    layer_row.w_checkbox.v_model = False
    assert layer_row.w_slider.v_model == 0.5
    assert layer.visible is False

    # set back the visibility
    layer_row.w_checkbox.v_model = True
    assert layer_row.w_slider.v_model == 0.5
    assert layer.visible is True

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_change_basemap() -> None:
    """Check that besmap can be changed and that user can select 2 at a time."""
    terrain_name = basemap_tiles["TERRAIN"].name
    m = sm.SepalMap(["HYBRID", "TERRAIN"])
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    layer_rows = layer_control.tile.get_children(klass=sm.BaseRow)
    terrain_row = next(r for r in layer_rows if r.children[0].children[0] == terrain_name)
    google_row = next(r for r in layer_rows if r.children[0].children[0] == "Google Satellite")
    terrain_layer = m.find_layer(terrain_name, base=True)
    google_layer = m.find_layer("Google Satellite", base=True)

    # select terrain (their initial order is random)
    terrain_row.w_radio.active = True
    assert google_row.w_radio.active is False
    assert google_layer.visible is False
    assert terrain_layer.visible is True

    # select google
    google_row.w_radio.active = True
    assert terrain_row.w_radio.active is False
    assert google_layer.visible is True
    assert terrain_layer.visible is False

    # do it from the layers
    terrain_layer.visible = True
    assert google_row.w_radio.active is False
    assert terrain_row.w_radio.active is True
    assert google_layer.visible is False

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_ungrouped() -> None:
    """Check that layer control can be displayed at the same time with other menus."""
    m = sm.SepalMap(["HYBRID", "TERRAIN"], vinspector=True)
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    m.v_inspector.menu.v_model = True

    # open the layer_control
    layer_control.menu.v_model = True
    assert m.v_inspector.menu.v_model is True

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_vectors() -> None:
    """Check that vectors are grouped together and they can be controlled."""
    m = sm.SepalMap()
    m.add_layer(aoi.AoiModel(admin="171").get_ipygeojson())
    aoi_layer = m.find_layer("aoi")
    layer_control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    vector_rows = layer_control.tile.get_children(klass=sm.VectorRow)
    vector_row = vector_rows[0]

    assert len(vector_rows) == 1

    # set visibility from the btn
    vector_row.w_checkbox.v_model = False
    assert aoi_layer.visible is False

    # set the visibility from the layer
    aoi_layer.visible = True
    assert vector_row.w_checkbox.v_model is True

    return


def _pmtiles(name: str) -> PMTilesLayer:
    """Return a PMTiles layer, which owns no visible trait."""
    return PMTilesLayer(name=name, url=f"https://example.com/{name}.pmtiles")


def test_toggle_row_keeps_its_position() -> None:
    """Check that hiding a layer does not move its row under the user's cursor."""
    m = Map()
    layer_control = sm.LayersControl(m)
    m.add(_pmtiles("first"))
    m.add(_pmtiles("second"))

    def row_names() -> list:
        return [r.layer.name for r in layer_control.tile.get_children(klass=sm.ToggleRow)]

    def row(name: str):
        return next(
            r for r in layer_control.tile.get_children(klass=sm.ToggleRow) if r.layer.name == name
        )

    assert row_names() == ["second", "first"]

    # hiding must leave the row exactly where it was
    row("second").w_checkbox.v_model = False
    assert row_names() == ["second", "first"]

    # and a layer added meanwhile must not displace it either
    m.add(_pmtiles("third"))
    assert row_names() == ["second", "third", "first"]

    row("second").w_checkbox.v_model = True
    assert row_names() == ["second", "third", "first"]

    return


def test_toggle_row() -> None:
    """Check that a layer exposing no visible trait still gets a row."""
    m = Map()
    layer_control = sm.LayersControl(m)
    m.add(PMTilesLayer(name="pmtiles", url="https://example.com/tiles.pmtiles"))

    rows = layer_control.tile.get_children(klass=sm.ToggleRow)

    assert len(rows) == 1
    assert rows[0].w_checkbox.v_model is True

    return


def test_toggle_row_skips_linkable_layers() -> None:
    """Check that a layer owning a visible trait is left out of the toggle rows."""
    m = Map()
    layer_control = sm.LayersControl(m)

    # a Marker is neither a GeoJSON nor a TileLayer but it can still be linked,
    # and SepalMap ships one by default so it must not show up as a blank row
    m.add(Marker(location=(0, 0)))

    assert len(layer_control.tile.get_children(klass=sm.ToggleRow)) == 0

    return


def test_toggle_layer() -> None:
    """Check that such a layer is hidden by removing it from the map."""
    m = Map()
    layer_control = sm.LayersControl(m)
    layer = PMTilesLayer(name="pmtiles", url="https://example.com/tiles.pmtiles")
    m.add(layer)

    # hiding drops it from the map but the row must survive to switch it back on
    layer_control.tile.get_children(klass=sm.ToggleRow)[0].w_checkbox.v_model = False
    rows = layer_control.tile.get_children(klass=sm.ToggleRow)
    assert layer not in m.layers
    assert len(rows) == 1
    assert rows[0].w_checkbox.v_model is False

    rows[0].w_checkbox.v_model = True
    assert layer in m.layers
    assert len(layer_control.tile.get_children(klass=sm.ToggleRow)) == 1

    return
