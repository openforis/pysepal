"""Tests for the LayerSpec models."""

import threading

import ee
import geopandas as gpd
import pytest
from matplotlib.colors import LinearSegmentedColormap
from pydantic import ValidationError

from pysepal.layers import (
    GeeSource,
    LayerSpec,
    RasterStyle,
    TileSource,
    VectorStyle,
    colormap_stops,
    uri_to_path,
)
from pysepal.layers.spec import _raster_style_from_ee


def test_json_round_trip(byte):
    spec = LayerSpec.from_raster(byte, colormap="viridis", vmin=0, vmax=255)
    again = LayerSpec.model_validate_json(spec.model_dump_json())
    assert again == spec and again.render_hash == spec.render_hash
    assert "data_hash" not in spec.model_dump()


def test_gee_source_round_trips_without_ee_calls():
    expr = {"result": "0", "values": {"0": {"constantValue": 1}}}
    source = GeeSource(expr=expr, kind="Image")
    spec = LayerSpec(id="a", name="a", source=source, style=RasterStyle())
    assert LayerSpec.model_validate_json(spec.model_dump_json()).source.expr == expr


def test_restyle_keeps_data_hash(byte):
    spec = LayerSpec.from_raster(byte)
    new = spec.revise(style=RasterStyle(colormap="magma"))
    assert new.data_hash == spec.data_hash and new.render_hash != spec.render_hash
    assert (new.revision, new.parent, new.id) == (1, spec.render_hash, spec.id)


def test_frozen(byte):
    with pytest.raises(ValidationError):
        LayerSpec.from_raster(byte).name = "x"


def test_ops_reserved(byte):
    with pytest.raises(NotImplementedError):
        LayerSpec.from_raster(byte).revise(ops=[{"op": "clip"}])


def test_palette_and_colormap_exclusive():
    with pytest.raises(ValidationError):
        RasterStyle(palette=["#000000"], colormap="viridis")


def test_from_vector_formats(fake_vector):
    assert LayerSpec.from_vector(fake_vector).source.format == "ESRI Shapefile"
    pm = LayerSpec.from_vector("https://x.org/a.pmtiles", layer="roads")
    assert pm.source.format == "PMTiles"
    assert LayerSpec.from_vector(fake_vector).style.stroke is None


def test_local_uri_is_absolute(byte):
    spec = LayerSpec.from_raster(byte)
    assert spec.source.uri.startswith("file://") and uri_to_path(spec.source.uri) == byte.resolve()


def test_uri_to_path_rejects_other_schemes():
    assert uri_to_path("/a/b.tif").name == "b.tif"
    with pytest.raises(ValueError):
        uri_to_path("https://x.org/a.tif")


def test_legacy_inputs_normalised(byte):
    cmap = LinearSegmentedColormap.from_list("x", ["#228b22", "#ff0000"], N=256)
    spec = LayerSpec.from_raster(byte, bands=2, colormap=cmap)
    assert spec.style.bands == [2] and spec.style.colormap is None
    assert len(spec.style.palette) == 256
    assert LayerSpec.from_raster(byte, bands=[3, 2, 1]).style.colormap is None
    assert VectorStyle(stroke="red").stroke == "#ff0000"
    with pytest.raises(ValidationError):
        RasterStyle(palette=["#zz"])


def test_vector_style_to_ee():
    style = VectorStyle(
        stroke="#ff0000", fill="#00ff00", fill_opacity=0.5, width=3, extra={"pointSize": 4}
    )
    assert style.to_ee_style_params() == {
        "color": "ff0000",
        "fillColor": "00ff0080",
        "width": 3,
        "pointSize": 4,
    }
    assert VectorStyle().to_ee_style_params() == {"width": 2.0}


def test_vector_style_class_colors():
    style = VectorStyle(color_by="status", class_colors={"a": "red", "b": "00FF00"})
    assert style.class_colors == {"a": "#ff0000", "b": "#00ff00"}
    ints = VectorStyle(color_by="n", class_colors={1: "#F00", 2: "blue"}, class_labels={1: "One"})
    assert ints.class_colors == {1: "#ff0000", 2: "#0000ff"}
    assert [type(k) for k in ints.class_colors] == [int, int]
    assert VectorStyle().color_by is None and VectorStyle().class_colors is None


