"""Tests for preparing Earth Engine layers."""

import asyncio
from types import SimpleNamespace

import ee
import pytest

import pysepal.layers.preparation as preparation
from pysepal.layers import (
    GeeSource,
    LayerPrepareError,
    LayerSpec,
    RasterStyle,
    colormap_stops,
    prepare,
    prepare_sync,
)


class FakeGee:
    """Records the params of each map id request."""

    def __init__(self):
        """Start with no calls."""
        self.calls = []

    def get_map_id(self, image, params):
        self.calls.append(params)
        url = f"https://t/{len(self.calls)}/{{z}}/{{x}}/{{y}}"
        return {"tile_fetcher": SimpleNamespace(url_format=url)}

    async def get_map_id_async(self, image, params):
        return self.get_map_id(image, params)


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_gee_image_uses_style(image_id):
    gee = FakeGee()
    vis = {"bands": ["B4"], "min": 0, "max": 3000, "palette": ["#000000", "#ffffff"]}
    spec = LayerSpec.from_ee(ee.Image(image_id), vis, name="i")
    render = prepare_sync(spec, gee_interface=gee)
    assert render.kind == "raster-xyz" and render.theme_urls is None
    assert gee.calls[0]["palette"] == ["#000000", "#ffffff"]
    assert render.legend is None


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_gee_vector_without_color_renders_per_theme():
    gee = FakeGee()
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([0, 0]))])
    spec = LayerSpec.from_ee(fc, name="v")
    render = asyncio.run(prepare(spec, gee_interface=gee))
    assert set(render.theme_urls) == {True, False} and len(gee.calls) == 2
    assert "fillColor" not in spec.style.to_ee_style_params()
    assert all(p["fillColor"] == "00000000" for p in gee.calls)


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_gee_vector_forwards_fill_and_width(monkeypatch):
    seen = []
    real = preparation.process_vis_params

    def spy(obj, vis_params, **kw):
        seen.append(vis_params)
        return real(obj, vis_params=vis_params, **kw)

    monkeypatch.setattr(preparation, "process_vis_params", spy)
    vis = {"color": "red", "fillColor": "00ff0080", "width": 3}
    spec = LayerSpec.from_ee(ee.FeatureCollection([]), vis, name="v")
    prepare_sync(spec, gee_interface=FakeGee())
    assert seen == [{"color": "ff0000", "fillColor": "00ff0080", "width": 3}]
    restyled = spec.revise(style=spec.style.model_copy(update={"width": 5}))
    seen.clear()
    prepare_sync(restyled, gee_interface=FakeGee())
    assert seen[0]["width"] == 5


@pytest.mark.gee
@pytest.mark.skipif(not ee.data.is_initialized(), reason="GEE is not set")
def test_gee_named_colormap_reaches_map_id(image_id):
    gee = FakeGee()
    spec = LayerSpec.from_ee(ee.Image(image_id), {"bands": ["B4"], "min": 0, "max": 3000}, name="i")
    styled = spec.revise(style=spec.style.model_copy(update={"colormap": "viridis"}))
    prepare_sync(styled, gee_interface=gee)
    assert gee.calls[-1]["palette"] == colormap_stops("viridis")


def test_gee_without_interface_raises():
    spec = LayerSpec(id="a", name="a", source=GeeSource(expr={}, kind="Image"), style=RasterStyle())
    with pytest.raises(LayerPrepareError, match="gee_interface"):
        prepare_sync(spec)
    with pytest.raises(LayerPrepareError, match="gee_interface"):
        asyncio.run(prepare(spec))
