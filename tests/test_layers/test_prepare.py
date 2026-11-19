"""Tests for turning a LayerSpec into a RenderLayer."""

import asyncio
import os
import shutil

import geopandas as gpd
import pytest

import pysepal.layers.preparation as preparation
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    local_fingerprint,
    prepare,
    prepare_sync,
)


def test_prepare_raster(byte):
    spec = LayerSpec.from_raster(byte, colormap="viridis", vmin=0, vmax=200)
    render = asyncio.run(prepare(spec))
    assert (
        render.kind == "raster-xyz" and "{z}" in render.url and render.raster == str(byte.resolve())
    )
    w, s, e, n = render.bounds
    assert w < e and s < n and render.render_hash == spec.render_hash
    assert render.keepalive is not None and render.legend is None


def test_prepare_raster_single_band_list(byte):
    render = prepare_sync(LayerSpec.from_raster(byte, bands=1, colormap="viridis"))
    assert render.tile_kwargs["indexes"] == [1] and render.tile_kwargs["colormap"] == "viridis"


def test_prepare_sync_matches_async(byte):
    spec = LayerSpec.from_raster(byte)
    assert prepare_sync(spec).kind == asyncio.run(prepare(spec)).kind == "raster-xyz"


def test_prepare_sync_inside_running_loop(byte):
    async def run():
        return prepare_sync(LayerSpec.from_raster(byte))

    assert asyncio.run(run()).kind == "raster-xyz"


def test_prepare_vector_geojson(fake_vector):
    render = prepare_sync(LayerSpec.from_vector(fake_vector, stroke="#ff0000"))
    assert render.kind == "geojson" and render.data["type"] == "FeatureCollection"
    assert render.vector_style.stroke == "#ff0000" and render.bounds is not None


def test_prepare_geoparquet_reprojects(fake_vector, tmp_path):
    path = tmp_path / "v.parquet"
    gpd.read_file(fake_vector).to_crs(3857).to_parquet(path)
    render = prepare_sync(LayerSpec.from_vector(path))
    w, s, e, n = render.bounds
    assert 12 < w < e < 13 and 41 < s < n < 42  # Vatican, back in lon/lat


def test_fingerprint_tracks_sidecars(fake_vector, tmp_path):
    for f in fake_vector.parent.glob(f"{fake_vector.stem}.*"):
        shutil.copy(f, tmp_path)
    spec = LayerSpec.from_vector(tmp_path / fake_vector.name)
    before = local_fingerprint(spec)
    dbf = tmp_path / f"{fake_vector.stem}.dbf"
    os.utime(dbf, ns=(dbf.stat().st_atime_ns, dbf.stat().st_mtime_ns + 10**9))
    assert local_fingerprint(spec) != before
    assert local_fingerprint(LayerSpec.from_vector("https://x.org/a.pmtiles", layer="r")) is None


def test_prepare_pmtiles_http():
    render = prepare_sync(LayerSpec.from_vector("https://x.org/a.pmtiles", layer="roads"))
    assert (render.kind, render.url, render.source_layer) == (
        "pmtiles",
        "https://x.org/a.pmtiles",
        "roads",
    )


def test_local_pmtiles_not_supported(tmp_path):
    with pytest.raises(LayerPrepareError, match="PMTiles"):
        prepare_sync(LayerSpec.from_vector(tmp_path / "a.pmtiles", layer="x"))


def test_missing_file(tmp_path):
    with pytest.raises(LayerPrepareError) as info:
        prepare_sync(LayerSpec.from_raster(tmp_path / "gone.tif"))
    assert info.value.layer_id and "gone.tif" in str(info.value)


def test_large_geojson_warns(fake_vector, monkeypatch, caplog):
    monkeypatch.setattr(preparation, "GEOJSON_WARN_BYTES", 10)
    prepare_sync(LayerSpec.from_vector(fake_vector))
    assert "GeoJSON" in caplog.text
