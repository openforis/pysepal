"""The drawing tools of a map, the sessions that hold them, and the shapes drawn features take.

The views draw with Terra Draw 1.39, which validates every feature added to it.
Python checks the shapes it validates (``validations/*.validation.ts``), so a
feature Python accepts is one a view can add. Each view prepares the features
before it adds them: it rounds them to Terra Draw's precision, drops the
property names Terra Draw reserves and gives them ids, the same in every view.
"""

from __future__ import annotations

import copy
import json
import math
import numbers
from collections.abc import Callable, Mapping, Sequence
from types import MappingProxyType
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
#: The toolbar's English labels: one per drawing tool, ``select`` and ``clear``.
DRAW_LABELS = MappingProxyType(
    {
        "polygon": "Draw a polygon",
        "rectangle": "Draw a rectangle",
        "circle": "Draw a circle",
        "linestring": "Draw a line",
        "point": "Draw a point",
        "select": "Select and edit shapes",
        "clear": "Remove all shapes",
    }
)
#: The geometries Terra Draw draws, and the part each Multi* geometry splits into.
_KINDS = ("Polygon", "LineString", "Point")
_MULTI = {"MultiPolygon": "Polygon", "MultiLineString": "LineString", "MultiPoint": "Point"}

DrawCallback = Callable[[dict], object]


def _empty() -> dict:
    return {"type": "FeatureCollection", "features": []}


def _position(value) -> list[float]:
    """A finite ``[lng, lat]`` on the globe."""
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
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
        raise ValueError(f"a position needs a lng in [-180, 180] and a lat in [-90, 90]: {value!r}")
    return [lng, lat]


def _positions(value, minimum: int) -> list[list[float]]:
    if not isinstance(value, (list, tuple)) or len(value) < minimum:
        raise ValueError(f"expected at least {minimum} positions, got {value!r}")
    return [_position(p) for p in value]


def _coordinates(kind: str, coordinates):
    """The checked coordinates of a Polygon, LineString or Point."""
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
    if kind not in _KINDS:
        raise ValueError(f"Terra Draw draws Polygon, LineString and Point geometries, not {kind!r}")
    return [{"type": kind, "coordinates": _coordinates(kind, coordinates)}]


def _json(value, what: str):
    """A copy of ``value`` the comm can send: a NaN or an object would fail once synced."""
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{what} must be JSON: {error}") from error


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


def _check(feature, split: bool) -> list[dict]:
    """``feature`` as drawn features, one per part, with its id and properties."""
    if not isinstance(feature, Mapping) or feature.get("type") != "Feature":
        raise ValueError(f"expected a GeoJSON Feature, got {feature!r}")
    geometries = _geometries(feature.get("geometry"), split)
    properties = feature.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        raise ValueError(f"feature properties must be a mapping, got {properties!r}")
    properties = _json(dict(properties or {}), "feature properties")
    head: dict[str, Any] = {"type": "Feature"}
    if "id" in feature:
        head["id"] = _json(feature["id"], "a feature id")
    return [
        {**head, "geometry": geometry, "properties": copy.deepcopy(properties)}
        for geometry in geometries
    ]


def check_features(features) -> list[dict]:
    """The drawn features of ``features``, each Multi* geometry split into one per part.

    ``features`` is a FeatureCollection, a Feature or a sequence of Features
    of Polygon, LineString or Point geometries, or Multi* ones. Ids,
    properties and coordinates are kept as given. A position is a finite
    ``[lng, lat]`` with a lng in [-180, 180] and a lat in [-90, 90]; a line has
    2 positions or more, and a polygon one closed ring of 4 or more, since
    Terra Draw draws no holes. Properties must be JSON. Any failure raises
    ``ValueError``.
    """
    return [part for f in _feature_list(features) for part in _check(f, split=True)]


def report_features(features: list) -> list[dict]:
    """The features of a view's report that ``check_features`` accepts; the rest are dropped.

    A view reports no Multi* geometry, so one is dropped too.
    """
    out: list[dict] = []
    for feature in features:
        try:
            out.extend(_check(feature, split=False))
        except ValueError:
            continue
    return out


