"""How add_raster colors a raster, and that the choice reaches the tile server.

``get_leaflet_tile_layer`` only forwards ``indexes``, ``colormap``, ``vmin``,
``vmax``, ``nodata``, ``stretch`` and ``expression`` into the tile URL; every
other keyword is dropped. So these assert on the query of the tile URL the map
publishes to the browser rather than on the layer spec.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from matplotlib.colors import LinearSegmentedColormap

from pysepal import mapping as sm
from pysepal.mapping.raster_style import (
    _build_class_colormap,
    _class_color_kwargs,
    _densify_class_codes,
    _hex_to_rgb,
    _needs_dense_codes,
)


def _render(m, layer):
    """The render the map draws for a layer handle."""
    return m.layer_engine.accepted(layer.id)[1]


def _drawn_url(m, layer) -> str:
    """The tile URL the map publishes for a layer handle."""
    drawn = next(x for x in m.state["layers"] if x["id"] == layer.id)
    return drawn["source"]["tiles"][0]


def _params(m, layer) -> dict:
    """Tile URL query parameters, minus the filename."""
    params = parse_qs(urlparse(_drawn_url(m, layer)).query)
    params.pop("filename", None)
    return {key: values[0] if len(values) == 1 else values for key, values in params.items()}


def _served_file(m, layer) -> str:
    return parse_qs(urlparse(_drawn_url(m, layer)).query)["filename"][0]


def _rendered_colors(m, layer) -> set:
    """The opaque RGB colors the tile server actually draws for this layer.

    Renders through the layer's own URL parameters, so it measures what
    ``add_raster`` asked for rather than what the test thinks it asked for.
    """
    import numpy as np
    import rasterio as rio

    params = _params(m, layer)
    indexes = [int(i) for i in params["indexes"].split(",")] if "indexes" in params else None
    png = _render(m, layer).keepalive.thumbnail(
        indexes=indexes,
        colormap=params.get("colormap"),
        vmin=params.get("vmin"),
        vmax=params.get("vmax"),
        nodata=params.get("nodata"),
    )

    with rio.MemoryFile(png) as memfile, memfile.open() as ds:
        rgba = ds.read()
    opaque = rgba[3] > 0 if rgba.shape[0] == 4 else np.ones(rgba.shape[1:], dtype=bool)
    return {tuple(int(v) for v in c) for c in rgba[:3][:, opaque].T}


def test_colormap_colors_class_zero():
    cm = _build_class_colormap({0: "#ff0000", 5: "#00ff00"})
    assert cm[0] == (255, 0, 0, 255)  # class 0 is a real class, not background
    assert cm[5] == (0, 255, 0, 255)


def test_colormap_holds_only_the_declared_classes():
    # padding out to 256 entries would push rio-tiler onto its make_lut path,
    # where a value above 255 wraps into a class and gets painted with its color
    cm = _build_class_colormap({5: "#00ff00"})
    assert cm == {5: (0, 255, 0, 255)}


def test_colormap_accepts_short_hex():
    assert _build_class_colormap({1: "#f00"}) == {1: (255, 0, 0, 255)}


def test_hex_to_rgb_rejects_a_malformed_color():
    with pytest.raises(ValueError):
        _hex_to_rgb("#ff00")


def test_class_color_kwargs_registers_a_colormap():
    kwargs = _class_color_kwargs({1: "#ff0000"})
    # a server-side registration key, not a raw dict: the only route that keeps
    # per-class alpha. vmin/vmax neutralise localtileserver's rescale, which
    # would otherwise turn the class codes into ramp positions.
    assert kwargs["colormap"].startswith("custom:")
    assert (kwargs["vmin"], kwargs["vmax"]) == (0, 255)


def test_class_color_kwargs_returns_none_when_unavailable(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_palettes(name, *args, **kwargs):
        if name == "localtileserver.tiler.palettes":
            raise ImportError("no palette registry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_palettes)
    assert _class_color_kwargs({1: "#ff0000"}) is None


def test_codes_within_a_byte_need_no_renumbering():
    assert _needs_dense_codes({0: "#ff0000", 255: "#00ff00"}) is False


def test_codes_outside_a_byte_need_renumbering():
    assert _needs_dense_codes({1: "#ff0000", 300: "#00ff00"}) is True
    assert _needs_dense_codes({-1: "#ff0000"}) is True


def test_densify_renumbers_codes_and_colors(int16_classes: Path, tmp_path: Path) -> None:
    import rasterio as rio

    path, colors = _densify_class_codes(int16_classes, {1: "#ff0000", 2: "#00ff00"}, tmp_path)

    assert colors == {1: "#ff0000", 2: "#00ff00"}  # already dense, order preserved
    with rio.open(path) as ds:
        assert ds.dtypes[0] == "uint8"


def test_densify_maps_high_codes_onto_a_byte(int16_classes: Path, tmp_path: Path) -> None:
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    source = tmp_path / "high.tif"
    data = np.full((8, 8), 300, dtype="int32")
    data[:, 4:] = 1024
    with rio.open(
        source,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_origin(0, 0, 0.01, 0.01),
    ) as ds:
        ds.write(data, 1)

    path, colors = _densify_class_codes(source, {300: "#0000ff", 1024: "#ffffff"}, tmp_path)

    assert colors == {1: "#0000ff", 2: "#ffffff"}
    with rio.open(path) as ds:
        assert set(np.unique(ds.read(1))) == {1, 2}


def test_densify_keys_its_cache_on_the_classes_asked_for(
    int16_classes: Path, tmp_path: Path
) -> None:
    # renumbering depends on the code set, so sharing one file between two
    # different sets paints one class with another's colour
    first, first_colors = _densify_class_codes(
        int16_classes, {1: "#ff0000", 2: "#00ff00"}, tmp_path
    )
    second, second_colors = _densify_class_codes(int16_classes, {2: "#00ff00"}, tmp_path)

    assert second != first
    assert first_colors == {1: "#ff0000", 2: "#00ff00"}
    assert second_colors == {1: "#00ff00"}  # class 2 renumbered to 1 on its own


def test_densify_reuses_its_cached_copy(int16_classes: Path, tmp_path: Path) -> None:
    first, _ = _densify_class_codes(int16_classes, {1: "#ff0000"}, tmp_path)
    stamp = first.stat().st_mtime_ns
    second, _ = _densify_class_codes(int16_classes, {1: "#ff0000"}, tmp_path)

    assert second == first
    assert second.stat().st_mtime_ns == stamp  # not rewritten


def test_add_raster_with_class_colors(byte: Path) -> None:
    m = sm.SepalMap()
    layer = m.add_raster(byte, class_colors={1: "#ff0000", 2: "#00ff00"}, key="clas")

    assert isinstance(layer, sm.LayerHandle) and _render(m, layer).kind == "raster-xyz"
    assert m.find_layer("clas") == layer
    assert _params(m, layer)["colormap"].startswith("custom:")


def test_class_colors_draw_their_exact_colors(int16_classes: Path) -> None:
    # regression: an int16 class map rendered fully transparent, because
    # localtileserver rescales a non-uint8 tile onto 0-255 before the colormap
    # and turned the class codes into ramp positions
    m = sm.SepalMap()
    layer = m.add_raster(int16_classes, class_colors={1: "#ff0000", 2: "#00ff00"}, key="i16")

    assert _rendered_colors(m, layer) == {(255, 0, 0), (0, 255, 0)}


def test_class_colors_above_a_byte_draw_their_exact_colors(tmp_path: Path) -> None:
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    source = tmp_path / "high.tif"
    data = np.full((64, 64), 300, dtype="int32")
    data[:, 32:] = 1024
    with rio.open(
        source,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=1,
        dtype="int32",
        crs="EPSG:4326",
        transform=from_origin(0, 0, 0.01, 0.01),
    ) as ds:
        ds.write(data, 1)

    m = sm.SepalMap()
    layer = m.add_raster(source, class_colors={300: "#0000ff", 1024: "#ffffff"}, key="high")

    assert _rendered_colors(m, layer) == {(0, 0, 255), (255, 255, 255)}


def test_class_colors_leave_undeclared_values_transparent(tmp_path: Path) -> None:
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    source = tmp_path / "stray.tif"
    data = np.ones((64, 64), dtype="int16")
    data[:, 32:] = 257  # wraps onto class 1 if the renderer casts to uint8
    with rio.open(
        source,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=from_origin(0, 0, 0.01, 0.01),
    ) as ds:
        ds.write(data, 1)

    m = sm.SepalMap()
    layer = m.add_raster(source, class_colors={1: "#ff0000"}, key="stray")

    assert _rendered_colors(m, layer) == {(255, 0, 0)}


def test_class_colors_ignore_a_caller_supplied_range(int16_classes: Path, caplog) -> None:
    # a caller's vmin/vmax would rescale the class codes and blank the raster
    m = sm.SepalMap()
    layer = m.add_raster(
        int16_classes, class_colors={1: "#ff0000", 2: "#00ff00"}, vmin=1, vmax=2, key="pin"
    )

    params = _params(m, layer)
    assert (params["vmin"], params["vmax"]) == ("0", "255")
    assert "vmin/vmax are ignored" in caplog.text


@pytest.mark.asyncio
async def test_add_raster_async_matches_the_sync_call(int16_classes: Path) -> None:
    colors = {1: "#ff0000", 2: "#00ff00"}
    m = sm.SepalMap()
    layer = await m.add_raster_async(int16_classes, class_colors=colors, key="a")
    m.layer_engine.flush()

    assert m.find_layer("a") == layer
    assert _rendered_colors(m, layer) == {(255, 0, 0), (0, 255, 0)}


@pytest.mark.asyncio
async def test_add_raster_async_prepares_off_the_loop(byte: Path, monkeypatch) -> None:
    # the whole point: rewriting the pixels must not run on the thread driving the UI
    import threading

    import pysepal.mapping.tiling as sepal_map

    calling_thread = {}
    real = sepal_map._optimize_for_tiles

    def _record(*args, **kwargs):
        calling_thread["name"] = threading.current_thread()
        return real(*args, **kwargs)

    monkeypatch.setattr(sepal_map, "_optimize_for_tiles", _record)

    m = sm.SepalMap()
    await m.add_raster_async(byte, key="off")

    assert calling_thread["name"] is not threading.current_thread()


def test_add_raster_points_the_inspector_at_the_source(byte: Path) -> None:
    # the served file may be a prepared COG copy; the inspector must report
    # values from the raster the caller supplied
    m = sm.SepalMap()
    layer = m.add_raster(byte, class_colors={1: "#ff0000"}, key="clas")

    assert _render(m, layer).raster == str(byte)


def test_empty_class_colors_takes_the_continuous_path(byte: Path) -> None:
    m = sm.SepalMap()
    layer = m.add_raster(byte, class_colors={}, layer_name="empty", key="empty")

    assert m.find_layer("empty") == layer
    assert not _params(m, layer).get("colormap", "").startswith("custom:")


def test_falls_back_to_continuous_when_registration_is_unavailable(byte: Path, monkeypatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _no_palettes(name, *args, **kwargs):
        if name == "localtileserver.tiler.palettes":
            raise ImportError("no palette registry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_palettes)

    m = sm.SepalMap()
    layer = m.add_raster(byte, class_colors={1: "#ff0000"}, layer_name="fb", key="fb")

    assert m.find_layer("fb") == layer
    assert not _params(m, layer).get("colormap", "").startswith("custom:")


def test_a_broken_class_color_is_not_swallowed(byte: Path) -> None:
    # a bad hex used to fall back to the continuous ramp while logging that the
    # palette registry was unavailable, which was never the actual problem
    m = sm.SepalMap()
    with pytest.raises(ValueError):
        m.add_raster(byte, class_colors={1: "not-a-color"}, key="bad")


def test_colormap_reaches_the_tile_server(byte: Path) -> None:
    # regression: the colormap used to be sampled into a large-image style dict,
    # which get_leaflet_tile_layer hands to the widget instead of the renderer --
    # so every raster drew with localtileserver's default, whatever was asked for
    m = sm.SepalMap()
    layer = m.add_raster(byte, colormap="viridis", key="v")

    assert _params(m, layer)["colormap"] == "viridis"


def test_colormap_object_is_registered_server_side(byte: Path) -> None:
    # a computed ramp (a QGIS translation, say) rather than a named one; this
    # used to raise NameError because cmap was only bound for str colormaps
    cmap = LinearSegmentedColormap.from_list("x", ["#228b22", "#ff0000"], N=256)
    m = sm.SepalMap()
    layer = m.add_raster(byte, colormap=cmap, key="c")

    assert _params(m, layer)["colormap"].startswith("custom:")


def test_value_range_and_nodata_reach_the_tile_server(byte: Path) -> None:
    m = sm.SepalMap()
    layer = m.add_raster(byte, colormap="viridis", vmin=1, vmax=14, nodata=0, key="p")

    # numbers, not strings: the layer spec stores the range and nodata as floats
    params = _params(m, layer)
    assert tuple(float(params[k]) for k in ("vmin", "vmax", "nodata")) == (1, 14, 0)


def test_unpinned_range_leaves_the_stretch_to_the_file(byte: Path) -> None:
    m = sm.SepalMap()
    params = _params(m, m.add_raster(byte, key="auto"))

    assert "vmin" not in params and "vmax" not in params


def test_multi_band_source_renders_as_an_rgb_composite(rgb: Path) -> None:
    m = sm.SepalMap()
    params = _params(m, m.add_raster(rgb, key="rgb"))

    # band indexes, no colormap: an RGB composite is not a ramp
    assert params["indexes"] == "3,2,1"
    assert "colormap" not in params


def test_explicit_band_on_a_multi_band_source_uses_a_ramp(rgb: Path) -> None:
    m = sm.SepalMap()
    params = _params(m, m.add_raster(rgb, bands=2, colormap="viridis", key="one"))

    assert params["indexes"] == "2"
    assert params["colormap"] == "viridis"


def write_rgb(tmp_path: Path) -> Path:
    """Write a small 3-band uint8 GeoTIFF, so the test needs no download."""
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    path = tmp_path / "rgb.tif"
    data = np.stack([np.full((64, 64), value, dtype="uint8") for value in (10, 120, 240)])
    data[:, :, 32:] //= 2
    with rio.open(
        path,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=3,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_origin(0, 0, 0.01, 0.01),
    ) as ds:
        ds.write(data)
    return path


def test_band_selection_through_the_wrapper(tmp_path: Path) -> None:
    path = write_rgb(tmp_path)
    m = sm.SepalMap()
    one = _params(m, m.add_raster(path, bands=2, colormap="viridis", key="one"))
    # inherits the "inferno" default
    rgb = _params(m, m.add_raster(path, bands=[3, 2, 1], key="rgb"))
    assert (one["indexes"], one["colormap"]) == ("2", "viridis")
    assert rgb["indexes"] == "3,2,1" and "colormap" not in rgb


def test_styling_survives_a_restyle_with_the_same_values(byte: Path) -> None:
    # the store keeps a spec, not the wrapper's arguments: an int band, a Colormap
    # object, the range, nodata and warping reach the tile server, and a restyle
    # that round-trips the same style reuses that render instead of preparing anew
    import rasterio as rio

    cmap = LinearSegmentedColormap.from_list("x", ["#228b22", "#ff0000"], N=256)
    m = sm.SepalMap()
    kwargs = dict(bands=1, colormap=cmap, vmin=1, vmax=14, nodata=0, warp_to_3857=True)
    layer = m.add_raster(byte, key="r", **kwargs)
    first = _drawn_url(m, layer)
    m.layer_store.restyle("r", **m.layer_store.get("r").style.model_dump())

    assert _drawn_url(m, m.find_layer("r")) == first
    params = _params(m, layer)
    assert params["indexes"] == "1" and params["colormap"].startswith("custom:")
    assert tuple(float(params[k]) for k in ("vmin", "vmax", "nodata")) == (1, 14, 0)
    with rio.open(_served_file(m, layer)) as ds:
        assert ds.crs.to_epsg() == 3857


@pytest.mark.parametrize("fixture", ["byte", "rgb"])
def test_fit_bounds_frames_the_whole_raster(fixture: str, request) -> None:
    # localtileserver's default_zoom frames a raster in a 256px tile rather than
    # in the map; the map asks the browser to fit the raster's own bounds instead
    m = sm.SepalMap()
    layer = m.add_raster(request.getfixturevalue(fixture), key="fit")

    west, south, east, north = _render(m, layer).bounds
    assert west < east and south < north
    assert m.view_request["bounds"] == [west, south, east, north]
    assert m.view_request["padding"] == 20


def test_fit_bounds_can_be_declined(byte: Path) -> None:
    m = sm.SepalMap()
    before = m.view_request
    m.add_raster(byte, fit_bounds=False, key="still")

    assert m.view_request == before


def test_optimize_serves_a_prepared_copy(byte: Path) -> None:
    m = sm.SepalMap()
    layer = m.add_raster(byte, key="cog")

    assert _served_file(m, layer) != str(byte)  # the cached COG, not the source


def test_warp_reaches_the_tile_server(byte: Path) -> None:
    import rasterio as rio

    m = sm.SepalMap()
    layer = m.add_raster(byte, warp_to_3857=True, key="warp")

    with rio.open(_served_file(m, layer)) as ds:
        assert ds.crs.to_epsg() == 3857


def test_warp_without_optimize_says_so(byte: Path, caplog) -> None:
    # reprojecting means writing a copy, which optimize=False forbids
    m = sm.SepalMap()
    layer = m.add_raster(byte, warp_to_3857=True, optimize=False, key="nowarp")

    assert _served_file(m, layer) == str(byte)
    assert "warp_to_3857 needs optimize=True" in caplog.text


def test_optimize_false_serves_the_source_untouched(byte: Path) -> None:
    # for a large raster you don't want duplicated into the tile cache, or one
    # that already carries .ovr sidecars
    m = sm.SepalMap()
    layer = m.add_raster(byte, optimize=False, key="raw")

    assert _served_file(m, layer) == str(byte)