@pytest.mark.parametrize(
    "kw",
    [
        {"color_by": "s", "class_colors": {True: "#ff0000"}},
        {"color_by": "s", "class_colors": {"a": "#ff0000", 1: "#00ff00"}},
        {"color_by": "s", "class_colors": {"a": "#ff0000"}, "class_labels": {False: "x"}},
        {"color_by": "s", "class_colors": {"a": "#ff0000"}, "class_labels": {"a": "x", 1: "y"}},
        {"color_by": "s"},
        {"class_colors": {"a": "#ff0000"}},
        {"color_by": "s", "class_colors": {}},
        {"color_by": "", "class_colors": {"a": "#ff0000"}},
        {"color_by": "s", "class_colors": {"a": "not a colour"}},
        {"color_by": "s", "class_colors": {2**53: "#ff0000"}},
        {"color_by": "s", "class_colors": {1.0: "#ff0000"}},
        {"color_by": "s", "class_colors": [[True, "#ff0000"]]},
        {"color_by": "s", "class_colors": [["a", "#ff0000"], [1, "#00ff00"]]},
        {"color_by": "s", "class_colors": [[1.0, "#ff0000"]]},
        {"color_by": "s", "class_colors": [[1, "#ff0000"], [1, "#00ff00"]]},
        {"color_by": "s", "class_colors": [[1, "#ff0000", "x"]]},
        {"color_by": "s", "class_colors": [[[1], "#ff0000"]]},
        {"color_by": "s", "class_colors": {"a": "#ff0000"}, "class_labels": [[False, "x"]]},
    ],
)
def test_vector_style_rejects_bad_classes(kw):
    with pytest.raises(ValidationError):
        VectorStyle(**kw)


def test_vector_classes_round_trip_through_json():
    style = VectorStyle(
        color_by="n", class_colors={2: "#00ff00", 1: "#ff0000"}, class_labels={1: "One"}
    )
    spec = LayerSpec.from_points(POINTS, name="p", style=style)
    dumped = spec.model_dump(mode="json")["style"]
    assert dumped["class_colors"] == [[2, "#00ff00"], [1, "#ff0000"]]
    assert dumped["class_labels"] == [[1, "One"]]
    again = LayerSpec.model_validate_json(spec.model_dump_json())
    assert again == spec and again.render_hash == spec.render_hash
    assert list(again.style.class_colors) == [2, 1]

    def hash_of(classes):
        return spec.revise(style=VectorStyle(color_by="n", class_colors=classes)).render_hash

    assert hash_of({1: "#ff0000"}) != hash_of({"1": "#ff0000"})
    assert hash_of({1: "#ff0000", 2: "#00ff00"}) != hash_of({2: "#00ff00", 1: "#ff0000"})


def test_vector_classes_accept_pairs():
    style = VectorStyle(color_by="n", class_colors=[[1, "red"], (2, "blue")])
    assert style.class_colors == {1: "#ff0000", 2: "#0000ff"}


def test_class_colors_fill_by_default():
    classes = {"color_by": "s", "class_colors": {"a": "#ff0000"}}
    assert VectorStyle(**classes).effective_fill_opacity == 1.0
    assert VectorStyle(**classes, fill_opacity=0.3).effective_fill_opacity == 0.3


def test_explicit_fill_is_visible():
    assert VectorStyle().effective_fill_opacity == 0.0
    assert VectorStyle(fill="#00ff00").effective_fill_opacity == 1.0
    assert VectorStyle(fill="#00ff00", fill_opacity=0).effective_fill_opacity == 0.0
    style = VectorStyle.from_ee_style({"color": "red", "fillColor": "00ff00"})
    assert style.to_ee_style_params()["fillColor"] == "00ff00ff"
    assert VectorStyle.from_ee_style({"fillColor": "00ff0000"}).fill_opacity == 0.0


def test_ee_colormap_becomes_palette():
    params = RasterStyle(bands=["NDVI"], min=0, max=1, colormap="viridis").to_ee_vis_params()
    assert params["palette"] == colormap_stops("viridis") and "colormap" not in params
    with pytest.raises(ValidationError):
        RasterStyle(bands=["B4", "B3", "B2"], colormap="viridis")


