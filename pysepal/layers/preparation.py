"""Turn a :class:`LayerSpec` into a :class:`RenderLayer`."""

import asyncio
import dataclasses
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from pysepal.scripts.gee_interface import GEEInterface

from .render import RenderLayer
from .spec import LayerSpec, RasterSource, VectorSource, uri_to_path

log = logging.getLogger("sepalui.layers")

GEOJSON_WARN_BYTES = 20_000_000
SHAPEFILE_SIDECARS = (
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".sbn",
    ".sbx",
    ".qix",
    ".fix",
    ".shp.xml",
)
_RASTER_SIDECARS = (".ovr", ".aux.xml")


class LayerPrepareError(Exception):
    """A layer could not be prepared for display."""

    def __init__(self, message: str, *, layer_id: str) -> None:
        """Build the error.

        Args:
            message: what went wrong.
            layer_id: id of the layer that failed.
        """
        super().__init__(message)
        self.layer_id = layer_id


def _is_local(uri: str) -> bool:
    return urlparse(uri).scheme in ("", "file")


def local_files(spec: LayerSpec) -> list[Path]:
    """List the main file of a local source plus the sidecars that exist next to it.

    Args:
        spec: the layer spec.

    Returns:
        The files, or ``[]`` for sources that are not local files.
    """
    source = spec.source
    if not isinstance(source, (RasterSource, VectorSource)) or not _is_local(source.uri):
        return []
    main = uri_to_path(source.uri)
    if isinstance(source, RasterSource):
        extras = [Path(f"{main}{suffix}") for suffix in _RASTER_SIDECARS]
    elif source.format == "ESRI Shapefile":
        extras = [Path(f"{main.with_suffix('')}{suffix}") for suffix in SHAPEFILE_SIDECARS]
    else:
        extras = []
    return [main] + [p for p in extras if p != main and p.exists()]


def local_fingerprint(spec: LayerSpec) -> tuple[tuple[str, int, int], ...] | None:
    """Return ``(path, size, mtime_ns)`` of each local file, to detect changes on disk.

    Args:
        spec: the layer spec.

    Returns:
        ``None`` for sources that are not local files.

    Raises:
        FileNotFoundError: when the main file is gone.
    """
    files = local_files(spec)
    if not files:
        return None
    stats = [(p, os.stat(p)) for p in files]
    return tuple((str(p), st.st_size, st.st_mtime_ns) for p, st in stats)


def _check_supported(spec: LayerSpec) -> None:
    """Fail early, with a readable cause, on sources that cannot be prepared here."""
    source = spec.source
    if source.type == "gee":
        raise NotImplementedError("Earth Engine layers are prepared by a later step")
    if not _is_local(source.uri):
        if source.type == "raster":
            raise ValueError("remote rasters are not supported")
        return
    if source.type == "vector" and source.format == "PMTiles":
        raise ValueError("local PMTiles files are not supported, serve them over http(s)")
    path = uri_to_path(source.uri)
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")


def _remote_pmtiles(spec: LayerSpec) -> RenderLayer | None:
    source = spec.source
    if source.type != "vector" or source.format != "PMTiles" or _is_local(source.uri):
        return None
    return RenderLayer(
        render_hash=spec.render_hash,
        kind="pmtiles",
        url=source.uri,
        source_layer=source.layer,
        vector_style=spec.style,
    )


def _read_vector(source: VectorSource) -> tuple[dict, tuple | None]:
    import geopandas as gpd

    path = uri_to_path(source.uri) if _is_local(source.uri) else source.uri
    if source.format == "Parquet":
        gdf = gpd.read_parquet(path)
    else:
        gdf = gpd.read_file(path, layer=source.layer)
    gdf = gdf.to_crs(4326)
    text = gdf.to_json()
    if len(text) > GEOJSON_WARN_BYTES:
        log.warning(
            "GeoJSON for %s is %.0f MB; consider a PMTiles source for large vectors.",
            source.uri,
            len(text) / 1e6,
        )
    bounds = None if gdf.empty else tuple(float(v) for v in gdf.total_bounds)
    return json.loads(text), bounds


def _vector_render(spec: LayerSpec, payload: tuple[dict, tuple | None]) -> RenderLayer:
    data, bounds = payload
    return RenderLayer(
        render_hash=spec.render_hash,
        kind="geojson",
        data=data,
        bounds=bounds,
        vector_style=spec.style,
    )


def _scalar(value):
    return value[0] if isinstance(value, list) else value


