"""The non-serialized, display-ready form of a layer."""

from dataclasses import dataclass, field
from typing import Any, Literal

from .spec import Legend, VectorStyle

RenderKind = Literal["raster-xyz", "geojson", "pmtiles"]


@dataclass(frozen=True)
class RenderLayer:
    """What an engine needs to draw a layer, shareable between layers with one ``render_hash``.

    It carries no id, name or attribution: the engine binds those from the current spec.

    Attributes:
        render_hash: hash of the spec's data and style this was prepared from.
        kind: how the engine draws it.
        url: tile URL template, or the PMTiles URL.
        theme_urls: tile URLs per theme (``True`` for dark), when they differ.
        data: GeoJSON FeatureCollection for ``geojson``.
        bounds: ``(west, south, east, north)`` in lon/lat.
        vector_style: style of vector layers.
        source_layer: vector layer name inside a PMTiles archive.
        legend: legend computed while preparing, if any.
        max_zoom: highest zoom the layer is drawn at.
        tile_size: pixel size of a raster tile.
        ee_object: the Earth Engine object behind the tiles, if any.
        raster: path of the source raster, for the inspector.
        keepalive: object that must outlive the layer (the ``TileClient`` of a local raster).
        tile_kwargs: the tile options of a local raster in the form of Leaflet's
            ``get_leaflet_tile_layer``, kept only to compare with that helper until phase 5
            removes ipyleaflet.
        fingerprint: ``(path, size, mtime_ns)`` of the local files this was built from.
        prepare_options: the ``optimize`` and ``warp_to_3857`` a local raster was prepared with,
            so that a restyle prepares it the same way.
    """

    render_hash: str
    kind: RenderKind
    url: str = ""
    theme_urls: dict[bool, str] | None = None
    data: dict | None = None
    bounds: tuple[float, float, float, float] | None = None
    vector_style: VectorStyle | None = None
    source_layer: str | None = None
    legend: Legend | None = None
    max_zoom: int = 24
    tile_size: int = 256
    ee_object: Any = None
    raster: str = ""
    keepalive: Any = None
    tile_kwargs: dict | None = None
    fingerprint: tuple | None = None
    prepare_options: dict = field(default_factory=dict)