def test_to_ee_vis_params_drops_none():
    style = RasterStyle(bands=["B4"], min=0, max=1, extra={"opacity": 0.5})
    assert style.to_ee_vis_params() == {"bands": ["B4"], "min": 0, "max": 1, "opacity": 0.5}


def test_ee_comma_strings_become_lists():
    params = {"bands": "B4, B3,B2", "min": "0,0,0", "max": "3000, 3000, 3000", "gamma": 1.4}
    style = _raster_style_from_ee(params, "", True)
    assert style.bands == ["B4", "B3", "B2"]
    assert (style.min, style.max, style.gamma) == ([0, 0, 0], [3000] * 3, 1.4)
    assert _raster_style_from_ee({"min": "5", "max": 9}, "", True).min == 5.0


@pytest.mark.parametrize("gamma", [[1.2, 1.1, 1.0], "1.2,1.1,1.0", "1.2, 1.1, 1.0"])
def test_ee_per_band_gamma(gamma):
    params = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": gamma}
    style = _raster_style_from_ee(params, "", True)
    assert style.gamma == [1.2, 1.1, 1.0]
    assert style.to_ee_vis_params()["gamma"] == [1.2, 1.1, 1.0]


def test_ee_palette_and_extras_normalised():
    params = {"palette": "red, 00ff00, #0000FF", "min": 0, "max": 1, "opacity": 0.5}
    style = _raster_style_from_ee(params, "viz", False)
    assert style.palette == ["#ff0000", "#00ff00", "#0000ff"]
    assert style.extra == {"opacity": 0.5}
    assert (style.viz_name, style.use_asset_viz) == ("viz", False)
    bare = _raster_style_from_ee({"palette": ["FF0000", "00ff00"]}, "", True)
    assert bare.palette == ["#ff0000", "#00ff00"]


def test_ee_feature_style_normalised():
    params = {"color": "FF0000", "width": 3, "fillColor": "00ff0080", "pointSize": 4}
    style = VectorStyle.from_ee_style({**params, "lineType": None})
    assert (style.stroke, style.fill, style.width) == ("#ff0000", "#00ff00", 3)
    assert style.fill_opacity == pytest.approx(128 / 255)
    assert style.extra == {"pointSize": 4}


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_from_ee_round_trip(image_id):
    vis = {"bands": ["B4"], "min": 0, "max": 3000}
    spec = LayerSpec.from_ee(ee.Image(image_id), vis, name="img")
    obj = LayerSpec.model_validate_json(spec.model_dump_json()).source.to_ee()
    assert isinstance(obj, ee.Image)
    assert ee.serializer.toJSON(obj) == ee.serializer.toJSON(ee.Image(image_id))


def test_missing_local_files_build_without_io(tmp_path):
    raster = LayerSpec.from_raster(tmp_path / "gone.tif")
    vector = LayerSpec.from_vector(tmp_path / "gone.geojson")
    assert raster.source.size is None and vector.source.size is None


@pytest.fixture
def fake_geojson():
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    feature = {
        "type": "Feature",
        "properties": {"a": 1},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }
    return {"type": "FeatureCollection", "features": [feature]}


def test_zone_defaults_to_data_and_leaves_hashes_alone(vector_spec):
    assert vector_spec.zone == "data"
    overlay = vector_spec.model_copy(update={"zone": "overlay"})
    assert overlay.data_hash == vector_spec.data_hash
    assert overlay.render_hash == vector_spec.render_hash


def test_wms_keeps_the_callers_query():
    src = TileSource.wms("https://h/wms?CQL_FILTER=gaul0_code=1", "gaul:adm0")
    assert src.url == (
        "https://h/wms?CQL_FILTER=gaul0_code=1&SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0"
        "&LAYERS=gaul:adm0&STYLES=&FORMAT=image/png&TRANSPARENT=TRUE&CRS=EPSG:3857"
        "&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}"
    )


def test_wms_without_query_and_111_uses_srs():
    src = TileSource.wms("https://h/wms", "a", version="1.1.1", transparent=False)
    assert src.url.startswith("https://h/wms?SERVICE=WMS")
    assert "SRS=EPSG:3857" in src.url and "CRS=" not in src.url
    assert "TRANSPARENT=FALSE" in src.url


