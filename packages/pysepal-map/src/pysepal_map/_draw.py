"""The drawing tools of a map, and the rules drawn features follow.

The views draw with Terra Draw 1.39, which validates every feature added to it.
The rules here are the ones it applies (``validations/*.validation.ts`` and
``store/store-feature-validation.ts``), so a feature Python accepts is one a
view can add back.
"""

from __future__ import annotations

import copy
import json
import math
import numbers
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .widget import MapWidget

#: The drawing tools a map can offer, in toolbar order.
DRAW_MODES = ("polygon", "rectangle", "circle", "linestring", "point")
#: The mode that edits what the tools drew, offered after them.
SELECT = "select"
#: No tool: the map pans and clicks as usual.
STATIC = "static"
DEFAULT_COLOR = "#3388ff"
#: The decimals Terra Draw keeps: the coordinatePrecision of its MapLibre adapter.
PRECISION = 9
_SCALE = 10.0**PRECISION
#: Terra Draw's SELECT_PROPERTIES and COMMON_PROPERTIES (common.ts), which it
#: reserves for its own flags. A seed carrying one could be taken for a helper.
RESERVED_PROPERTIES = frozenset(
    {
        "selected",
        "midPoint",
        "selectionPointFeatureId",
        "selectionPoint",
        "mode",
        "currentlyDrawing",
        "edited",
        "closingPoint",
        "snappingPoint",
        "coordinatePoint",
        "coordinatePointFeatureId",
        "coordinatePointIds",
        "provisionalCoordinateCount",
        "committedCoordinateCount",
        # Select mode fetches its default marker image from raw.githubusercontent.com
        # for a point flagged `marker`, which breaks the no-CDN rule.
        "marker",
    }
)
#: The mode Terra Draw adds a geometry under when no drawing mode is known.
GEOMETRY_MODES = {"Polygon": "polygon", "LineString": "linestring", "Point": "point"}
#: The geometry each drawing mode draws.
MODE_GEOMETRIES = {
    "polygon": "Polygon",
    "rectangle": "Polygon",
    "circle": "Polygon",
    "linestring": "LineString",
    "point": "Point",
}
_MULTI = {"MultiPolygon": "Polygon", "MultiLineString": "LineString", "MultiPoint": "Point"}
# Terra Draw's own ids are UUID4 strings; its store accepts any 36-character string.
_UUID4 = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.IGNORECASE
)


def _round(value: float) -> float:
    """``value`` as Terra Draw keeps it: ``Math.round(value * 1e9) / 1e9``.

    Python's ``round`` rounds half to even on the decimal value, which gives
    another result for some inputs.
    """
    scaled = value * _SCALE
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    return whole / _SCALE


