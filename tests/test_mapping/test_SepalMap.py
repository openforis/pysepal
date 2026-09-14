"""Test the SepalMap object."""

import json
import math
import random
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import ee
import ipyvuetify as v
import pytest
from ipyleaflet import GeoJSON

from pysepal import mapping as sm
from pysepal.frontend import styles as ss
from pysepal.mapping.basemaps import basemap_tiles, xyz_tiles
from pysepal.mapping.legend_control import LegendControl
from pysepal.mapping.visualization import get_viz_params
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.sepalwidgets.vue_app import ThemeToggle
from pysepal.solara.theme import ThemeState

# create a seed so that we can check values
random.seed(42)


def test_init() -> None:
    """Init a Sepal Map."""
    # check that the map start with no info
    m = sm.SepalMap()
    id1 = m._id  # to check that the next map has another ID

    assert isinstance(m, sm.SepalMap)
    assert m.center == [0, 0]
    assert m.zoom == 3
    assert len(m.layers) == 2

    default_basemaps = ["SEPAL Dark", "SEPAL Light"]

    # Get current theme
    dark_theme = bool(v.theme.dark)

    # The basemap will change depending on the current theme.
    assert m.layers[0].name == default_basemaps[not dark_theme]

    # check that the map start with several basemaps

    # xyz_tiles keys, so that an upstream provider needing a key cannot take
    # these out of basemap_tiles the way it took CartoDB out (#1044).
    basemaps = ["ROADMAP", "TERRAIN"]
    names = [basemap_tiles[b].name for b in basemaps]
    m = sm.SepalMap(basemaps)
    assert len(m.layers) == 3
    layers_name = [layer.name for layer in m.layers]
    assert all(n in layers_name for n in names)

    # the caller's order has to survive, as only the first one is left visible
    assert layers_name[: len(names)] == names
    assert m.layers[0].visible
    assert not m.layers[1].visible

    # duplicates are dropped without disturbing that order
    m = sm.SepalMap([basemaps[1], basemaps[0], basemaps[1]])
    assert [layer.name for layer in m.layers][:2] == [names[1], names[0]]

    # check that the map start with a DC
    m = sm.SepalMap(dc=True)
    assert m._id != id1
    assert m.dc in m.controls

    # check that the map starts with a vinspector
    m = sm.SepalMap(vinspector=True)
    assert m.v_inspector in m.controls

    # check that the map start with a statebar
    m = sm.SepalMap(statebar=True)
    assert m.state in m.controls

    # check that a wrong layer raise an error if it's not part of the leaflet basemap list
    with pytest.raises(Exception):
        m = sm.SepalMap(["TOTO"])

    return


def test_theme_toggle_is_deprecated_but_still_follows_bound_theme_state() -> None:
    """Legacy theme_toggle input should warn while still honoring the bound ThemeState."""
    theme_state = ThemeState(mode="light", dark=False)
    first_toggle = ThemeToggle(theme_state=theme_state)
    with pytest.deprecated_call(match="theme_toggle"):
        m = sm.SepalMap(theme_toggle=first_toggle, gee=False)

    assert m.layers[0].name == "SEPAL Light"

    second_toggle = ThemeToggle(theme_state=theme_state)
    second_toggle.dark = True

    assert m.layers[0].name == "SEPAL Dark"

    first_toggle.dark = False
    assert m.layers[0].name == "SEPAL Light"

    return


def test_set_center() -> None:
    """Check the center can be updated."""
    m = sm.SepalMap()

    lat = random.randint(-90, 90)
    lng = random.randint(-180, 180)
    zoom = random.randint(0, 22)
    m.set_center(lng, lat, zoom)

    assert m.zoom == zoom
    assert m.center == [lat, lng]

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_zoom_ee_object() -> None:
    """Check we can zoom on a GEE object."""
    # init objects
    m = sm.SepalMap()
    ee_object = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(
        ee.Filter.eq("ADM0_NAME", "France")
    )

    # zoom without zoom out
    m.zoom_ee_object(ee_object.geometry())

    assert m.center == pytest.approx([46.5, 2.5], abs=0.5)
    assert m.zoom == 5.0

    # zoom with a zoom_out option
    m.zoom_ee_object(ee_object.geometry(), 3)

    assert m.zoom == pytest.approx(4, abs=1)

    return


def test_zoom_bounds() -> None:
    """Check we can zoom on bounds.

    When specified in the same order as in shapely bounds method.
    """
    # init objects
    m = sm.SepalMap()
    bounds = [
        45.73871293893269,  # minx
        4.9050034976367,  # miny
        45.7746437385302,  # maxx
        4.9050034976367,  # maxy
    ]

    # zoom without zoom_out
    m.zoom_bounds(bounds)

    # it works but we cannot test pure JS from here
    # assert m.zoom == 14.0

    # zoom with zoom_out
    m.zoom_bounds(bounds, 5)

    # it works but we cannot test pure JS from here
    # assert m.zoom == 10.0

    return