def _check_modes(modes, edit: bool) -> list[str]:
    if isinstance(modes, str) or not isinstance(modes, Sequence):
        raise ValueError(f"modes must be a sequence of names, got {modes!r}")
    names = list(modes)
    if not names or len(set(names)) != len(names) or any(m not in DRAW_MODES for m in names):
        raise ValueError(f"modes must name tools of {DRAW_MODES} once each, got {modes!r}")
    return names + ([SELECT] if edit else [])


class DrawSession:
    """One owner's hold on a map's drawing tools, from ``Draw.begin`` until it ends.

    A session ends when its ``end`` runs or another ``Draw.begin`` does. An
    ended session stays ended: ``features`` is empty, ``set``, ``clear``,
    ``start`` and ``stop`` raise ``RuntimeError`` and ``end`` does nothing.
    """

    def __init__(self, draw: Draw, on_change: DrawCallback | None) -> None:
        self._draw = draw
        self._on_change = on_change
        self._active = True

    @property
    def active(self) -> bool:
        """Whether the session still holds the tools."""
        with self._draw._widget._lock:
            return self._active

    @property
    def features(self) -> dict:
        """The drawn features, as a FeatureCollection the caller may change.

        The features of the newest request until a view acknowledged it, then
        those of the last report the widget accepted; empty once the session
        ended.
        """
        widget = self._draw._widget
        with widget._lock:
            if not self._active:
                return _empty()
            request, drawn = widget.draw_request, widget.drawn
            current = drawn if drawn["request_seq"] >= request["seq"] else request
            return {"type": "FeatureCollection", "features": copy.deepcopy(current["features"])}

    def set(self, features) -> None:
        """Ask every view to show exactly ``features``, as ``check_features`` takes them.

        A polygon with holes, or any other failure, raises ``ValueError`` and
        changes nothing. Each view prepares the features before it shows them:
        it rounds the coordinates to 9 decimals, drops the property names Terra
        Draw reserves but ``mode``, replaces a ``mode`` that does not draw the
        geometry with the geometry's own, and replaces an id that is not a
        UUID4 string, or repeats one, with an id every view derives alike.
        ``features`` holds what the views report once one acknowledged them.
        """
        self._require()
        checked = check_features(features)
        widget = self._draw._widget
        with widget._lock:
            self._require()
            widget.set_trait(
                "draw_request", {"seq": widget.draw_request["seq"] + 1, "features": checked}
            )

    def clear(self) -> None:
        """Ask every view to remove every drawn feature."""
        self.set([])

    def start(self, mode: str) -> None:
        """Ask for ``mode``, one of ``Draw.modes``, as the active tool.

        The browser holds the active tool, which the toolbar sets. Every view
        that runs the session applies the request; of the views shown later,
        only the first to start does. A mode the session does not offer,
        ``"static"`` included, raises ``ValueError``.
        """
        with self._draw._widget._lock:
            self._require()
            if mode not in self._draw.modes:
                raise ValueError(f"{mode!r} is not among the tools offered: {self._draw.modes}")
            self._request_tool(mode)

    def stop(self) -> None:
        """Ask for no active tool, as ``start`` asks for one: the map pans and clicks as usual."""
        with self._draw._widget._lock:
            self._require()
            self._request_tool(STATIC)

    def end(self) -> None:
        """Clear the drawing and hide the tools in every view; nothing once ended."""
        with self._draw._widget._lock:
            if self._active:
                self._draw._hand_over(None, modes=[], features=[])

    def _require(self) -> None:
        if not self.active:
            raise RuntimeError("this drawing session has ended")

    def _request_tool(self, mode: str) -> None:
        widget = self._draw._widget
        seq, session = widget.draw_tool["seq"] + 1, widget.drawing["session"]
        widget.set_trait("draw_tool", {"seq": seq, "session": session, "mode": mode})


