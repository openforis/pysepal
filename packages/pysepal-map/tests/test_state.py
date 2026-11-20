import json
from pathlib import Path

import pytest

from pysepal_map import (
    Basemap,
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)

FIXTURE = Path(__file__).parents[1] / "js" / "test" / "fixtures" / "state.json"
EMPTY = b'{"type":"FeatureCollection","features":[]}'


def raster(**kw):
    return Layer("r", RasterSource(("https://r/{z}/{x}/{y}.png",)), **kw)


def test_to_json_matches_the_contract_fixture():
    widget = MapWidget()
    digest = widget.add_payload(EMPTY)
    widget.draw(
        MapState(
            layers=(
                Layer("v1", GeoJSONSource(digest), token=3),
                Layer("pm", PMTilesSource("https://x.org/a.pmtiles", "roads"), token=1),
                Layer(
                    "r1",
                    RasterSource(
                        ("https://r/{z}/{x}/{y}.png",),
                        max_native_zoom=20,
                        bounds=(-10, -5, 10, 5),
                    ),
                    token=2,
                ),
            ),
            basemap=Basemap(("https://t/{z}/{x}/{y}.png",), "© OSM"),
        )
    )
    assert widget.state == json.loads(FIXTURE.read_text())
    assert widget.state["revision"] == 1
    assert [x["instance"] for x in widget.state["layers"]] == [1, 2, 3]


def test_duplicate_ids_raise():
    with pytest.raises(ValueError, match="duplicate"):
        MapState(layers=(raster(), raster()))


def test_empty_id_raises():
    with pytest.raises(ValueError):
        MapState(layers=(Layer("", RasterSource(("t",))),))


def test_raster_with_paint_raises():
    with pytest.raises(ValueError, match="paint"):
        raster(paint=VectorPaint())


def test_vector_gets_default_paint():
    layer = Layer("v", GeoJSONSource("abc"))
    assert layer.paint == VectorPaint()
    assert layer.kind == "geojson"


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan"), float("inf")])
def test_opacity_out_of_range_raises(value):
    with pytest.raises(ValueError):
        raster(opacity=value)
    with pytest.raises(ValueError):
        VectorPaint(fill_opacity=value)


@pytest.mark.parametrize(
    "kw",
    [
        {"width": -1},
        {"width": float("nan")},
        {"point_radius": -1},
        {"point_radius": float("inf")},
    ],
)
def test_bad_paint_sizes_raise(kw):
    with pytest.raises(ValueError):
        VectorPaint(**kw)


@pytest.mark.parametrize(
    "kw",
    [
        {"min_zoom": -1},
        {"min_zoom": float("nan")},
        {"max_zoom": 25},
        {"max_zoom": float("nan")},
        {"min_zoom": 5, "max_zoom": 5},
        {"zone": "top"},
    ],
)
def test_bad_zoom_or_zone_raises(kw):
    with pytest.raises(ValueError):
        raster(**kw)


def test_empty_tiles_and_bad_theme_raise():
    with pytest.raises(ValueError):
        RasterSource(())
    with pytest.raises(ValueError):
        Basemap(())
    with pytest.raises(ValueError):
        MapState(theme="sepia")
