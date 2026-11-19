"""Serializable description of a map layer: where the data lives, how it is styled."""

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

import ee
import matplotlib
import numpy as np
from matplotlib.colors import Colormap, is_color_like, to_hex
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_CONFIG = ConfigDict(frozen=True, extra="forbid")
_BARE_HEX = re.compile(r"^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")

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


Source = Annotated[GeeSource | RasterSource | VectorSource, Field(discriminator="type")]


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
    """How a vector layer is rendered. A ``None`` stroke is the theme primary color."""

    model_config = _CONFIG

    type: Literal["vector"] = "vector"
    stroke: str | None = None
    fill: str | None = None
    fill_opacity: float | None = None
    width: float = 2.0
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("stroke", "fill")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        return None if value is None else _normalise_color(value)

    @property
    def effective_fill_opacity(self) -> float:
        """The fill opacity: explicit value, else 0 without a fill and 1 with one."""
        if self.fill_opacity is not None:
            return self.fill_opacity
        return 0.0 if self.fill is None else 1.0

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
