"""Tests for the frozen map state: validation and the JSON it publishes."""

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


@pytest.mark.parametrize(
    "bounds",
    [
        (0, 0, 1),
        (0, 0, 1, 1, 1),
        5,
        "abcd",
        (float("nan"), 0, 1, 1),
        (0, float("nan"), 1, 1),
        (0, 0, float("inf"), 1),
        (0, 0, 1, float("-inf")),
        (0, 0, 1, "1"),
        (0, True, 1, 1),
        (0, 10, 1, 5),
        (0, -91, 1, 1),
        (0, 0, 1, 90.5),
    ],
)
def test_bad_raster_bounds_raise(bounds):
    with pytest.raises(ValueError, match="RasterSource.bounds"):
        RasterSource(("t",), bounds=bounds)


def test_raster_bounds_may_cross_the_antimeridian():
    source = RasterSource(("t",), bounds=[170, -10, -170, 10])
    assert source.bounds == (170, -10, -170, 10)
    assert source.to_json()["bounds"] == [170, -10, -170, 10]


@pytest.mark.parametrize("value", [0, -256, 256.0, True, "256", None])
def test_bad_tile_size_raises(value):
    with pytest.raises(ValueError, match="RasterSource.tile_size"):
        RasterSource(("t",), tile_size=value)


@pytest.mark.parametrize("value", [-1, 25, 20.0, True, "20", float("nan")])
def test_bad_native_and_basemap_zooms_raise(value):
    with pytest.raises(ValueError, match="RasterSource.max_native_zoom"):
        RasterSource(("t",), max_native_zoom=value)
    with pytest.raises(ValueError, match="Basemap.max_zoom"):
        Basemap(("t",), max_zoom=value)


def test_zoom_limits_are_inclusive():
    assert RasterSource(("t",), max_native_zoom=0).max_native_zoom == 0
    assert Basemap(("t",), max_zoom=24).max_zoom == 24


@pytest.mark.parametrize("value", [True, 1.0, "1", None, float("nan")])
def test_a_token_that_is_not_an_int_raises(value):
    with pytest.raises(ValueError, match="token"):
        raster(token=value)


@pytest.mark.parametrize("tiles", [("",), ("t", ""), ("t", 3), ("t", None)])
def test_bad_tile_entries_raise(tiles):
    with pytest.raises(ValueError, match="RasterSource.tiles"):
        RasterSource(tiles)
    with pytest.raises(ValueError, match="Basemap.tiles"):
        Basemap(tiles)


@pytest.mark.parametrize("kw", [{"opacity": True}, {"min_zoom": False}])
def test_a_bool_is_not_a_number(kw):
    with pytest.raises(ValueError):
        raster(**kw)


def test_numpy_numbers_are_accepted_and_published_as_plain_json():
    np = pytest.importorskip("numpy")
    f32 = np.float32
    source = RasterSource(
        ("t",),
        tile_size=np.int64(512),
        bounds=(f32(-10), f32(-5), f32(10), f32(5)),
        max_native_zoom=np.int32(20),
    )
    layer = Layer("r", source, token=np.int64(3), opacity=f32(0.5), min_zoom=f32(1))
    paint = VectorPaint(fill_opacity=f32(0.25), width=f32(2), point_radius=f32(4))
    vector = Layer("v", GeoJSONSource("abc"), paint=paint, max_zoom=f32(10))
    state = MapState(layers=(layer, vector), basemap=Basemap(("t",), max_zoom=np.int64(18)))
    published = state.to_json()
    assert json.loads(json.dumps(published, allow_nan=False)) == published
    assert published["layers"][0]["source"]["bounds"] == [-10, -5, 10, 5]
    assert published["layers"][0]["opacity"] == 0.5
