"""Serializable description of a map layer: where the data lives, how it is styled."""

import atexit
import hashlib
import json
import numbers
import os
import re
import shutil
import tempfile
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import ee
import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
from matplotlib.colors import Colormap, is_color_like, to_hex
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from pysepal.scripts.scratch import scratch_root

_CONFIG = ConfigDict(frozen=True, extra="forbid")
_BARE_HEX = re.compile(r"^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_MAX_SAFE_INTEGER = 2**53 - 1

GeeKind = Literal["Image", "ImageCollection", "FeatureCollection", "Feature", "Geometry"]
VectorFormat = Literal["GeoJSON", "GPKG", "FlatGeobuf", "Parquet", "ESRI Shapefile", "PMTiles"]

_VECTOR_SUFFIXES: dict[str, VectorFormat] = {
    ".geojson": "GeoJSON",
    ".json": "GeoJSON",
    ".gpkg": "GPKG",
    ".fgb": "FlatGeobuf",
    ".parquet": "Parquet",
    ".shp": "ESRI Shapefile",
    ".pmtiles": "PMTiles",
}


def _normalise_color(value: str) -> str:
    """Return a color as lowercase ``#rrggbb``, accepting Earth Engine style bare hex."""
    if isinstance(value, str) and _BARE_HEX.match(value):
        value = f"#{value}"
    if not isinstance(value, str) or not is_color_like(value):
        raise ValueError(f"{value!r} is not a valid color")
    return to_hex(value, keep_alpha=False).lower()


def colormap_stops(name: str, n: int = 16) -> list[str]:
    """Sample a Matplotlib colormap into ``n`` lowercase ``#rrggbb`` stops.

    Args:
        name: Matplotlib colormap name.
        n: number of stops.
    """
    cmap = matplotlib.colormaps[name]
    return [to_hex(cmap(x)).lower() for x in np.linspace(0, 1, n)]


def uri_to_path(uri: str) -> Path:
    """Convert a ``file://`` URI or a bare path to a ``Path``.

    Args:
        uri: a ``file://`` URI or a bare filesystem path.

    Raises:
        ValueError: for any other URI scheme.
    """
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return Path(url2pathname(unquote(parsed.path)))
    if parsed.scheme == "":
        return Path(uri)
    raise ValueError(f"Unsupported URI scheme: {parsed.scheme!r}")


def _to_uri(path_or_url: str | Path) -> str:
    text = str(path_or_url)
    if urlparse(text).scheme in ("http", "https", "file"):
        return text
    return Path(text).expanduser().resolve().as_uri()


def _canonical_hash(obj: Any) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


class GeeSource(BaseModel):
    """An Earth Engine object stored as its serialized expression."""

    model_config = _CONFIG

    type: Literal["gee"] = "gee"
    expr: dict[str, Any]
    kind: GeeKind

    @classmethod
    def from_ee(cls, obj: ee.ComputedObject) -> "GeeSource":
        """Serialize an Earth Engine object."""
        return cls(expr=json.loads(ee.serializer.toJSON(obj)), kind=type(obj).__name__)

    def to_ee(self) -> ee.ComputedObject:
        """Rebuild the Earth Engine object."""
        return getattr(ee, self.kind)(ee.deserializer.fromJSON(json.dumps(self.expr)))


class RasterSource(BaseModel):
    """A local or remote raster file."""

    model_config = _CONFIG

    type: Literal["raster"] = "raster"
    uri: str
    format: str = "GTiff"
    checksum: str | None = None
    size: int | None = None


class VectorSource(BaseModel):
    """A local or remote vector file."""

    model_config = _CONFIG

    type: Literal["vector"] = "vector"
    uri: str
    format: VectorFormat
    layer: str | None = None
    checksum: str | None = None
    size: int | None = None


class TileSource(BaseModel):
    """A remote XYZ or WMS tile service, given as a URL template."""

    model_config = _CONFIG

    type: Literal["tile"] = "tile"
    url: str
    tile_size: int = 256
    max_zoom: int = 24

    @field_validator("url")
    @classmethod
    def _placeholders(cls, value: str) -> str:
        xyz = all(token in value for token in ("{z}", "{x}", "{y}"))
        if not xyz and "{bbox-epsg-3857}" not in value:
            raise ValueError("a tile url needs {z}, {x} and {y}, or {bbox-epsg-3857}")
        return value

    @field_validator("tile_size")
    @classmethod
    def _positive_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("tile_size must be positive")
        return value

    @field_validator("max_zoom")
    @classmethod
    def _zoom_range(cls, value: int) -> int:
        if not 0 <= value <= 24:
            raise ValueError("max_zoom must be between 0 and 24")
        return value

    @classmethod
    def wms(
        cls,
        url: str,
        layers: str,
        *,
        styles: str = "",
        format: str = "image/png",
        transparent: bool = True,
        version: str = "1.3.0",
    ) -> "TileSource":
        """Build a WMS GetMap template in Web Mercator, keeping any query already in ``url``.

        Args:
            url: the WMS endpoint, with an optional query string.
            layers: comma-separated layer names.
            styles: comma-separated style names.
            format: image format.
            transparent: ask for a transparent background.
            version: WMS version; 1.3.0 sends ``CRS``, older ones ``SRS``.
        """
        crs = "CRS" if version == "1.3.0" else "SRS"
        params = (
            f"SERVICE=WMS&REQUEST=GetMap&VERSION={version}&LAYERS={layers}&STYLES={styles}"
            f"&FORMAT={format}&TRANSPARENT={str(transparent).upper()}&{crs}=EPSG:3857"
            "&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}"
        )
        joiner = "" if url.endswith(("?", "&")) else ("&" if "?" in url else "?")
        return cls(url=f"{url}{joiner}{params}")


Source = Annotated[
    GeeSource | RasterSource | VectorSource | TileSource, Field(discriminator="type")
]


class RasterStyle(BaseModel):
    """How a raster or Earth Engine image is rendered."""

    model_config = _CONFIG

    type: Literal["raster"] = "raster"
    bands: list[int | str] | None = None
    min: float | list[float] | None = None
    max: float | list[float] | None = None
    palette: list[str] | None = None
    colormap: str | None = None
    class_colors: dict[int, str] | None = None
    class_labels: dict[int, str] | None = None
    nodata: float | None = None
    gamma: float | list[float] | None = None
    viz_name: str = ""
    use_asset_viz: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("palette")
    @classmethod
    def _palette_colors(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else [_normalise_color(c) for c in value]

    @field_validator("class_colors")
    @classmethod
    def _class_colors(cls, value: dict[int, str] | None) -> dict[int, str] | None:
        return None if value is None else {k: _normalise_color(v) for k, v in value.items()}

    @model_validator(mode="after")
    def _check_color_ramp(self) -> "RasterStyle":
        if self.palette is not None and self.colormap is not None:
            raise ValueError("palette and colormap are mutually exclusive")
        if self.colormap is not None and self.bands is not None and len(self.bands) > 1:
            raise ValueError("a colormap needs a single band")
        return self

    def to_ee_vis_params(self) -> dict:
        """Return Earth Engine visualization parameters (a colormap becomes a palette)."""
        palette = colormap_stops(self.colormap) if self.colormap else self.palette
        params = {
            "bands": self.bands,
            "min": self.min,
            "max": self.max,
            "palette": palette,
            "gamma": self.gamma,
        }
        return {**{k: v for k, v in params.items() if v is not None}, **self.extra}


class VectorStyle(BaseModel):
    """How a vector layer is rendered. A ``None`` stroke is the theme primary color.

    ``color_by`` names a feature property and ``class_colors`` gives its values
    their colors; the two go together. A feature whose value is not a key, a
    value of the other type (``"1"`` is not ``1``), a null or a missing property
    keeps the style's own color. Keys are all ``str`` or all ``int``. Only
    vectors the browser draws take classes: Earth Engine vectors refuse them.
    """

    model_config = _CONFIG

    type: Literal["vector"] = "vector"
    stroke: str | None = None
    fill: str | None = None
    fill_opacity: float | None = None
    width: float = 2.0
    radius: float = Field(default=5.0, ge=0)
    marker: Literal["circle", "pin"] = "circle"
    cluster: bool = False
    cluster_radius: int = Field(default=50, ge=1)
    cluster_max_zoom: int = Field(default=14, ge=1, le=17)
    popup: bool | list[str] = False
    tooltip: bool | list[str] = False
    color_by: str | None = Field(default=None, min_length=1)
    class_colors: dict[str | int, str] | None = None
    class_labels: dict[str | int, str] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stroke", "fill")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        return None if value is None else _normalise_color(value)

    @field_validator("class_colors", "class_labels", mode="before")
    @classmethod
    def _class_keys(cls, value: Any) -> Any:
        # pydantic would turn a bool key into an int, and a float key too
        if isinstance(value, (list, tuple)):
            pairs = []
            for pair in value:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError(f"classes must be (class, value) pairs, got {pair!r}")
                pairs.append(tuple(pair))
            try:
                value = dict(pairs)
            except TypeError:
                raise ValueError(f"classes must be str or int, got {pairs!r}") from None
            if len(value) != len(pairs):
                raise ValueError("classes must be unique")
        if not isinstance(value, dict):
            return value
        kinds = set()
        for key in value:
            if isinstance(key, str):
                kinds.add(str)
            elif isinstance(key, numbers.Integral) and not isinstance(key, bool):
                if abs(key) > _MAX_SAFE_INTEGER:
                    raise ValueError(f"class {key!r} is beyond what JavaScript holds exactly")
                kinds.add(int)
            else:
                raise ValueError(f"classes must be str or int, got {key!r}")
        if len(kinds) > 1:
            raise ValueError("classes must be all str or all int")
        return value

    @field_validator("class_colors")
    @classmethod
    def _class_colors(cls, value: dict[str | int, str] | None) -> dict[str | int, str] | None:
        return None if value is None else {k: _normalise_color(v) for k, v in value.items()}

    @field_serializer("class_colors", "class_labels", when_used="json")
    def _classes_as_pairs(self, value: dict[str | int, str] | None) -> list[list] | None:
        # JSON object keys are strings; pairs keep an int class an int, and the order, in the
        # render hash and through a round trip
        return None if value is None else [[k, v] for k, v in value.items()]

    @field_validator("popup", "tooltip")
    @classmethod
    def _fields_not_empty(cls, value: bool | list[str]) -> bool | list[str]:
        if isinstance(value, list) and not value:
            raise ValueError("name at least one property, or use True for all of them")
        return value

    @model_validator(mode="after")
    def _pin_is_visible(self) -> "VectorStyle":
        # a pin's icon size is radius / 5, so a zero radius makes it vanish
        if self.marker == "pin" and self.radius <= 0:
            raise ValueError("a pin needs a radius above 0")
        return self

    @model_validator(mode="after")
    def _classes_pair(self) -> "VectorStyle":
        if (self.color_by is None) != (not self.class_colors):
            raise ValueError("color_by and a non-empty class_colors must be given together")
        return self

    @property
    def effective_fill_opacity(self) -> float:
        """The fill opacity: explicit value, else 1 with a fill or classes and 0 without."""
        if self.fill_opacity is not None:
            return self.fill_opacity
        return 0.0 if self.fill is None and not self.class_colors else 1.0

    def to_ee_style_params(self) -> dict:
        """Return Earth Engine ``FeatureCollection.style`` parameters."""
        params: dict[str, Any] = {}
        if self.stroke is not None:
            params["color"] = self.stroke.lstrip("#")
        if self.fill is not None:
            alpha = int(self.effective_fill_opacity * 255 + 0.5)
            params["fillColor"] = f"{self.fill.lstrip('#')}{alpha:02x}"
        params["width"] = self.width
        return {**params, **self.extra}

    @classmethod
    def from_ee_style(cls, vis_params: dict) -> "VectorStyle":
        """Normalise Earth Engine feature style parameters."""
        kwargs: dict[str, Any] = {}
        extra: dict[str, Any] = {}
        for key, value in vis_params.items():
            if value is None:
                continue
            if key == "color":
                kwargs["stroke"] = value
            elif key == "fillColor":
                text = str(value).lstrip("#")
                if len(text) == 8 and _BARE_HEX.match(text):
                    kwargs["fill_opacity"] = int(text[6:], 16) / 255
                    text = text[:6]
                kwargs["fill"] = text
            elif key == "width":
                kwargs["width"] = value
            else:
                extra[key] = value
        return cls(**kwargs, extra=extra)


Style = Annotated[RasterStyle | VectorStyle, Field(discriminator="type")]


class Gradient(BaseModel):
    """A continuous color ramp in a legend."""

    colors: list[str]
    labels: list[str]
    title: str = ""


class LegendItem(BaseModel):
    """One categorical legend entry."""

    label: str
    color: str
    detail: str = ""


class Legend(BaseModel):
    """Legend content, shaped like ``LegendData`` of the Solara legend component."""

    title: str = ""
    gradients: list[Gradient] = Field(default_factory=list)
    items: list[LegendItem] = Field(default_factory=list)


class LayerSpec(BaseModel):
    """A serializable layer: source data, reserved ops and style."""

    model_config = _CONFIG

    id: str
    revision: int = 0
    parent: str | None = None
    name: str
    description: str = ""
    attribution: str = ""
    zone: Literal["data", "overlay"] = "data"
    source: Source
    ops: list[Any] = Field(default_factory=list)
    style: Style
    legend: Legend | None = None
    derived_from: list[str] = Field(default_factory=list)

    @field_validator("ops")
    @classmethod
    def _ops_reserved(cls, value: list[Any]) -> list[Any]:
        if value:
            raise NotImplementedError("layer ops are reserved")
        return value

    @property
    def data_hash(self) -> str:
        """Hash of what is drawn (source and ops), independent of styling."""
        return _canonical_hash(self.model_dump(mode="json", include={"source", "ops"}))

    @property
    def render_hash(self) -> str:
        """Hash of the data and the style."""
        style = self.model_dump(mode="json", include={"style"})["style"]
        return _canonical_hash({"data_hash": self.data_hash, "style": style})

    def revise(self, **changes: Any) -> "LayerSpec":
        """Return a copy with ``changes`` applied, revision bumped and ``parent`` set."""
        fields = {name: getattr(self, name) for name in type(self).model_fields}
        fields.update(changes)
        fields.update(revision=self.revision + 1, parent=self.render_hash)
        return type(self)(**fields)

    @classmethod
    def from_ee(
        cls,
        obj: ee.ComputedObject,
        vis_params: dict | None = None,
        *,
        name: str,
        id: str | None = None,
        viz_name: str = "",
        use_asset_viz: bool = True,
        attribution: str = "Google Earth Engine",
    ) -> "LayerSpec":
        """Build a spec from an Earth Engine object and its visualization parameters."""
        source = GeeSource.from_ee(obj)
        params = dict(vis_params or {})
        if source.kind in ("FeatureCollection", "Feature", "Geometry"):
            style: RasterStyle | VectorStyle = VectorStyle.from_ee_style(params)
        else:
            style = _raster_style_from_ee(params, viz_name, use_asset_viz)
        return cls(
            id=id or uuid.uuid4().hex,
            name=name,
            attribution=attribution,
            source=source,
            style=style,
        )

    @classmethod
    def from_raster(
        cls,
        path: str | Path,
        *,
        name: str | None = None,
        id: str | None = None,
        bands: int | str | list[int | str] | None = None,
        colormap: str | Colormap | None = "inferno",
        palette: list[str] | None = None,
        class_colors: dict[int, str] | None = None,
        vmin: float | None = None,
        vmax: float | None = None,
        nodata: float | None = None,
    ) -> "LayerSpec":
        """Build a spec from a raster file, normalising the legacy wrapper inputs."""
        if bands is not None and not isinstance(bands, list):
            bands = [bands]
        if isinstance(colormap, Colormap):
            palette = palette or [to_hex(c) for c in colormap(np.linspace(0, 1, 256))]
            colormap = None
        if palette is not None or (bands is not None and len(bands) > 1):
            colormap = None
        style = RasterStyle(
            bands=bands,
            min=vmin,
            max=vmax,
            palette=palette,
            colormap=colormap,
            class_colors=class_colors,
            nodata=nodata,
        )
        uri = _to_uri(path)
        return cls(
            id=id or uuid.uuid4().hex,
            name=name or Path(urlparse(uri).path).stem,
            source=RasterSource(uri=uri),
            style=style,
        )

    @classmethod
    def from_vector(
        cls,
        path_or_url: str | Path,
        *,
        name: str | None = None,
        id: str | None = None,
        layer: str | None = None,
        stroke: str | None = None,
        fill: str | None = None,
        width: float = 2.0,
    ) -> "LayerSpec":
        """Build a spec from a vector file or URL, inferring the format from the suffix."""
        uri = _to_uri(path_or_url)
        suffix = Path(urlparse(uri).path).suffix.lower()
        if suffix not in _VECTOR_SUFFIXES:
            raise ValueError(f"Unsupported vector format: {suffix!r}")
        source = VectorSource(uri=uri, format=_VECTOR_SUFFIXES[suffix], layer=layer)
        return cls(
            id=id or uuid.uuid4().hex,
            name=name or Path(urlparse(uri).path).stem,
            source=source,
            style=VectorStyle(stroke=stroke, fill=fill, width=width),
        )

    @classmethod
    def from_tiles(
        cls,
        source: "TileSource | str",
        *,
        name: str,
        id: str | None = None,
        attribution: str = "",
        zone: Literal["data", "overlay"] = "data",
    ) -> "LayerSpec":
        """Build a spec from a tile source, or from a tile URL template."""
        if isinstance(source, str):
            source = TileSource(url=source)
        return cls(
            id=id or uuid.uuid4().hex,
            name=name,
            attribution=attribution,
            zone=zone,
            source=source,
            style=RasterStyle(),
        )

    @classmethod
    def from_geojson(
        cls,
        data: "dict | gpd.GeoDataFrame",
        *,
        name: str,
        id: str | None = None,
        style: VectorStyle | None = None,
        zone: Literal["data", "overlay"] = "data",
        attribution: str = "",
    ) -> "LayerSpec":
        """Build a spec from in-memory vector data, stored as a content-addressed GeoParquet.

        Args:
            data: a GeoJSON FeatureCollection or Feature (EPSG:4326), or a GeoDataFrame with a CRS.
            name: layer name.
            id: layer id, a new UUID by default.
            style: vector style.
            zone: drawing zone.
            attribution: attribution text.

        Raises:
            TypeError: for any other ``data``.
            ValueError: for a GeoDataFrame without a CRS.
        """
        if isinstance(data, gpd.GeoDataFrame):
            if data.crs is None:
                raise ValueError("the GeoDataFrame has no CRS")
            gdf = data
        elif isinstance(data, dict):
            features = data["features"] if data.get("type") == "FeatureCollection" else [data]
            gdf = gpd.GeoDataFrame.from_features(features, crs=4326)
        else:
            raise TypeError(f"expected a GeoJSON dict or a GeoDataFrame, got {type(data).__name__}")
        path = _write_parquet(gdf)
        source = VectorSource(
            uri=path.as_uri(),
            format="Parquet",
            checksum=path.stem,
            size=path.stat().st_size,
        )
        return cls(
            id=id or uuid.uuid4().hex,
            name=name,
            attribution=attribution,
            zone=zone,
            source=source,
            style=style or VectorStyle(),
        )

    @classmethod
    def from_points(
        cls,
        data: "gpd.GeoDataFrame | dict | pd.DataFrame | Sequence[tuple[float, float]]",
        *,
        name: str,
        lng: str = "lng",
        lat: str = "lat",
        id: str | None = None,
        style: VectorStyle | None = None,
        zone: Literal["data", "overlay"] = "data",
        attribution: str = "",
    ) -> "LayerSpec":
        """Build a point layer, stored through :meth:`from_geojson`.

        Args:
            data: a GeoDataFrame of points, a GeoJSON dict of points, a DataFrame with
                ``lng`` and ``lat`` columns (the others become properties), or a sequence of
                ``(lng, lat)`` pairs.
            name: layer name.
            lng: longitude column of a DataFrame.
            lat: latitude column of a DataFrame.
            id: layer id, a new UUID by default.
            style: vector style, by default a circle filled and outlined in the theme color.
                Pass ``VectorStyle(marker="pin")`` for pins, and ``color_by`` with
                ``class_colors`` to color the points by class.
            zone: drawing zone.
            attribution: attribution text.

        Raises:
            ValueError: for non-point geometries, missing columns or non-finite coordinates.
            TypeError: for any other ``data``.
        """
        if isinstance(data, gpd.GeoDataFrame):
            gdf = data
        elif isinstance(data, dict):
            if data.get("type") == "FeatureCollection":
                features = data["features"]
            elif data.get("type") == "Feature":
                features = [data]
            else:  # a bare geometry
                features = [{"type": "Feature", "properties": {}, "geometry": data}]
            gdf = gpd.GeoDataFrame.from_features(features, crs=4326)
        elif isinstance(data, pd.DataFrame):
            missing = [c for c in (lng, lat) if c not in data.columns]
            if missing:
                raise ValueError(f"the DataFrame has no column {', '.join(missing)}")
            xs = pd.to_numeric(data[lng], errors="coerce")
            ys = pd.to_numeric(data[lat], errors="coerce")
            rest = data.drop(columns=[lng, lat])
            gdf = gpd.GeoDataFrame(rest, geometry=gpd.points_from_xy(xs, ys), crs=4326)
        elif isinstance(data, Sequence) and not isinstance(data, (str, bytes)):
            try:
                pairs = np.asarray(data, dtype=float)
            except (TypeError, ValueError) as exc:
                raise ValueError("expected (lng, lat) pairs") from exc
            if pairs.size == 0:
                pairs = pairs.reshape(0, 2)
            elif pairs.ndim != 2 or pairs.shape[1] != 2:
                raise ValueError("expected (lng, lat) pairs")
            gdf = gpd.GeoDataFrame(geometry=gpd.points_from_xy(pairs[:, 0], pairs[:, 1]), crs=4326)
        else:
            raise TypeError(
                "expected a GeoDataFrame, a GeoJSON dict, a DataFrame or (lng, lat) pairs, "
                f"got {type(data).__name__}"
            )
        geometry = gdf.geometry
        if not (geometry.geom_type == "Point").all():
            raise ValueError("from_points needs Point geometries only")
        if not (np.isfinite(geometry.x) & np.isfinite(geometry.y)).all():
            raise ValueError("coordinates must be finite")
        return cls.from_geojson(
            gdf,
            name=name,
            id=id,
            style=style or VectorStyle(fill_opacity=1.0),
            zone=zone,
            attribution=attribution,
        )


_scratch_folder: Path | None = None
_scratch_lock = threading.Lock()


def _geojson_folder() -> Path:
    """The per-process folder of in-memory vectors, made on first use and removed at exit."""
    global _scratch_folder
    with _scratch_lock:
        if _scratch_folder is None:
            _scratch_folder = Path(tempfile.mkdtemp(prefix="pysepal_geojson_", dir=scratch_root()))
            atexit.register(shutil.rmtree, _scratch_folder, ignore_errors=True)
        return _scratch_folder


def _write_parquet(gdf: "gpd.GeoDataFrame") -> Path:
    """Write ``gdf`` as ``<sha256>.parquet`` once; an existing file is never touched."""
    folder = _geojson_folder()
    fd, temp = tempfile.mkstemp(suffix=".tmp", dir=folder)
    os.close(fd)
    try:
        gdf.to_parquet(temp)
        digest = hashlib.sha256(Path(temp).read_bytes()).hexdigest()
        final = folder / f"{digest}.parquet"
        if not final.exists():
            try:
                os.link(temp, final)
            except FileExistsError:
                pass
        return final
    finally:
        Path(temp).unlink(missing_ok=True)


def _as_list(value: Any) -> Any:
    if isinstance(value, str):
        return [v.strip() for v in value.split(",")]
    return value


def _raster_style_from_ee(params: dict, viz_name: str, use_asset_viz: bool) -> RasterStyle:
    params = dict(params)
    kwargs: dict[str, Any] = {"viz_name": viz_name, "use_asset_viz": use_asset_viz}
    if "bands" in params:
        kwargs["bands"] = _as_list(params.pop("bands"))
    for key in ("min", "max", "gamma"):
        if key in params:
            value = params.pop(key)
            if isinstance(value, str):
                values = [float(v) for v in value.split(",")]
                value = values[0] if len(values) == 1 else values
            kwargs[key] = value
    if "palette" in params:
        kwargs["palette"] = _as_list(params.pop("palette"))
    return RasterStyle(**kwargs, extra=params)