def test_add_raster(rgb: Path, byte: Path) -> None:
    """Add raster files to the map.

    Args:
        rgb: the path to a rgb image (3 bands)
        byte: the path to a byte image (1 band)
    """
    m = sm.SepalMap()

    # add a rgb layer to the map
    m.add_raster(rgb, layer_name="rgb")
    layer = m.find_layer("rgb")
    assert layer.name == "rgb"
    assert layer.key == "rgb"
    assert type(layer).__name__ == "BoundTileLayer"

    # add a byte layer
    m.add_raster(byte, layer_name="byte")
    layer = m.find_layer("byte")
    assert layer.name == "byte"
    assert layer.key == "byte"

    return


def test_add_colorbar() -> None:
    """Add a colorbar to the map."""
    # create a map and add a colorbar
    m = sm.SepalMap()
    m.add_colorbar(colors=["#fc8d59", "#ffffbf", "#91bfdb"], vmin=0, vmax=5)

    assert len(m.controls) == 5  # only thing I can check

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_exceptions() -> None:
    """Check exceptions are raised on ee_layer method."""
    map_ = sm.SepalMap()

    # Test add a non ee map element
    with pytest.raises(AttributeError):
        map_.addLayer({})

    # Test add a feature collection with invalid style
    geometry = ee.FeatureCollection(
        ee.Geometry.Polygon(
            [
                [
                    [-103.198046875, 36.866172202843465],
                    [-103.198046875, 34.655531078083534],
                    [-100.385546875, 34.655531078083534],
                    [-100.385546875, 36.866172202843465],
                ]
            ],
        )
    )

    with pytest.raises(TypeError):
        map_.addLayer(geometry, {"invalid_propery": "red", "fillColor": None})

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer(image_id: str) -> None:
    """Add a GEE layer on the map.

    Args:
        image_id: the AssetId of the Daniel W. image
    """
    # create map and image
    image = ee.Image(image_id)
    m = sm.SepalMap()

    # display all the viz available in the image
    for viz in get_viz_params(image, m.gee_interface).values():
        m.addLayer(image, {}, viz["name"], viz_name=viz["name"])

    assert len(m.layers) == 6

    # display an image without properties
    m = sm.SepalMap()

    dataset = ee.Image("CSP/ERGo/1_0/Global/ALOS_mTPI")
    dataset = ee.Image().addBands(dataset)  # with all bands and 0 properties
    m.addLayer(dataset)

    assert len(m.layers) == 3

    # Test with vector

    geometry = ee.FeatureCollection(
        ee.Geometry.Polygon(
            [
                [
                    [-103.198046875, 36.866172202843465],
                    [-103.198046875, 34.655531078083534],
                    [-100.385546875, 34.655531078083534],
                    [-100.385546875, 36.866172202843465],
                ]
            ],
        )
    )

    map_ = sm.SepalMap()
    map_.addLayer(geometry, {"color": "red", "fillColor": None})

    assert len(m.layers) == 3

    return


def test_get_basemap_list() -> None:
    """Every key SepalMap will accept as a basemap has to be listed.

    Named providers used to stand in for "some upstream basemaps"; xyzservices
    withdrew the whole CARTO family behind an API key in 2026.9.1 and the
    stand-ins became a failing test (#1044). The list is asserted against its
    two real sources instead.
    """
    res = sm.SepalMap.get_basemap_list()

    assert all(key in res for key in xyz_tiles)
    assert set(sm.basemaps.get_xyz_dict()) <= set(res)

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_get_viz_params(image_id: str) -> None:
    """Check I identify all the viz parameter from Daniel W. asset.

    Args:
        image_id: the AssetId of the GEE image
    """
    image = ee.Image(image_id)
    with GEEInterface() as gee_interface:
        res = get_viz_params(image, gee_interface)

    expected = {
        "1": {
            "bands": ["ndwi_phase_1", "ndwi_amplitude_1", "ndwi_rmse"],
            "max": [2.40625, 3296.0, 1792.0],
            "name": "NDWI harmonics",
            "min": [-2.1875, 352.0, 320.0],
            "type": "hsv",
            "inverted": [False, False, True],
        },
        "3": {
            "labels": ["Foo", "Bar", "Baz"],
            "bands": ["class"],
            "type": "categorical",
            "name": "Classification",
            "values": [5, 200, 1000],
            "palette": ["#042333", "#b15f82", "#e8fa5b"],
        },
        "2": {
            "bands": ["ndwi"],
            "name": "NDWI",
            "min": -8450,
            "max": 6610,
            "type": "continuous",
            "palette": [
                "#042333",
                "#2c3395",
                "#744992",
                "#b15f82",
                "#eb7958",
                "#fbb43d",
                "#e8fa5b",
            ],
        },
        "0": {
            "max": 2000,
            "type": "rgb",
            "min": 0,
            "name": "RGB",
            "gamma": 1.2,
            "bands": ["red", "green", "blue"],
        },
    }

    assert res == expected

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_remove_layer(ee_map_with_layers: sm.SepalMap) -> None:
    """Remove a specific layer from the map.

    Args:
        ee_map_with_layers: a map supporting multiple ee assets tile layer
    """
    m = ee_map_with_layers

    # remove using a layer without counting the base
    m.remove_layer(0)
    assert len(m.layers) == 5
    assert m.layers[0].base is True

    # remove when authorizing selection of bases
    m.remove_layer(0, base=True)
    assert len(m.layers) == 4
    assert len([ly for ly in m.layers if ly.base is True]) == 0
    # assert m.layers[0].name == "NDWI harmonics"

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_remove_all(ee_map_with_layers: sm.SepalMap) -> None:
    """Remove all layers from the map.

    Args:
        ee_map_with_layers: a map supporting multiple ee assets tile layer
    """
    m = ee_map_with_layers

    m.remove_all()
    assert len(m.layers) == 1

    m.remove_all(base=True)
    assert len(m.layers) == 0

    return