class Draw:
    """The drawing tools of one ``MapWidget``, and the session that holds them.

    The browser owns the drawn features, like the camera. ``begin`` offers the
    tools to one session at a time, which asks every view for features and
    mirrors what they report.
    """

    def __init__(self, widget: MapWidget) -> None:
        self._widget = widget
        self._session: DrawSession | None = None

    @property
    def modes(self) -> tuple[str, ...]:
        """The tools offered, ``"select"`` last when editing is on; ``()`` with no session."""
        return tuple(self._widget.drawing["modes"])

    @property
    def color(self) -> str:
        """The colour the tools draw in: outlines in it, fills in it at 0.2 opacity."""
        return self._widget.drawing["color"]

    @property
    def features(self) -> dict:
        """The active session's ``features``; an empty FeatureCollection with no session."""
        with self._widget._lock:
            session = self._session
        return _empty() if session is None else session.features

    def begin(
        self,
        modes: Sequence[str] = ("polygon", "rectangle", "circle"),
        *,
        edit: bool = True,
        features=None,
        on_change: DrawCallback | None = None,
    ) -> DrawSession:
        """End the active session and begin one that offers the tools ``modes``.

        ``modes`` names tools of ``DRAW_MODES`` once each, in toolbar order, and
        ``edit`` offers ``"select"`` after them. No tool is active. Every view
        shows ``features``, as ``DrawSession.set`` takes them, else nothing.
        ``on_change(collection)`` runs on the session loop with a
        FeatureCollection on each drawing or edit a user makes in this
        session, never for a view acknowledging a request. Bad modes or
        features raise ``ValueError`` and change nothing, so the active
        session goes on.
        """
        names = _check_modes(modes, edit)
        seeds = [] if features is None else check_features(features)
        session = DrawSession(self, on_change)
        self._hand_over(session, modes=names, features=seeds)
        return session

    def set_color(self, color: str) -> None:
        """Draw in ``color``, a MapLibre colour string, from now on."""
        if not isinstance(color, str) or not color:
            raise ValueError(f"color must be a non-empty string, got {color!r}")
        self._write(color=color)

    def set_labels(self, labels: Mapping[str, str]) -> None:
        """Label the toolbar's buttons that ``labels`` names; the others keep theirs.

        Keys are the keys of ``DRAW_LABELS``: the tools of ``DRAW_MODES``,
        ``select`` and ``clear``. A label is a non-empty string. Any other key
        or label raises ``ValueError`` and changes nothing.
        """
        if not isinstance(labels, Mapping):
            raise ValueError(f"labels must be a mapping, got {labels!r}")
        for key, label in labels.items():
            if key not in DRAW_LABELS:
                raise ValueError(f"{key!r} labels no button; the keys are {tuple(DRAW_LABELS)}")
            if not isinstance(label, str) or not label:
                raise ValueError(f"the {key!r} label must be a non-empty string, got {label!r}")
        with self._widget._lock:
            self._write(labels={**self._widget.drawing["labels"], **labels})

    def _hand_over(self, session: DrawSession | None, *, modes: list, features: list) -> None:
        """Give the tools to ``session``, or to nobody, in one message."""
        widget = self._widget
        with widget._lock, widget.hold_sync():
            # Before the traits: their observers must see who holds the tools.
            if self._session is not None:
                self._session._active = False
            self._session = session
            drawing = widget.drawing
            number = drawing["session"] + (0 if session is None else 1)
            seq = widget.draw_request["seq"] + 1
            widget.set_trait("draw_request", {"seq": seq, "features": features})
            widget.set_trait("drawing", {**drawing, "session": number, "modes": modes})

    def _change_callback(self) -> DrawCallback | None:
        """The active session's ``on_change``; call with the widget lock held."""
        return None if self._session is None else self._session._on_change

    def _write(self, **changes: Any) -> None:
        widget = self._widget
        with widget._lock:
            widget.set_trait("drawing", {**widget.drawing, **changes})