def _position(value) -> list[float]:
    """A finite ``[lng, lat]`` on the globe, rounded to Terra Draw's precision."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"a position is [lng, lat], got {value!r}")
    if not all(isinstance(x, numbers.Real) and not isinstance(x, bool) for x in value):
        raise ValueError(f"a position holds two finite numbers, got {value!r}")
    try:
        lng, lat = (float(x) for x in value)
    except OverflowError:
        raise ValueError(f"a position holds two finite numbers, got {value!r}") from None
    if not (math.isfinite(lng) and math.isfinite(lat)):
        raise ValueError(f"a position holds two finite numbers, got {value!r}")
    # Before rounding: scaling a huge value would overflow
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError(f"a position needs a lng in [-180, 180] and a lat in [-90, 90]: {value!r}")
    lng, lat = _round(lng), _round(lat)
    return [lng, lat]


def _positions(value, minimum: int) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < minimum:
        raise ValueError(f"expected at least {minimum} positions, got {value!r}")
    return [_position(p) for p in value]


def _coordinates(kind: str, coordinates):
    """Valid coordinates of a Polygon, LineString or Point, rounded."""
    if kind == "Point":
        return _position(coordinates)
    if kind == "LineString":
        return _positions(coordinates, 2)
    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 1:
        raise ValueError("a polygon has exactly one ring: Terra Draw cannot draw holes")
    ring = _positions(coordinates[0], 4)
    if ring[0] != ring[-1]:
        raise ValueError("a polygon's ring must be closed")
    return [ring]


def _geometries(geometry, split: bool) -> list[dict]:
    """The Polygon, LineString or Point geometries of ``geometry``.

    With ``split``, a Multi* geometry gives one per part.
    """
    if not isinstance(geometry, Mapping):
        raise ValueError(f"a feature needs a geometry, got {geometry!r}")
    kind, coordinates = geometry.get("type"), geometry.get("coordinates")
    if split and kind in _MULTI:
        if not isinstance(coordinates, (list, tuple)):
            raise ValueError(f"{kind} coordinates must be a list")
        part = _MULTI[kind]
        return [{"type": part, "coordinates": _coordinates(part, c)} for c in coordinates]
    if kind not in GEOMETRY_MODES:
        raise ValueError(f"Terra Draw draws Polygon, LineString and Point geometries, not {kind!r}")
    return [{"type": kind, "coordinates": _coordinates(kind, coordinates)}]


def _properties(properties) -> dict:
    """A JSON copy of ``properties`` without the names Terra Draw reserves."""
    if properties is None:
        return {}
    if not isinstance(properties, Mapping):
        raise ValueError(f"feature properties must be a mapping, got {properties!r}")
    kept = {k: v for k, v in properties.items() if k not in RESERVED_PROPERTIES}
    try:
        # What the comm can send: a NaN or an object would fail once synced.
        return json.loads(json.dumps(kept, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"feature properties must be JSON: {error}") from error


def _feature_list(features) -> list:
    """The features of a FeatureCollection, a Feature, or a sequence of Features."""
    if isinstance(features, Mapping):
        if features.get("type") == "FeatureCollection":
            features = features.get("features")
            if not isinstance(features, (list, tuple)):
                raise ValueError("a FeatureCollection needs a list of features")
            return list(features)
        return [features]
    if isinstance(features, Sequence) and not isinstance(features, (str, bytes)):
        return list(features)
    raise ValueError(f"expected a FeatureCollection, a Feature or Features, got {features!r}")


def _normalise(feature, used: set[str], split: bool) -> list[dict]:
    """``feature`` as drawn features, one per part, with ids unique in ``used``.

    The mode is the geometry's, unless ``split`` is off (a view's report) and
    the feature names a drawing mode that draws its geometry.
    """
    if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
        raise ValueError(f"expected a GeoJSON Feature, got {feature!r}")
    geometries = _geometries(feature.get("geometry"), split)
    properties = _properties(feature.get("properties"))
    named = None if split else (feature.get("properties") or {}).get("mode")
    mode = named if isinstance(named, str) else None
    out = []
    fid = feature.get("id")
    for geometry in geometries:
        if not (isinstance(fid, str) and _UUID4.fullmatch(fid)) or fid in used:
            fid = str(uuid.uuid4())
        used.add(fid)
        if MODE_GEOMETRIES.get(mode) != geometry["type"]:
            mode = GEOMETRY_MODES[geometry["type"]]
        out.append(
            {
                "type": "Feature",
                "id": fid,
                "geometry": geometry,
                "properties": {**properties, "mode": mode},
            }
        )
    return out


def normalise_features(features) -> list[dict]:
    """The drawn features of a replacement, all checked; any failure raises ``ValueError``."""
    used: set[str] = set()
    return [part for f in _feature_list(features) for part in _normalise(f, used, split=True)]


def report_features(features: list) -> list[dict]:
    """The features of a view's report that a view could add back; the rest are dropped."""
    used: set[str] = set()
    out: list[dict] = []
    for feature in features:
        try:
            out.extend(_normalise(feature, used, split=False))
        except ValueError:
            continue
    return out