def test_add_layer() -> None:
    """Add geojson layer to the map."""
    m = sm.SepalMap()

    polygon = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-80.37597656249999, 25.720735134412106],
                            [-66.181640625, 18.312810846425442],
                            [-64.8193359375, 32.10118973232094],
                            [-80.37597656249999, 25.720735134412106],
                        ]
                    ],
                },
            }
        ],
    }

    # Arrange without style and requesting default hover.
    geojson = GeoJSON(data=polygon, name="geojson data")

    # Act
    m.add_layer(geojson, hover=True)

    # Assert
    new_layer = m.layers[-1]

    layer_style = json.loads((ss.JSON_DIR / "layer.json").read_text())["layer"]
    hover_style = json.loads((ss.JSON_DIR / "layer_hover.json").read_text())

    assert all([new_layer.style[k] == v for k, v in layer_style.items()])
    assert all([new_layer.hover_style[k] == v for k, v in hover_style.items()])
    assert new_layer.name == "geojson data"
    assert new_layer.key == "geojson_data"

    # Arrange with style
    layer_style = {"color": "blue"}
    layer_hover_style = {"color": "red"}
    geojson = GeoJSON(data=polygon, style=layer_style, hover_style=layer_hover_style)

    # Act
    m.add_layer(geojson)

    # Assert
    new_layer = m.layers[-1]

    assert new_layer.style == layer_style
    assert new_layer.hover_style == layer_hover_style

    return


def test_add_basemap() -> None:
    """Add a basemap to the map."""
    m = sm.SepalMap()
    m.add_basemap("HYBRID")

    assert len(m.layers) == 3
    layer = m.find_layer("Google Satellite", base=True)
    assert layer.name == "Google Satellite"
    assert layer.base is True

    # check that a wrong layer raise an error if it's not part of the leaflet basemap list
    with pytest.raises(Exception):
        m.add_basemap("TOTO")

    return


def test_get_scale():
    """Get the scale of a map."""
    m = sm.SepalMap()
    m.zoom = 5

    assert math.isclose(m.get_scale(), 4891.97)

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_find_layer(ee_map_with_layers: sm.SepalMap) -> None:
    """Find a layer in a map.

    Args:
        ee_map_with_layers: a map supporting multiple ee assets tile layer
    """
    m = ee_map_with_layers

    # search by name
    res = m.find_layer("Classification")
    assert res.name == "Classification"

    # assert the two ways of handling non existing layer
    with pytest.raises(ValueError):
        res = m.find_layer("toto")
    res = m.find_layer("toto", none_ok=True)
    assert res is None

    # search by index
    res = m.find_layer(1)
    assert res.name == "RGB"

    res = m.find_layer(-1)
    assert res.name == "Classification"

    # out of bounds
    with pytest.raises(ValueError):
        res = m.find_layer(50)

    # search by layer name
    res = m.find_layer(m.layers[3])
    assert res.name == "NDWI harmonics"

    # search by layer key
    res = m.find_layer(m.layers[3].key)
    assert res.name == "NDWI harmonics"

    # search including the basemap
    res = m.find_layer(0, base=True)
    assert "SEPAL" in res.name
    assert res.base is True

    # search something that is not a key
    with pytest.raises(ValueError):
        m.find_layer(m)

    return


