"""Test the Inspector Control."""

import math
from pathlib import Path

import ee
import geopandas as gpd
import pytest

from pysepal import mapping as sm


def test_init() -> None:
    """Init the inspector control."""
    m = sm.SepalMap()
    inspector_control = sm.InspectorControl(m)
    m.add(inspector_control)

    assert isinstance(inspector_control, sm.InspectorControl)

    return


def test_deprecated() -> None:
    """Check deprecation notice."""
    m = sm.SepalMap()
    with pytest.deprecated_call():
        inspector_control = sm.ValueInspector(m)
    m.add(inspector_control)

    assert isinstance(inspector_control, sm.InspectorControl)

    return


def test_toogle_cursor() -> None:
    """Toggle cursor when activated."""
    m = sm.SepalMap()
    inspector_control = sm.InspectorControl(m)
    m.add(inspector_control)

    # activate the window
    inspector_control.menu.v_model = True
    assert m.default_style.cursor == "crosshair"

    # close with the menu
    inspector_control.menu.v_model = False
    assert m.default_style.cursor == "grab"

    return


def test_read_data() -> None:
    """Check the infuence of activation on control behaviour."""
    # not testing the display of anything here just the interaction
    m = sm.SepalMap()
    inspector_control = sm.InspectorControl(m)
    m.add(inspector_control)

    # click anywhere without activation
    inspector_control.read_data(type="click", coordinates=[0, 0])
    assert len(inspector_control.text.children) == 1

    # click when activated
    inspector_control.menu.v_model = True
    inspector_control.read_data(type="click", coordinates=[0, 0])
    assert len(inspector_control.text.children) == 4

    return


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_free_eelayer(world_temp: ee.imagecollection, ee_adm2: ee.FeatureCollection) -> None:
    """Check result when clicking on a ee object.

    Args:
        world_temp: the imagecollection of the world temperature dataset
        ee_adm2: the vectors of the administrative boundaries of level 2
    """
    # _from_eelayer samples at the map's zoom, so pin it rather than inherit the
    # default: the expected values below are only meaningful at one resolution.
    m = sm.SepalMap(zoom=2, min_zoom=2)
    inspector_control = sm.InspectorControl(m)

    # check a nodata place on Image
    data = inspector_control._from_eelayer(world_temp.mosaic(), [0, 0])
    assert data == {"temperature_2m": None}

    # check vatican city
    data = inspector_control._from_eelayer(world_temp.mosaic(), [12.457, 41.902])
    assert data == {"temperature_2m": 296.00286865234375}

    # check a featurecollection on nodata place
    data = inspector_control._from_eelayer(ee_adm2, [0, 0])
    assert data == {"ADM2_CODE": None}

    # check the featurecollection on vatican city
    data = inspector_control._from_eelayer(ee_adm2, [12.457, 41.902])
    assert data == {"ADM2_CODE": 18350}

    return


def test_from_geojson(adm0_vatican: dict) -> None:
    """Check the result of clicking on a geojson.

    Args:
        adm0_vatican: the geo_interface of the vatican
    """
    # create a map with a value inspector
    m = sm.SepalMap()
    inspector_control = sm.InspectorControl(m)

    # check a featurecollection on nodata place
    data = inspector_control._from_geojson(adm0_vatican, [0, 0])
    assert data == {"GID_0": None, "COUNTRY": None}

    # check the featurecollection on vatican city
    data = inspector_control._from_geojson(adm0_vatican, [12.457, 41.902])
    assert data == {"GID_0": "VAT", "COUNTRY": "VaticanCity"}

    return


def test_from_raster(rgb: Path) -> None:
    """Check the result of clicking on a raster.

    Args:
        rgb: the path of a raster image
    """
    # _from_raster samples at the map's zoom, so pin it rather than inherit the
    # default: the expected value below is only meaningful at one resolution.
    m = sm.SepalMap(zoom=2, min_zoom=2)
    inspector_control = sm.InspectorControl(m)

    # check a featurecollection on nodata place
    data = inspector_control._from_raster(rgb, [0, 0])
    assert data == {"band 1": None, "band 2": None, "band 3": None}

    # check the featurecollection on vatican city
    data = inspector_control._from_raster(rgb, [-78.072, 24.769])
    assert math.isclose(data["band 1"], 70.46553, rel_tol=1e-5)
    assert math.isclose(data["band 2"], 91.41595, rel_tol=1e-5)
    assert math.isclose(data["band 3"], 93.08673, rel_tol=1e-5)

    return


@pytest.fixture(scope="module")
def world_temp() -> ee.ImageCollection:
    """Get the world temperature dataset from GEE.

    Returns:
        the filtered temperature_2m band
    """
    return (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .filter(ee.Filter.date("2020-07-01", "2020-07-02"))
        .select("temperature_2m")
    )


@pytest.fixture(scope="module")
def ee_adm2() -> ee.FeatureCollection:
    """Get a featurecollection with only adm2code values.

    Returns:
        the adm2 names of FAO GAUL
    """
    return ee.FeatureCollection("FAO/GAUL/2015/level2").select("ADM2_CODE")


@pytest.fixture(scope="module")
def adm0_vatican(fake_vector: Path) -> dict:
    """Create a geojson of vatican city.

    Args:
        fake_vector: the path to the vatican vector file

    Returns:
        the geo_interface of vatican city
    """
    return gpd.read_file(fake_vector).__geo_interface__
