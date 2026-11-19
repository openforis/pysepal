"""Tests for the LayerSpec models."""

import ee
import pytest
from matplotlib.colors import LinearSegmentedColormap
from pydantic import ValidationError

from pysepal.layers import (
    GeeSource,
    LayerSpec,
    RasterStyle,
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