def test_tile_source_needs_placeholders():
    TileSource(url="https://h/{z}/{x}/{y}.png")
    TileSource(url="https://h/wms?BBOX={bbox-epsg-3857}")
    with pytest.raises(ValueError):
        TileSource(url="https://h/{z}/{x}.png")


@pytest.mark.parametrize("kwargs", [{"tile_size": 0}, {"tile_size": -1}, {"max_zoom": 25}])
def test_tile_source_rejects_bad_size_and_zoom(kwargs):
    with pytest.raises(ValueError):
        TileSource(url="https://h/{z}/{x}/{y}.png", **kwargs)


def test_from_tiles_accepts_a_url_string():
    spec = LayerSpec.from_tiles("https://h/{z}/{x}/{y}.png", name="t", zone="overlay")
    assert spec.source.type == "tile" and spec.zone == "overlay"
    assert isinstance(spec.style, RasterStyle) and spec.id


def test_from_geojson_is_content_addressed(fake_geojson):
    a = LayerSpec.from_geojson(fake_geojson, name="x")
    b = LayerSpec.from_geojson(fake_geojson, name="x")
    assert a.source.uri == b.source.uri and a.data_hash == b.data_hash and a.id != b.id
    assert a.source.format == "Parquet" and a.source.checksum and a.source.size


def test_from_geojson_wraps_a_feature(fake_geojson):
    spec = LayerSpec.from_geojson(fake_geojson["features"][0], name="x")
    assert len(gpd.read_parquet(uri_to_path(spec.source.uri))) == 1


def test_from_geojson_keeps_a_projected_crs(fake_geojson):
    from pysepal.layers import prepare_sync

    gdf = gpd.GeoDataFrame.from_features(fake_geojson["features"], crs=4326).to_crs(3857)
    render = prepare_sync(LayerSpec.from_geojson(gdf, name="x"))
    assert render.bounds == pytest.approx((0, 0, 1, 1), abs=1e-6)


def test_from_geojson_needs_a_crs(fake_geojson):
    gdf = gpd.GeoDataFrame.from_features(fake_geojson["features"])
    with pytest.raises(ValueError):
        LayerSpec.from_geojson(gdf, name="x")


def test_from_geojson_rejects_other_types():
    with pytest.raises(TypeError):
        LayerSpec.from_geojson("nope", name="x")


def test_from_geojson_concurrent_identical_writes(fake_geojson):
    fake_geojson["features"][0]["properties"]["a"] = "concurrent"
    specs = []
    threads = [
        threading.Thread(
            target=lambda: specs.append(LayerSpec.from_geojson(fake_geojson, name="x"))
        )
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(specs) == 8 and len({s.source.uri for s in specs}) == 1
    assert len(gpd.read_parquet(uri_to_path(specs[0].source.uri))) == 1
    assert len(list(uri_to_path(specs[0].source.uri).parent.glob("*.tmp"))) == 0


def test_from_geojson_keeps_the_fingerprint_on_a_second_add(fake_geojson):
    from pysepal.layers import local_fingerprint

    first = local_fingerprint(LayerSpec.from_geojson(fake_geojson, name="x"))
    second = local_fingerprint(LayerSpec.from_geojson(fake_geojson, name="x"))
    assert first == second


POINTS = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]


def _point_inputs():
    import pandas as pd

    frame = pd.DataFrame({"lng": [p[0] for p in POINTS], "lat": [p[1] for p in POINTS]})
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": p}}
            for p in POINTS
        ],
    }
    gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(*zip(*POINTS)), crs=4326)
    return {"gdf": gdf, "geojson": geojson, "frame": frame, "pairs": POINTS}


@pytest.mark.parametrize("kind", ["gdf", "geojson", "frame", "pairs"])
def test_from_points_inputs(kind):
    spec = LayerSpec.from_points(_point_inputs()[kind], name="p")
    back = gpd.read_parquet(uri_to_path(spec.source.uri))
    assert [(g.x, g.y) for g in back.geometry] == POINTS
    assert [c for c in back.columns if c != "geometry"] == []


def test_from_points_defaults_to_a_filled_circle():
    style = LayerSpec.from_points(POINTS, name="p").style
    assert style.marker == "circle"
    assert style.effective_fill_opacity == 1.0
    pin = VectorStyle(marker="pin")
    assert LayerSpec.from_points(POINTS, name="p", style=pin).style == pin


