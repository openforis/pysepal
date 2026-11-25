"""Frozen declarations of everything a map persistently shows."""

from __future__ import annotations

import math
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

THEMES = ("light", "dark")
ZONES = ("data", "overlay")
SIDES = ("left", "right", "both")
#: Which half of a compare map draws a layer.
Side = Literal["left", "right", "both"]


def _finite(name: str, value: float) -> float:
    """``value`` as a plain float; any finite real number but a bool."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return float(value)


def _int(name: str, value: int) -> int:
    """``value`` as a plain int; any integer but a bool."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{name} must be an int, got {value!r}")
    return int(value)


def _zoom_level(name: str, value: int) -> int:
    level = _int(name, value)
    if not 0 <= level <= 24:
        raise ValueError(f"{name} must be an int in [0, 24], got {value!r}")
    return level


def _unit(name: str, value: float) -> float:
    number = _finite(name, value)
    if not 0 <= number <= 1:
        raise ValueError(f"{name} must be in [0, 1], got {value!r}")
    return number


def _tiles(name: str, tiles: tuple[str, ...]) -> None:
    if isinstance(tiles, str) or not tiles:
        raise ValueError(f"{name} needs a non-empty tuple of tile URLs")
    for tile in tiles:
        if not isinstance(tile, str) or not tile:
            raise ValueError(f"{name} entries must be non-empty strings, got {tile!r}")


def _bounds(name: str, bounds) -> tuple[float, float, float, float]:
    """``(west, south, east, north)`` as floats; west may exceed east."""
    try:
        values = tuple(bounds)
    except TypeError:
        values = ()
    if isinstance(bounds, str) or len(values) != 4:
        raise ValueError(f"{name} must be (west, south, east, north), got {bounds!r}")
    corners = ("west", "south", "east", "north")
    west, south, east, north = (_finite(f"{name} {c}", v) for c, v in zip(corners, values))
    if not -90 <= south <= north <= 90:
        raise ValueError(f"{name} needs -90 <= south <= north <= 90, got {bounds!r}")
    return west, south, east, north


@dataclass(frozen=True)
class RasterSource:
    tiles: tuple[str, ...]
    tile_size: int = 256
    bounds: tuple[float, float, float, float] | None = None
    max_native_zoom: int | None = None

    def __post_init__(self) -> None:
        """Reject bad tiles, tile size, bounds or native zoom; store plain numbers."""
        _tiles("RasterSource.tiles", self.tiles)
        tile_size = _int("RasterSource.tile_size", self.tile_size)
        if tile_size < 1:
            raise ValueError(f"RasterSource.tile_size must be positive, got {self.tile_size!r}")
        object.__setattr__(self, "tile_size", tile_size)
        if self.bounds is not None:
            object.__setattr__(self, "bounds", _bounds("RasterSource.bounds", self.bounds))
        if self.max_native_zoom is not None:
            zoom = _zoom_level("RasterSource.max_native_zoom", self.max_native_zoom)
            object.__setattr__(self, "max_native_zoom", zoom)

    def to_json(self) -> dict:
        """The source as the JSON the front end reads, with bounds as a plain list."""
        return {
            "tiles": list(self.tiles),
            "tile_size": self.tile_size,
            "max_native_zoom": self.max_native_zoom,
            "bounds": None if self.bounds is None else list(self.bounds),
        }


@dataclass(frozen=True)
class Cluster:
    """Group the points of a GeoJSON source into count bubbles below ``max_zoom``.

    ``radius`` is the grouping distance in pixels. MapLibre reads a max zoom of 0
    as its default and wants it below the source's own max zoom (18).
    """

    radius: int = 50
    max_zoom: int = 14

    def __post_init__(self) -> None:
        """Reject a radius below 1 or a max zoom outside [1, 17]; store plain ints."""
        radius = _int("Cluster.radius", self.radius)
        if radius < 1:
            raise ValueError(f"Cluster.radius must be at least 1, got {self.radius!r}")
        max_zoom = _int("Cluster.max_zoom", self.max_zoom)
        if not 1 <= max_zoom <= 17:
            raise ValueError(f"Cluster.max_zoom must be an int in [1, 17], got {self.max_zoom!r}")
        object.__setattr__(self, "radius", radius)
        object.__setattr__(self, "max_zoom", max_zoom)

    def to_json(self) -> dict:
        """The cluster options as JSON."""
        return {"radius": self.radius, "max_zoom": self.max_zoom}


@dataclass(frozen=True)
class GeoJSONSource:
    digest: str
    cluster: Cluster | None = None

    def to_json(self) -> dict:
        """The source as JSON: the digest, since the data travels apart, and the cluster."""
        return {
            "digest": self.digest,
            "cluster": None if self.cluster is None else self.cluster.to_json(),
        }