def test_zoom_raster(byte: Path) -> None:
    """Check that we can zoom on a raster.

    Args:
        byte: the path to the image
    """
    m = sm.SepalMap()
    layer = m.add_raster(byte)
    m.zoom_raster(layer)

    center = [33.89703655465772, -117.63458938969723]
    assert all([math.isclose(s, t, rel_tol=0.2) for s, t in zip(m.center, center)])

    # it works but we cannot test pure JS from here
    # assert m.zoom == 15.0

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_legend(ee_map_with_layers: sm.SepalMap) -> None:
    """Add a legend to the map.

    Args:
        ee_map_with_layers: a map supporting multiple ee assets tile layer
    """
    legend_dict = {
        "forest": "#b3842e",
        "non forest": "#a1458e",
        "secondary": "#324a88",
        "success": "#3f802a",
        "info": "#79b1c9",
        "warning": "#b8721d",
    }

    ee_map_with_layers.add_legend(legend_dict=legend_dict)

    # just test that is a Legend, the rest is tested by Legend
    assert isinstance(ee_map_with_layers.legend, LegendControl)
    assert ee_map_with_layers.legend.legend_dict == legend_dict

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_autocenter_sync() -> None:
    """Test that autocenter calls zoom_bounds with expected bbox in sync add_ee_layer."""
    # Arrange
    m = sm.SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    # Mock the extent get_bounds computes for the object (per-feature-bbox, #996)
    m.gee_interface.get_bounds = MagicMock(return_value=(-180, -90, 180, 90))
    m.gee_interface.get_map_id = MagicMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test")}
    )

    # Mock zoom_bounds to track if it's called
    with patch.object(m, "zoom_bounds") as mock_zoom_bounds:
        # Act
        m.add_ee_layer(ee_object, autocenter=True, name="test_layer")

        # Assert - zoom_bounds should be called with the expected bbox
        mock_zoom_bounds.assert_called_once_with((-180, -90, 180, 90))

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
async def test_add_ee_layer_autocenter_async() -> None:
    """Test that autocenter calls zoom_bounds with expected bbox in async add_ee_layer_async."""
    # Arrange
    m = sm.SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    # Mock the extent get_bounds_async computes for the object (per-feature-bbox, #996)
    m.gee_interface.get_bounds_async = AsyncMock(return_value=(-180, -90, 180, 90))
    m.gee_interface.get_map_id_async = AsyncMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test")}
    )

    # Mock zoom_bounds to track if it's called
    with patch.object(m, "zoom_bounds") as mock_zoom_bounds:
        # Act
        await m.add_ee_layer_async(ee_object, autocenter=True, name="test_layer")

        # Assert - zoom_bounds should be called with the expected bbox
        mock_zoom_bounds.assert_called_once_with((-180, -90, 180, 90))

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_add_ee_layer_no_autocenter_sync() -> None:
    """Test that zoom_bounds is not called when autocenter=False in sync add_ee_layer."""
    # Arrange
    m = sm.SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    # Mock gee_interface methods
    m.gee_interface.get_info = MagicMock(return_value=[])
    m.gee_interface.get_map_id = MagicMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test")}
    )

    # Mock zoom_bounds to track if it's called
    with patch.object(m, "zoom_bounds") as mock_zoom_bounds:
        # Act
        m.add_ee_layer(ee_object, autocenter=False, name="test_layer")

        # Assert - zoom_bounds should NOT be called
        mock_zoom_bounds.assert_not_called()

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
@pytest.mark.asyncio
async def test_add_ee_layer_no_autocenter_async() -> None:
    """Test that zoom_bounds is not called when autocenter=False in async add_ee_layer_async."""
    # Arrange
    m = sm.SepalMap()
    ee_object = ee.Geometry.Rectangle([-180, -90, 180, 90])

    # Mock gee_interface async methods
    m.gee_interface.get_info_async = AsyncMock(return_value=[])
    m.gee_interface.get_map_id_async = AsyncMock(
        return_value={"tile_fetcher": MagicMock(url_format="http://test")}
    )

    # Mock zoom_bounds to track if it's called
    with patch.object(m, "zoom_bounds") as mock_zoom_bounds:
        # Act
        await m.add_ee_layer_async(ee_object, autocenter=False, name="test_layer")

        # Assert - zoom_bounds should NOT be called
        mock_zoom_bounds.assert_not_called()

    return


@pytest.fixture(scope="function")
def ee_map_with_layers(image_id: str) -> sm.SepalMap:
    """A sepalMap supporting each combo band from the asset."""
    image = ee.Image(image_id)
    m = sm.SepalMap()

    # display all the viz available in the image
    for viz in get_viz_params(image, m.gee_interface).values():
        m.addLayer(image, {}, viz["name"], viz_name=viz["name"])

    return m