def test_from_points_dataframe_columns_become_properties():
    import pandas as pd

    frame = pd.DataFrame({"x": [1.0], "y": [2.0], "name": ["a"]})
    spec = LayerSpec.from_points(frame, name="p", lng="x", lat="y")
    back = gpd.read_parquet(uri_to_path(spec.source.uri))
    assert list(back["name"]) == ["a"]


def test_from_points_rejects_lines():
    line = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
    }
    with pytest.raises(ValueError, match="Point"):
        LayerSpec.from_points(line, name="p")


def test_from_points_missing_column():
    import pandas as pd

    with pytest.raises(ValueError, match="lat"):
        LayerSpec.from_points(pd.DataFrame({"lng": [1.0]}), name="p")


def test_from_points_non_finite():
    with pytest.raises(ValueError, match="finite"):
        LayerSpec.from_points([(float("nan"), 1.0)], name="p")


@pytest.mark.parametrize("field", ["popup", "tooltip"])
def test_vector_style_popup_list_must_not_be_empty(field):
    with pytest.raises(ValidationError):
        VectorStyle(**{field: []})
    assert VectorStyle(**{field: ["a"]}).model_dump()[field] == ["a"]


@pytest.mark.parametrize("field", ["popup", "tooltip"])
def test_vector_style_popup_labels(field):
    style = VectorStyle(**{field: {"b": "Bee", "a": "a"}})
    assert getattr(style, field) == {"b": "Bee", "a": "a"}
    assert style.model_dump(mode="json")[field] == [["b", "Bee"], ["a", "a"]]
    for bad in ({}, {"a": ""}, {"": "A"}):
        with pytest.raises(ValidationError):
            VectorStyle(**{field: bad})
    spec = LayerSpec.from_points(POINTS, name="p", style=style)
    again = LayerSpec.model_validate_json(spec.model_dump_json())
    assert again == spec and again.render_hash == spec.render_hash
    assert list(getattr(again.style, field)) == ["b", "a"]
    flipped = spec.revise(style=VectorStyle(**{field: {"a": "a", "b": "Bee"}}))
    assert flipped.render_hash != spec.render_hash
    assert VectorStyle(**{field: ["a"]}).model_dump(mode="json")[field] == ["a"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cluster_radius": 0},
        {"cluster_max_zoom": 0},
        {"cluster_max_zoom": 18},
        {"radius": -1},
        {"marker": "pin", "radius": 0},
    ],
)
def test_vector_style_point_validation(kwargs):
    with pytest.raises(ValidationError):
        VectorStyle(**kwargs)
    assert VectorStyle(radius=0).radius == 0


def test_ee_style_params_ignore_point_fields():
    plain = VectorStyle(stroke="#ff0000", width=3)
    rich = VectorStyle(
        stroke="#ff0000", width=3, radius=9, marker="pin", cluster=True, popup=True, tooltip=["a"]
    )
    assert rich.to_ee_style_params() == plain.to_ee_style_params()
    again = VectorStyle.from_ee_style(rich.to_ee_style_params())
    assert (again.marker, again.cluster, again.popup) == ("circle", False, False)


@pytest.mark.parametrize(
    "data",
    [
        [(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)],
        [(1.0, 2.0, 3.0)] * 4,
        [1.0, 2.0, 3.0, 4.0],
        [(1.0, 2.0), (3.0,)],
    ],
    ids=["two-triples", "four-triples", "flat", "ragged"],
)
def test_from_points_rejects_malformed_pairs(data):
    with pytest.raises(ValueError):
        LayerSpec.from_points(data, name="p")


def test_from_points_empty_sequence_gives_an_empty_layer():
    spec = LayerSpec.from_points([], name="p")
    assert len(gpd.read_parquet(uri_to_path(spec.source.uri))) == 0


def test_from_points_bare_point_geometry():
    spec = LayerSpec.from_points({"type": "Point", "coordinates": [1.0, 2.0]}, name="p")
    back = gpd.read_parquet(uri_to_path(spec.source.uri))
    assert [(g.x, g.y) for g in back.geometry] == [(1.0, 2.0)]
    with pytest.raises(ValueError, match="Point"):
        LayerSpec.from_points({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, name="p")
