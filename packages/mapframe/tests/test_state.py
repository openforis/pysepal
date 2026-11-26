"""Tests for the frozen map state: validation and the JSON it publishes."""

import json
from pathlib import Path

import pytest

from mapframe import (
    Basemap,
    Cluster,
    GeoJSONSource,
    Interaction,
    Layer,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
    tile_urls,
)

FIXTURE = Path(__file__).parents[1] / "js" / "test" / "fixtures" / "state.json"
EMPTY = b'{"type":"FeatureCollection","features":[]}'


def raster(**kw):
    return Layer("r", RasterSource(("https://r/{z}/{x}/{y}.png",)), **kw)


def test_to_json_matches_the_contract_fixture():
    widget = MapWidget()
    digest = widget.add_payload(EMPTY)
    widget.publish(
        MapState(
            layers=(
                Layer("v1", GeoJSONSource(digest, Cluster(40, 12)), token=3),
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
    with pytest.raises(ValueError, match=r"RasterSource.bounds"):
        RasterSource(("t",), bounds=bounds)


def test_raster_bounds_may_cross_the_antimeridian():
    source = RasterSource(("t",), bounds=[170, -10, -170, 10])
    assert source.bounds == (170, -10, -170, 10)
    assert source.to_json()["bounds"] == [170, -10, -170, 10]


@pytest.mark.parametrize("value", [0, -256, 256.0, True, "256", None])
def test_bad_tile_size_raises(value):
    with pytest.raises(ValueError, match=r"RasterSource.tile_size"):
        RasterSource(("t",), tile_size=value)


@pytest.mark.parametrize("value", [-1, 25, 20.0, True, "20", float("nan")])
def test_bad_native_and_basemap_zooms_raise(value):
    with pytest.raises(ValueError, match=r"RasterSource.max_native_zoom"):
        RasterSource(("t",), max_native_zoom=value)
    with pytest.raises(ValueError, match=r"Basemap.max_zoom"):
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
    with pytest.raises(ValueError, match=r"RasterSource.tiles"):
        RasterSource(tiles)
    with pytest.raises(ValueError, match=r"Basemap.tiles"):
        Basemap(tiles)


def test_tile_urls_expands_subdomains():
    assert tile_urls("https://{s}.t.test/{z}/{x}/{y}{r}.png", "ab") == (
        "https://a.t.test/{z}/{x}/{y}.png",
        "https://b.t.test/{z}/{x}/{y}.png",
    )
    assert tile_urls("https://{s}.t.test/{z}", ["x", "y", "z"]) == tuple(
        f"https://{c}.t.test/{{z}}" for c in "xyz"
    )
    assert tile_urls("https://t.test/{z}/{x}/{y}") == ("https://t.test/{z}/{x}/{y}",)


def test_tile_urls_needs_a_subdomain_for_s():
    with pytest.raises(ValueError, match="subdomain"):
        tile_urls("https://{s}.t.test/{z}/{x}/{y}", "")


def test_leaflet_templates_expand_to_the_default_subdomains():
    template = "https://{s}.t.test/{z}/{x}/{y}{r}.png"
    expanded = tuple(f"https://{c}.t.test/{{z}}/{{x}}/{{y}}.png" for c in "abc")
    plain = "https://t.test/{z}/{x}/{y}.png"
    assert RasterSource((template, plain)).tiles == (*expanded, plain)
    assert Basemap((template,)).to_json()["tiles"] == list(expanded)


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


def test_interaction_json():
    layer = Layer("v", GeoJSONSource("abc"), interaction=Interaction(popup=("a", "b"), tooltip=()))
    assert layer.to_json()["interaction"] == {"popup": [["a", "a"], ["b", "b"]], "tooltip": []}
    off = Layer("v", GeoJSONSource("abc"), interaction=Interaction(tooltip=("a",)))
    assert off.to_json()["interaction"] == {"popup": None, "tooltip": [["a", "a"]]}
    labelled = Interaction(popup={"alert_dt": "Date", "status": "status"})
    assert labelled.to_json()["popup"] == [["alert_dt", "Date"], ["status", "status"]]


@pytest.mark.parametrize("field", ["popup", "tooltip"])
@pytest.mark.parametrize("bad", [{"a": ""}, {"": "A"}, {"a": 1}, {1: "A"}])
def test_interaction_rejects_empty_label(field, bad):
    with pytest.raises(ValueError):
        Interaction(**{field: bad})
    assert Layer("v", GeoJSONSource("abc")).to_json()["interaction"] is None


@pytest.mark.parametrize("field", ["popup", "tooltip"])
@pytest.mark.parametrize("bad", [("",), ("a", ""), (1,), "name"])
def test_interaction_rejects_empty_field(field, bad):
    with pytest.raises(ValueError):
        Interaction(**{field: bad})


def test_raster_layer_rejects_interaction():
    with pytest.raises(ValueError, match="interaction"):
        raster(interaction=Interaction(popup=()))


def test_interaction_change_keeps_instance():
    widget = MapWidget()
    digest = widget.add_payload(EMPTY)
    source = GeoJSONSource(digest)
    widget.publish(MapState(layers=(Layer("v", source, interaction=Interaction(popup=("a",))),)))
    first = widget.state["layers"][0]["instance"]
    widget.publish(MapState(layers=(Layer("v", source, interaction=Interaction(popup=("b",))),)))
    assert widget.state["layers"][0]["instance"] == first
    assert widget.state["layers"][0]["interaction"] == {"popup": [["b", "b"]], "tooltip": None}


@pytest.mark.parametrize(
    "kwargs",
    [
        *({"radius": r} for r in (0, True, 1.5)),
        *({"max_zoom": z} for z in (0, 18, True, 2.5)),
    ],
)
def test_cluster_validation(kwargs):
    with pytest.raises(ValueError):
        Cluster(**kwargs)


def test_cluster_json_and_defaults():
    assert GeoJSONSource("abc").to_json() == {"digest": "abc", "cluster": None}
    source = GeoJSONSource("abc", cluster=Cluster(radius=30, max_zoom=12))
    assert source.to_json() == {"digest": "abc", "cluster": {"radius": 30, "max_zoom": 12}}
    assert (Cluster().radius, Cluster().max_zoom) == (50, 14)


def test_cluster_changes_instance():
    widget = MapWidget()
    digest = widget.add_payload(EMPTY)
    widget.publish(MapState(layers=(Layer("v", GeoJSONSource(digest)),)))
    first = widget.state["layers"][0]["instance"]
    widget.publish(MapState(layers=(Layer("v", GeoJSONSource(digest, cluster=Cluster())),)))
    second = widget.state["layers"][0]["instance"]
    assert second != first
    widget.publish(MapState(layers=(Layer("v", GeoJSONSource(digest, cluster=Cluster())),)))
    assert widget.state["layers"][0]["instance"] == second


def test_marker_json():
    assert VectorPaint().to_json()["marker"] == "circle"
    assert VectorPaint(marker="pin").to_json()["marker"] == "pin"
    with pytest.raises(ValueError, match="marker"):
        VectorPaint(marker="star")


def test_class_colors_json():
    paint = VectorPaint(color_by="status", class_colors={"a": "#f00", "b": "#0f0"})
    assert paint.class_colors == (("a", "#f00"), ("b", "#0f0"))
    assert paint.to_json()["color_by"] == "status"
    assert paint.to_json()["class_colors"] == [["a", "#f00"], ["b", "#0f0"]]
    pairs = VectorPaint(color_by="n", class_colors=[(1, "#f00"), (2, "#0f0")])
    assert pairs.to_json()["class_colors"] == [[1, "#f00"], [2, "#0f0"]]
    assert VectorPaint().to_json()["color_by"] is None
    assert VectorPaint().to_json()["class_colors"] == []


@pytest.mark.parametrize(
    "kw",
    [
        {"color_by": "s", "class_colors": {True: "#f00"}},
        {"color_by": "s", "class_colors": {"a": "#f00", 1: "#0f0"}},
        {"color_by": "s", "class_colors": {2**53: "#f00"}},
        {"color_by": "s", "class_colors": {"a": ""}},
        {"color_by": "s"},
        {"class_colors": {"a": "#f00"}},
        {"color_by": "", "class_colors": {"a": "#f00"}},
        {"color_by": "s", "class_colors": [("a", "#f00"), ("a", "#0f0")]},
        {"color_by": "s", "class_colors": {1.5: "#f00"}},
        {"color_by": "s", "class_colors": [("a",)]},
    ],
)
def test_class_colors_validation(kw):
    with pytest.raises(ValueError):
        VectorPaint(**kw)


def test_class_colors_change_keeps_instance():
    widget = MapWidget()
    source = GeoJSONSource(widget.add_payload(EMPTY))
    red = VectorPaint(color_by="s", class_colors={"a": "#f00"})
    widget.publish(MapState(layers=(Layer("v", source, paint=red),)))
    first = widget.state["layers"][0]["instance"]
    green = VectorPaint(color_by="s", class_colors={"a": "#0f0"})
    widget.publish(MapState(layers=(Layer("v", source, paint=green),)))
    assert widget.state["layers"][0]["instance"] == first
    assert widget.state["layers"][0]["paint"]["class_colors"] == [["a", "#0f0"]]


def test_layer_side_defaults_to_both_and_serializes():
    assert raster().side == "both"
    assert raster().to_json()["side"] == "both"
    assert raster(side="left").to_json()["side"] == "left"


@pytest.mark.parametrize("side", ["main", "top", None])
def test_layer_rejects_unknown_side(side):
    with pytest.raises(ValueError, match="side"):
        raster(side=side)


def test_state_compare_serializes():
    assert MapState().compare is False
    assert MapState().to_json()["compare"] is False
    assert MapState(compare=True).to_json()["compare"] is True


@pytest.mark.parametrize("bad", [1, 0, None, "yes"])
def test_compare_rejects_non_bool(bad):
    with pytest.raises(TypeError, match="compare"):
        MapState(compare=bad)


def _provider(**options):
    xyz = pytest.importorskip("xyzservices")
    url = "https://{s}.synthetic.test/{variant}/{z}/{x}/{y}.png"
    options = {"url": url, "attribution": "synthetic", "variant": "base", **options}
    return xyz.TileProvider(name="Synthetic", **options)


def test_from_xyz_keeps_every_subdomain_of_the_provider():
    assert Basemap.from_xyz(_provider(subdomains="12")).tiles == (
        "https://1.synthetic.test/base/{z}/{x}/{y}.png",
        "https://2.synthetic.test/base/{z}/{x}/{y}.png",
    )


def test_from_xyz_takes_the_attribution_and_a_max_zoom_up_to_24():
    tiles = tuple(f"https://{c}.synthetic.test/base/{{z}}/{{x}}/{{y}}.png" for c in "abc")
    assert Basemap.from_xyz(_provider()) == Basemap(tiles, "synthetic", max_zoom=22)
    assert Basemap.from_xyz(_provider(max_zoom=12)).max_zoom == 12
    assert Basemap.from_xyz(_provider(max_zoom=30)).max_zoom == 24


def test_from_xyz_rejects_tms_providers():
    with pytest.raises(ValueError, match="cannot draw Synthetic: it is a TMS provider"):
        Basemap.from_xyz(_provider(tms=True))


@pytest.mark.parametrize(
    "options, placeholder",
    [
        ({"url": "https://t.test/{z}/{x}/{y}.{ext}"}, "{ext}"),
        ({"variant": "{style}"}, "{style}"),
    ],
)
def test_from_xyz_rejects_placeholders_maplibre_cannot_fill(options, placeholder):
    with pytest.raises(ValueError, match=f"unfilled placeholder {placeholder}"):
        Basemap.from_xyz(_provider(**options))


def test_from_xyz_rejects_a_provider_missing_its_api_key():
    provider = _provider(url="https://t.test/{z}/{x}/{y}?k={apikey}", apikey="<insert your key>")
    with pytest.raises(ValueError, match="cannot draw Synthetic: Token is required"):
        Basemap.from_xyz(provider)
