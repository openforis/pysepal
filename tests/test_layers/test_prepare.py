"""Tests for turning a LayerSpec into a RenderLayer."""

import asyncio
import os
import shutil
import threading
from urllib.parse import parse_qs, urlparse

import geopandas as gpd
import pytest

import pysepal.layers.preparation as preparation
from pysepal.layers import (
    Gradient,
    LayerPrepareError,
    LayerSpec,
    Legend,
    TileSource,
    VectorSource,
    VectorStyle,
    colormap_stops,
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
    assert render.keepalive is not None
    assert render.legend == Legend(
        gradients=[Gradient(colors=colormap_stops("viridis"), labels=["0", "200"])]
    )


def gradient_labels(render) -> list:
    return [g.labels for g in render.legend.gradients]


@pytest.mark.parametrize(
    "pinned, labels",
    [({}, ["10", "90"]), ({"vmin": 0}, ["0", "90"]), ({"vmax": 50}, ["10", "50"])],
)
def test_an_unpinned_end_is_the_one_the_tiles_stretch_to(ramp, pinned, labels):
    # the tile server reads the file's own ends for the ones left unset
    render = prepare_sync(LayerSpec.from_raster(ramp, name="Ramp", colormap="viridis", **pinned))
    assert gradient_labels(render) == [labels]
    # the URL still leaves them to the server
    query = parse_qs(urlparse(render.url).query)
    assert {end for end in ("vmin", "vmax") if end in query} == set(pinned)


def test_the_stretch_is_read_off_the_calling_thread(ramp, monkeypatch):
    threads, real = [], preparation._tile_range
    monkeypatch.setattr(
        preparation, "_tile_range", lambda *a: threads.append(threading.get_ident()) or real(*a)
    )
    render = asyncio.run(prepare(LayerSpec.from_raster(ramp, colormap="viridis")))
    assert gradient_labels(render) == [["10", "90"]]
    assert threads and threading.get_ident() not in threads


def test_a_byte_raster_left_unpinned_is_not_stretched(byte):
    # localtileserver rescales a byte band only when given an end: 0-255 is the ramp
    render = prepare_sync(LayerSpec.from_raster(byte, palette=["#000000", "#ffffff"]))
    assert gradient_labels(render) == [["0", "255"]]
    assert render.legend.gradients[0].colors == ["#000000", "#ffffff"]


def test_a_raster_without_a_ramp_has_no_render_legend(ramp, rgb):
    for spec in (
        LayerSpec.from_raster(ramp, colormap=None),  # greyscale
        LayerSpec.from_raster(rgb),  # an RGB composite
        LayerSpec.from_raster(ramp, class_colors={10: "#ff0000", 90: "#0000ff"}),
    ):
        assert prepare_sync(spec).legend is None


def test_prepare_raster_single_band_list(byte):
    render = prepare_sync(LayerSpec.from_raster(byte, bands=1, colormap="viridis"))
    assert "indexes=1" in render.url and "colormap=viridis" in render.url


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


def test_a_root_relative_pmtiles_url_reaches_the_browser_as_is():
    # what vectortileserver hands out behind SEPAL's proxy
    url = "/api/sandbox/jupyter/proxy/8000/pmtiles?filePath=/home/me/a.pmtiles"
    spec = LayerSpec.from_vector(url, format="PMTiles", layer="roads")
    render = prepare_sync(spec)
    assert (render.kind, render.url, render.source_layer) == ("pmtiles", url, "roads")
    assert local_fingerprint(spec) is None


@pytest.mark.parametrize("given", ["path", "str", "bare uri"])
def test_a_local_pmtiles_file_is_refused_however_it_is_named(tmp_path, given):
    archive = tmp_path / "a.pmtiles"
    archive.write_bytes(b"")
    if given == "bare uri":
        source = VectorSource(uri=str(archive), format="PMTiles", layer="x")
        spec = LayerSpec(id="a", name="a", source=source, style=VectorStyle())
    else:
        spec = LayerSpec.from_vector(archive if given == "path" else str(archive), layer="x")
    with pytest.raises(LayerPrepareError, match="local PMTiles"):
        prepare_sync(spec)


def test_missing_file(tmp_path):
    with pytest.raises(LayerPrepareError) as info:
        prepare_sync(LayerSpec.from_raster(tmp_path / "gone.tif"))
    assert info.value.layer_id and "gone.tif" in str(info.value)


def test_large_geojson_warns(fake_vector, monkeypatch, caplog):
    monkeypatch.setattr(preparation, "GEOJSON_WARN_BYTES", 10)
    prepare_sync(LayerSpec.from_vector(fake_vector))
    assert "GeoJSON" in caplog.text


@pytest.mark.parametrize("run", [prepare_sync, lambda s: asyncio.run(prepare(s))])
def test_tile_spec_prepares_with_size_and_zoom(run):
    source = TileSource(url="https://h/{z}/{x}/{y}.png", tile_size=512)
    spec = LayerSpec.from_tiles(source, name="t")
    render = run(spec)
    assert (render.kind, render.tile_size, render.max_zoom, render.bounds) == (
        "raster-xyz",
        512,
        24,
        None,
    )
    assert render.url == source.url and render.render_hash == spec.render_hash


def test_raster_prepare_enables_the_loopback_bridge(rgb, monkeypatch):
    from localtileserver import TileClient

    calls = []
    monkeypatch.setattr(TileClient, "enable_jupyter_loopback", lambda self: calls.append(self))
    render = prepare_sync(LayerSpec.from_raster(rgb, name="r"), optimize=False)
    assert calls == [render.keepalive]


def test_client_prefix_constant_lives_in_preparation():
    from pysepal.mapping.sepal_map import CLIENT_PREFIX_ENV_VAR

    assert CLIENT_PREFIX_ENV_VAR is preparation.CLIENT_PREFIX_ENV_VAR


@pytest.mark.parametrize(("name", "drawn"), [("Reds", "reds"), ("reds", "reds"), ("berlin", None)])
def test_local_tiles_take_the_colormap_by_their_own_name(byte, name, drawn):
    render = prepare_sync(LayerSpec.from_raster(byte, name="b", colormap=name), optimize=False)
    query = parse_qs(urlparse(render.url).query)
    # rio-tiler names its colormaps in lower case; one it lacks is registered from its colors
    if drawn:
        assert query["colormap"] == [drawn]
    else:
        assert query["colormap"][0].startswith("custom:")
    assert render.legend.gradients
