"""Test the custom EELayer TileLayer."""

import ee
import pytest

from pysepal import mapping as sm


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_init() -> None:
    """Init a EELyer and check members."""
    # create a point gee layer (easier to check)
    m = sm.SepalMap()
    ee_point = ee.FeatureCollection(ee.Geometry.Point(0, 0))
    m.addLayer(ee_point, {}, "point")

    layer = m.find_layer("point")
    assert isinstance(layer, sm.EELayer)
    # rebuilt from the layer spec: the same expression, not the same object
    assert ee.serializer.toJSON(layer.ee_object) == ee.serializer.toJSON(ee_point)

    return