@dataclass(frozen=True)
class PMTilesSource:
    url: str
    source_layer: str

    def to_json(self) -> dict:
        """The source as JSON: the archive URL and the vector layer to draw."""
        return {"url": self.url, "source_layer": self.source_layer}


#: The largest integer a JavaScript number holds exactly.
_MAX_SAFE_INTEGER = 2**53 - 1


def _class_value(value) -> str | int:
    """A class value: a str, or an int MapLibre can compare exactly; never a bool."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError(f"class values must be str or int, got {value!r}")
    if abs(value) > _MAX_SAFE_INTEGER:
        raise ValueError(f"class value {value!r} is beyond what JavaScript holds exactly")
    return int(value)


def _class_colors(value) -> tuple[tuple[str | int, str], ...]:
    """``(value, color)`` pairs from a mapping or a sequence of pairs, values all of one type."""
    bad = f"class_colors must be a mapping or (value, color) pairs, got {value!r}"
    if isinstance(value, Mapping):
        entries = list(value.items())
    elif isinstance(value, Sequence) and not isinstance(value, str):
        entries = list(value)
    else:
        raise ValueError(bad)
    pairs = []
    for entry in entries:
        if isinstance(entry, str) or not isinstance(entry, Sequence) or len(entry) != 2:
            raise ValueError(bad)
        label, color = entry
        if not isinstance(color, str) or not color:
            raise ValueError(f"class colours must be non-empty strings, got {color!r}")
        pairs.append((_class_value(label), color))
    labels = [label for label, _ in pairs]
    if len({type(label) for label in labels}) > 1:
        raise ValueError("class values must be all str or all int")
    if len(set(labels)) != len(labels):
        raise ValueError(f"class values must be unique, got {labels!r}")
    return tuple(pairs)


@dataclass(frozen=True)
class VectorPaint:
    """How a vector layer is drawn.

    ``color_by`` names a feature property and ``class_colors``, a mapping or a
    sequence of ``(value, color)`` pairs, gives its values their colours; the two
    go together. Fill, line, circle and pin then take the colour of the
    feature's class, and a feature of no class keeps the colour it would have
    without them. Values are unique and all str or all int, and are compared as
    they are, so ``"1"`` is not ``1``.
    """

    stroke: str = "#3388ff"
    fill: str | None = None
    fill_opacity: float = 0.0
    width: float = 2.0
    point_radius: float = 5.0
    marker: Literal["circle", "pin"] = "circle"
    color_by: str | None = None
    class_colors: tuple[tuple[str | int, str], ...] = ()

    def __post_init__(self) -> None:
        """Reject a bad opacity, size, marker or class; store the classes as pairs."""
        if self.marker not in ("circle", "pin"):
            raise ValueError(f"marker must be 'circle' or 'pin', got {self.marker!r}")
        object.__setattr__(self, "fill_opacity", _unit("fill_opacity", self.fill_opacity))
        for name in ("width", "point_radius"):
            value = _finite(name, getattr(self, name))
            if value < 0:
                raise ValueError(f"{name} must not be negative")
            object.__setattr__(self, name, value)
        if self.color_by is not None and (not isinstance(self.color_by, str) or not self.color_by):
            raise ValueError(f"color_by must be a non-empty string, got {self.color_by!r}")
        object.__setattr__(self, "class_colors", _class_colors(self.class_colors))
        if (self.color_by is None) != (not self.class_colors):
            raise ValueError("color_by and class_colors must be given together")

    def to_json(self) -> dict:
        """The paint as the JSON the front end reads."""
        return {
            "stroke": self.stroke,
            "fill": self.fill,
            "fill_opacity": self.fill_opacity,
            "width": self.width,
            "point_radius": self.point_radius,
            "marker": self.marker,
            "color_by": self.color_by,
            "class_colors": [[label, color] for label, color in self.class_colors],
        }


def _fields(name: str, value) -> tuple[tuple[str, str], ...] | None:
    """``value`` as ``(name, label)`` pairs, or None.

    A mapping gives name -> label; a sequence of names labels each with itself.
    """
    if value is None:
        return None
    if isinstance(value, str):
        raise ValueError(f"{name} must be a tuple of property names, got {value!r}")
    if isinstance(value, Mapping):
        pairs = tuple(value.items())
    else:
        try:
            pairs = tuple((field, field) for field in value)
        except TypeError:
            raise ValueError(
                f"{name} must be a tuple of property names or a mapping to labels, got {value!r}"
            ) from None
    for field_name, label in pairs:
        if not isinstance(field_name, str) or not field_name:
            raise ValueError(f"{name} entries must be non-empty strings, got {field_name!r}")
        if not isinstance(label, str) or not label:
            raise ValueError(f"{name} labels must be non-empty strings, got {label!r}")
    return pairs


@dataclass(frozen=True)
class Interaction:
    """What a click or the pointer shows of a feature's properties.

    ``()`` shows every property, a tuple names the ones to show in that order, a mapping
    names them with the label to show for each, ``None`` turns the popup or tooltip off.
    """

    popup: tuple[tuple[str, str], ...] | None = None
    tooltip: tuple[tuple[str, str], ...] | None = None

    def __post_init__(self) -> None:
        """Store each field as ``(name, label)`` pairs; reject an empty name or label."""
        for name in ("popup", "tooltip"):
            object.__setattr__(self, name, _fields(f"Interaction.{name}", getattr(self, name)))

    def to_json(self) -> dict:
        """The interaction as JSON, with each field a list of ``[name, label]`` or null."""
        return {
            "popup": None if self.popup is None else [list(pair) for pair in self.popup],
            "tooltip": None if self.tooltip is None else [list(pair) for pair in self.tooltip],
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
    interaction: Interaction | None = None
    side: Side = "both"

    def __post_init__(self) -> None:
        """Reject an unknown source, zone or side, a non-int token, out-of-range opacity or zooms, and a paint or interaction on a raster layer; give vector layers the default paint."""
        if not isinstance(self.source, (RasterSource, GeoJSONSource, PMTilesSource)):
            raise ValueError(f"unsupported source {self.source!r}")
        object.__setattr__(self, "token", _int("token", self.token))
        if self.zone not in ZONES:
            raise ValueError(f"zone must be one of {ZONES}, got {self.zone!r}")
        if self.side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}, got {self.side!r}")
        object.__setattr__(self, "opacity", _unit("opacity", self.opacity))
        for name in ("min_zoom", "max_zoom"):
            value = getattr(self, name)
            if value is None and name == "max_zoom":
                continue
            zoom = _finite(name, value)
            if not 0 <= zoom <= 24:
                raise ValueError(f"{name} must be in [0, 24], got {value!r}")
            object.__setattr__(self, name, zoom)
        if self.max_zoom is not None and self.min_zoom >= self.max_zoom:
            raise ValueError("min_zoom must be below max_zoom")
        if self.kind == "raster":
            if self.paint is not None:
                raise ValueError("a raster layer takes no paint")
            if self.interaction is not None:
                raise ValueError("a raster layer takes no interaction")
        elif self.paint is None:
            object.__setattr__(self, "paint", VectorPaint())

    @property
    def kind(self) -> Literal["raster", "geojson", "pmtiles"]:
        """Which kind of layer the source makes: "raster", "geojson" or "pmtiles"."""
        if isinstance(self.source, RasterSource):
            return "raster"
        if isinstance(self.source, GeoJSONSource):
            return "geojson"
        return "pmtiles"

    def to_json(self) -> dict:
        """The layer as JSON, with its source and paint nested."""
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
            "interaction": None if self.interaction is None else self.interaction.to_json(),
            "side": self.side,
        }


@dataclass(frozen=True)
class Basemap:
    tiles: tuple[str, ...]
    attribution: str = ""
    max_zoom: int = 19

    def __post_init__(self) -> None:
        """Reject bad tiles or a max zoom outside [0, 24]."""
        _tiles("Basemap.tiles", self.tiles)
        object.__setattr__(self, "max_zoom", _zoom_level("Basemap.max_zoom", self.max_zoom))

    def to_json(self) -> dict:
        """The basemap as the JSON the front end reads."""
        return {
            "tiles": list(self.tiles),
            "attribution": self.attribution,
            "max_zoom": self.max_zoom,
        }


@dataclass(frozen=True)
class Controls:
    """The map controls to show.

    ``scale`` is a metric scale bar; ``coordinates`` a readout of the pointer's
    position at the bottom left; ``globe`` a button that turns the view's map
    into a globe and back. The projection is the view's, like its camera:
    hiding the button takes the view back to the flat map.
    """

    zoom: bool = True
    fullscreen: bool = True
    scale: bool = True
    coordinates: bool = False
    globe: bool = False

    def to_json(self) -> dict:
        """The control switches as JSON."""
        return {
            "zoom": self.zoom,
            "fullscreen": self.fullscreen,
            "scale": self.scale,
            "coordinates": self.coordinates,
            "globe": self.globe,
        }


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
    compare: bool = False

    def __post_init__(self) -> None:
        """Reject an unknown theme, a non-bool compare, and missing or duplicate layer ids."""
        if not isinstance(self.compare, bool):
            raise TypeError(f"compare must be a bool, got {self.compare!r}")
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
        """The whole desired state as the JSON published to the views."""
        return {
            "theme": self.theme,
            "compare": self.compare,
            "controls": self.controls.to_json(),
            "basemap": None if self.basemap is None else self.basemap.to_json(),
            "layers": [layer.to_json() for layer in self.layers],
        }
