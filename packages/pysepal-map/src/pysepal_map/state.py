"""Frozen declarations of everything a map persistently shows."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

THEMES = ("light", "dark")
ZONES = ("data", "overlay")


def _finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return value


def _unit(name: str, value: float) -> None:
    if not 0 <= _finite(name, value) <= 1:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")


def _tiles(name: str, tiles: tuple[str, ...]) -> None:
    if isinstance(tiles, str) or not tiles:
        raise ValueError(f"{name} needs a non-empty tuple of tile URLs")


@dataclass(frozen=True)
class RasterSource:
    tiles: tuple[str, ...]
    tile_size: int = 256
    bounds: tuple[float, float, float, float] | None = None
    max_native_zoom: int | None = None

    def __post_init__(self) -> None:
        _tiles("RasterSource.tiles", self.tiles)

    def to_json(self) -> dict:
        return {
            "tiles": list(self.tiles),
            "tile_size": self.tile_size,
            "max_native_zoom": self.max_native_zoom,
            "bounds": None if self.bounds is None else list(self.bounds),
        }


@dataclass(frozen=True)
class GeoJSONSource:
    digest: str

    def to_json(self) -> dict:
        return {"digest": self.digest}


@dataclass(frozen=True)
class PMTilesSource:
    url: str
    source_layer: str

    def to_json(self) -> dict:
        return {"url": self.url, "source_layer": self.source_layer}


@dataclass(frozen=True)
class VectorPaint:
    stroke: str = "#3388ff"
    fill: str | None = None
    fill_opacity: float = 0.0
    width: float = 2.0
    point_radius: float = 5.0

    def __post_init__(self) -> None:
        _unit("fill_opacity", self.fill_opacity)
        for name in ("width", "point_radius"):
            if _finite(name, getattr(self, name)) < 0:
                raise ValueError(f"{name} must not be negative")

    def to_json(self) -> dict:
        return {
            "stroke": self.stroke,
            "fill": self.fill,
            "fill_opacity": self.fill_opacity,
            "width": self.width,
            "point_radius": self.point_radius,
        }


@dataclass(frozen=True)
class Layer:
    id: str
    source: RasterSource | GeoJSONSource | PMTilesSource
    token: int = 0
    zone: Literal["data", "overlay"] = "data"
    visible: bool = True
    opacity: float = 1.0
    min_zoom: float = 0
    max_zoom: float | None = None
    paint: VectorPaint | None = None
    attribution: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.source, (RasterSource, GeoJSONSource, PMTilesSource)):
            raise ValueError(f"unsupported source {self.source!r}")
        if self.zone not in ZONES:
            raise ValueError(f"zone must be one of {ZONES}, got {self.zone!r}")
        _unit("opacity", self.opacity)
        for name in ("min_zoom", "max_zoom"):
            value = getattr(self, name)
            if value is None and name == "max_zoom":
                continue
            if not 0 <= _finite(name, value) <= 24:
                raise ValueError(f"{name} must be in [0, 24], got {value!r}")
        if self.max_zoom is not None and self.min_zoom >= self.max_zoom:
            raise ValueError("min_zoom must be below max_zoom")
        if self.kind == "raster":
            if self.paint is not None:
                raise ValueError("a raster layer takes no paint")
        elif self.paint is None:
            object.__setattr__(self, "paint", VectorPaint())

    @property
    def kind(self) -> Literal["raster", "geojson", "pmtiles"]:
        if isinstance(self.source, RasterSource):
            return "raster"
        if isinstance(self.source, GeoJSONSource):
            return "geojson"
        return "pmtiles"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "token": self.token,
            "zone": self.zone,
            "visible": self.visible,
            "opacity": self.opacity,
            "min_zoom": self.min_zoom,
            "max_zoom": self.max_zoom,
            "attribution": self.attribution,
            "source": self.source.to_json(),
            "paint": None if self.paint is None else self.paint.to_json(),
        }


@dataclass(frozen=True)
class Basemap:
    tiles: tuple[str, ...]
    attribution: str = ""
    max_zoom: int = 19

    def __post_init__(self) -> None:
        _tiles("Basemap.tiles", self.tiles)

    def to_json(self) -> dict:
        return {
            "tiles": list(self.tiles),
            "attribution": self.attribution,
            "max_zoom": self.max_zoom,
        }


@dataclass(frozen=True)
class Controls:
    zoom: bool = True
    fullscreen: bool = True

    def to_json(self) -> dict:
        return {"zoom": self.zoom, "fullscreen": self.fullscreen}


@dataclass(frozen=True)
class LayerStatus:
    """What the mounted views report for the current instance of a layer.

    ``error`` holds a message only when ``status`` is ``"error"``.
    """

    status: Literal["loading", "ready", "error"]
    error: str | None
    token: int
    instance: int


@dataclass(frozen=True)
class MapState:
    """Layers are top-first: index 0 draws on top."""

    layers: tuple[Layer, ...] = ()
    basemap: Basemap | None = None
    theme: Literal["light", "dark"] = "light"
    controls: Controls = field(default_factory=Controls)

    def __post_init__(self) -> None:
        if self.theme not in THEMES:
            raise ValueError(f"theme must be one of {THEMES}, got {self.theme!r}")
        seen: set[str] = set()
        for layer in self.layers:
            if not isinstance(layer.id, str) or not layer.id:
                raise ValueError("layer ids must be non-empty strings")
            if layer.id in seen:
                raise ValueError(f"duplicate layer id {layer.id!r}")
            seen.add(layer.id)

    def to_json(self) -> dict:
        return {
            "theme": self.theme,
            "controls": self.controls.to_json(),
            "basemap": None if self.basemap is None else self.basemap.to_json(),
            "layers": [layer.to_json() for layer in self.layers],
        }