class Draw:
    """The drawing tools of one ``MapWidget``: which are offered, the active one, the features.

    The browser owns the drawn features, like the camera: ``set`` and
    ``clear`` ask every view to replace them, and ``features`` mirrors what
    the views report.
    """

    def __init__(self, widget: MapWidget) -> None:
        self._widget = widget

    @property
    def modes(self) -> tuple[str, ...]:
        """The tools offered, ``"select"`` last when editing is on; ``()`` while drawing is off."""
        return tuple(self._widget.drawing["modes"])

    @property
    def mode(self) -> str:
        """The active tool, or ``"static"``."""
        return self._widget.drawing["mode"]

    @property
    def color(self) -> str:
        """The colour the tools draw in: outlines in it, fills in it at 0.2 opacity."""
        return self._widget.drawing["color"]

    @property
    def features(self) -> dict:
        """The drawn features, as a FeatureCollection the caller may change.

        The features of the newest ``set`` until a view acknowledged it, then
        those of the last report the widget accepted.
        """
        widget = self._widget
        with widget._lock:
            request, drawn = widget.draw_request, widget.drawn
            current = drawn if drawn["request_seq"] >= request["seq"] else request
            features = copy.deepcopy(current["features"])
        return {"type": "FeatureCollection", "features": features}

    def enable(
        self, modes: Sequence[str] = ("polygon", "rectangle", "circle"), *, edit: bool = True
    ) -> None:
        """Offer the tools ``modes``, in that order, and ``"select"`` with ``edit``.

        ``modes`` takes names from ``DRAW_MODES``, each once. No tool is active
        afterwards.
        """
        if isinstance(modes, str) or not isinstance(modes, Sequence):
            raise ValueError(f"modes must be a sequence of names, got {modes!r}")
        names = list(modes)
        if not names or len(set(names)) != len(names) or any(m not in DRAW_MODES for m in names):
            raise ValueError(f"modes must name tools of {DRAW_MODES} once each, got {modes!r}")
        self._write(modes=names + ([SELECT] if edit else []), mode=STATIC)

    def disable(self) -> None:
        """Hide the tools and the features; the features are kept for the next ``enable``."""
        self._write(modes=[], mode=STATIC)

    def start(self, mode: str) -> None:
        """Make ``mode``, one of ``modes``, the active tool."""
        if mode not in self.modes:
            raise ValueError(f"{mode!r} is not among the tools offered: {self.modes}")
        self._write(mode=mode)

    def stop(self) -> None:
        """Leave the active tool: the map pans and clicks as usual."""
        self._write(mode=STATIC)

    def set_color(self, color: str) -> None:
        """Draw in ``color``, a MapLibre colour string, from now on."""
        if not isinstance(color, str) or not color:
            raise ValueError(f"color must be a non-empty string, got {color!r}")
        self._write(color=color)

    def set(self, features) -> None:
        """Ask every view to show exactly ``features``.

        ``features`` is a FeatureCollection, a Feature or a sequence of
        Features of Polygon, LineString or Point geometries; a Multi* geometry
        becomes one feature per part. Coordinates are rounded to Terra Draw's
        9 decimals, and must be finite, with a lng in [-180, 180] and a lat in
        [-90, 90]. A polygon has one closed ring of 4 positions or more, since
        Terra Draw draws no holes, and a line 2 positions or more. Each feature
        gets ``properties.mode`` from its geometry (``polygon``, ``linestring``
        or ``point``), loses the properties Terra Draw reserves
        (``RESERVED_PROPERTIES``), and keeps its id if it is a UUID4 string
        not already used here, else gets a new one. Any failure raises
        ``ValueError`` and changes nothing.
        """
        normalised = normalise_features(features)
        widget = self._widget
        with widget._lock:
            seq = widget.draw_request["seq"] + 1
            widget.set_trait("draw_request", {"seq": seq, "features": normalised})

    def clear(self) -> None:
        """Ask every view to remove every drawn feature."""
        self.set([])

    def _write(self, **changes: Any) -> None:
        widget = self._widget
        with widget._lock:
            widget.set_trait("drawing", {**widget.drawing, **changes})