def _raster_render(spec: LayerSpec, served: str, class_colors: dict | None) -> RenderLayer:
    """Build the tile URL on the calling thread, the way ``SepalMap`` attaches rasters."""
    from localtileserver import TileClient, get_leaflet_tile_layer
    from matplotlib.colors import LinearSegmentedColormap

    from pysepal.mapping.raster_style import (
        _class_color_kwargs,
        _continuous_color_kwargs,
    )
    from pysepal.mapping.sepal_map import CLIENT_PREFIX_ENV_VAR

    style = spec.style
    image = uri_to_path(spec.source.uri)
    client = TileClient(served, client_prefix=os.environ.get(CLIENT_PREFIX_ENV_VAR))

    color_kwargs = _class_color_kwargs(class_colors) if class_colors else None
    if class_colors and color_kwargs is None:
        log.warning("localtileserver register_colormap unavailable; %s is drawn as a ramp.", image)
    if color_kwargs is None:
        colormap = style.colormap
        if style.palette:
            colormap = LinearSegmentedColormap.from_list("palette", style.palette)
        color_kwargs = _continuous_color_kwargs(image, style.bands, colormap or "inferno")
        if colormap is None:
            color_kwargs.pop("colormap", None)
        color_kwargs |= {"vmin": _scalar(style.min), "vmax": _scalar(style.max)}
    elif style.min is not None or style.max is not None:
        log.warning("vmin/vmax are ignored when class_colors is set.")

    tile_kwargs = dict(max_zoom=20, max_native_zoom=20, nodata=style.nodata, **color_kwargs)
    widget = get_leaflet_tile_layer(client, **tile_kwargs)
    try:
        url = widget.url
        (south, west), (north, east) = widget.bounds
    finally:
        widget.close()
    return RenderLayer(
        render_hash=spec.render_hash,
        kind="raster-xyz",
        url=url,
        bounds=(west, south, east, north),
        max_zoom=20,
        raster=str(image),
        keepalive=client,
        tile_kwargs=tile_kwargs,
    )


async def prepare(
    spec: LayerSpec,
    *,
    gee_interface: GEEInterface | None = None,
    optimize: bool = True,
    warp_to_3857: bool = False,
) -> RenderLayer:
    """Prepare a spec for display, running the heavy file work off the calling thread.

    Args:
        spec: the layer spec.
        gee_interface: interface for Earth Engine sources.
        optimize: convert rasters to a tiling-friendly COG first.
        warp_to_3857: reproject rasters to Web Mercator while optimizing.

    Returns:
        The render layer.

    Raises:
        LayerPrepareError: when the layer cannot be prepared.
        NotImplementedError: for Earth Engine sources.
    """
    from pysepal.mapping.tiling import prepare_raster_file

    try:
        _check_supported(spec)
        if (render := _remote_pmtiles(spec)) is not None:
            return render
        fingerprint = local_fingerprint(spec)
        if spec.source.type == "raster":
            served, class_colors = await asyncio.to_thread(
                prepare_raster_file,
                uri_to_path(spec.source.uri),
                spec.style.class_colors,
                optimize,
                warp_to_3857,
            )
            render = _raster_render(spec, served, class_colors)
        else:
            render = _vector_render(spec, await asyncio.to_thread(_read_vector, spec.source))
        return dataclasses.replace(render, fingerprint=fingerprint)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise LayerPrepareError(f"{spec.name}: {exc}", layer_id=spec.id) from exc


def prepare_sync(
    spec: LayerSpec,
    *,
    gee_interface: GEEInterface | None = None,
    optimize: bool = True,
    warp_to_3857: bool = False,
) -> RenderLayer:
    """Blocking twin of :func:`prepare`, safe to call inside a running event loop.

    Args:
        spec: the layer spec.
        gee_interface: interface for Earth Engine sources.
        optimize: convert rasters to a tiling-friendly COG first.
        warp_to_3857: reproject rasters to Web Mercator while optimizing.

    Returns:
        The render layer.

    Raises:
        LayerPrepareError: when the layer cannot be prepared.
        NotImplementedError: for Earth Engine sources.
    """
    from pysepal.mapping.tiling import prepare_raster_file

    try:
        _check_supported(spec)
        if (render := _remote_pmtiles(spec)) is not None:
            return render
        fingerprint = local_fingerprint(spec)
        if spec.source.type == "raster":
            served, class_colors = prepare_raster_file(
                uri_to_path(spec.source.uri),
                spec.style.class_colors,
                optimize,
                warp_to_3857,
            )
            render = _raster_render(spec, served, class_colors)
        else:
            render = _vector_render(spec, _read_vector(spec.source))
        return dataclasses.replace(render, fingerprint=fingerprint)
    except NotImplementedError:
        raise
    except Exception as exc:
        raise LayerPrepareError(f"{spec.name}: {exc}", layer_id=spec.id) from exc
