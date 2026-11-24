"""The MapLibre map widget, and the rules between it and its views.

``state.py`` declares and validates the state. This module publishes it and
keeps the rest of the contract, summed up here for whoever drives a widget or
writes a front end for it.

Traits. ``state``, ``view``, ``view_request``, ``insets``, ``marker``, ``drawing``,
``draw_request``, ``drawn`` and ``draw_tool`` are read-only: assigning one raises
``traitlets.TraitError``, and only the widget writes them. The comm opens with
the first request, sequence 1, in ``view_request``.

Publishing. ``MapWidget.publish`` sets a whole ``MapState`` in the ``state``
trait, with a ``revision`` one above the last. Each layer gets an
``instance``, an integer that grows over the widget's life, given in input
order from 1. A layer gets a new one when it first appears, when it comes back
after a publish without it, and when its source, source attribution or token
changes; visibility, opacity, paint, zooms, zone and order keep it. A publish that
raises publishes nothing and changes no counter.

Style ids. A view owns every source and layer whose id starts with ``psm:``. A
layer's source is ``psm:<id>:<instance>``, with the id escaped as
``encodeURIComponent`` does, and its layers add a part: ``:fill``, ``:line``
and ``:circle`` (or ``:pin``, for ``VectorPaint(marker="pin")``, and ``:cluster`` and ``:count``
on a clustered source), or ``:raster``. The basemap's source and layer are
``psm:basemap``. A GeoJSON source generates feature ids, unique within it.
A new instance is a new source, so nothing reported about the
old one counts for it. Owned layers stay below every other layer, and the view
never changes those.

Messages. Each mounted view has a unique ``view_id`` and a side
(``main``, or ``right`` for the second map of a compare view; any other
side is ignored). It sends JSON messages
with a ``type``: ``view_open`` on mount and every 20 s, ``view_close``,
``pull`` with the GeoJSON digests it lacks, ``status`` on one layer instance,
``click``, ``view_report`` with its camera and ``draw_report`` with its drawn
features. A ``status`` on a rejected style operation also carries its
``style_revision``, which counts only for the current publish. A layer whose
tiles fail is in ``error`` only when every tile of a load failed, until a tile
loads again; failed tiles beside loaded ones do not count.
Python answers each pulled digest with a ``data`` message that carries the
UTF-8 GeoJSON as one buffer, or ``missing: true`` once a publish dropped it, and
sends ``status_request`` to ask one view and side to send its statuses again.
Python's messages reach every view, so each ignores what it did not ask for.
Any message renews its view; one silent for ``VIEW_EXPIRY_S`` and then
``VIEW_GRACE_S`` is dropped with its reports.

Camera. The browser owns it. ``set_center`` and ``fit_bounds`` write
``view_request`` with a ``seq`` that only grows. A new view first restores the
camera saved in ``view``, then applies each request newer than the last one it
applied, and every report names that request and its ``cause``: ``user``,
``request``, ``resize``, or ``link`` for a linked map's move that no user made
(see Linked maps). ``view`` mirrors the last accepted report, with its
``cause``, and so does the dict each ``on_view`` callback gets. Reports from
views not mounted, on an older request, or with a latitude outside [-90, 90]
or a zoom outside [0, 24] are dropped, and on the same request a ``user`` or
``link`` camera is kept over an acknowledgement or another view's resize.

A center request carries ``center`` and ``zoom``, null to keep the zoom. A fit
carries ``bounds``, ``padding``, ``max_zoom`` (null for the map's maximum) and
the view fits the bounds inside ``padding`` px, no further in than
``max_zoom``, and jumps there. A padding the usable area cannot hold is
reduced so that 1 px is left each way. A request with ``animate: true``
flies there instead (MapLibre's ``flyTo``), and the view reports it when the
flight ends; a user who moves the map meanwhile ends it, and a newer request
replaces it. A view jumps to the request it finds on mount, to a fit that
waited for a usable area, and, as MapLibre does, for a user whose system asks
for reduced motion. A fit waits while the view's usable
area has no size, and runs once it has one.

Linked maps. Maps whose ``link_group`` names the same group keep one camera.
A map in a group has ``_link`` set to ``{"group", "seq", "member"}``, else
``{}``: the group is the token ``<scope>:<name>``, where the scope is the id
of the kernel that built the map (each virtual kernel's under ``solara
run``), else the process's, ``seq`` is the request the link was written on,
and ``member`` is an id the map keeps for life, by which its views tell each
other from other maps' views. Linking is per page and per kernel: the views
of one page that share a token follow each other, and a kernel's maps never
move another kernel's. In the browser
every move that changes one view's camera jumps the others to its center and
zoom in the same call, and each paints it on its next frame. Each view still
reports its own camera, a follower once per movement of the view that moved,
as that view does: as ``user`` when a user moved it, else as ``link``, which
counts like a user's. A move that keeps a view's camera, such as a resize,
or keeps its map in place as its insets change, moves no other view. Views of one widget never move each other. The first map
shown sets the camera: a view that joins takes the camera of the group's maps
already shown, unless a request newer than its link ``seq`` moved it on mount,
which then moves them. A request not newer than the link, such as a fit that
waited for a size, moves no other view: while another member is shown, the
view takes that member's camera instead.
Python keeps the group's camera, the last one a member reported that was not
a ``resize``, and moves only the members with no ``main`` view mounted: each
new camera becomes a request on them, sent with their ``_link`` in one
message, its ``seq`` the request's. A ``request`` report moves no such member
that holds a ``set_center`` or ``fit_bounds`` newer than its link ``seq`` and
made after the request reported, so that request moves the group once the
member is shown. A map's first request, and those that follow its group,
count as made before every ``set_center`` and ``fit_bounds``, and so does
one that a later ``set_center`` or ``fit_bounds`` of the same map replaced
before a view reported it. A map that joins a group with a camera, built
with ``link_group`` or set to it, requests that camera instead of its own
``center``, mounted or not; one that joins with an accepted ``view`` while
the group has none gives the group that view's camera. A group forgets its
camera with its last member, so a re-run notebook cell or a Solara hot
reload, which keeps the kernel, builds its new maps into the old group,
still open, and they ignore their ``center`` until the old maps are closed.
Under Solara, the component that builds a map closes it in an effect
cleanup, which also runs on a hot reload.

Compare. ``MapState.compare`` turns on a swipe compare: each ``Layer.side``
(``left``, ``right`` or ``both``) says which half draws it. The ``main`` view
draws the ``left`` and ``both`` layers and the ``right`` view the ``right`` and
``both`` ones. Outside compare every layer is drawn by ``main`` alone, whatever
its side, and the ``right`` view's reports count for nothing. A layer's status
reduces over the views that draw it, and a publish drops the reports of a view
whose side stops drawing a layer, since the browser sends nothing then. A
change of side keeps the layer's instance. A compare view keeps its own map
as ``main`` and adds the ``right`` map, under the same ``view_id``, while the
state compares: it opens with ``view_open`` and closes with ``view_close``
like a view, follows the main map's camera and sends no camera, click or
draw report. Each map takes a payload the other holds instead of pulling it.
The right map shows right of a divider the user moves inside the insets; the
browser keeps the divider's position and never sends it. The pointer reads the map shown under
it: right of the divider, a click's ``features`` (sent by ``main``), the
content of the popup and the tooltip, the ``pointer`` cursor and a cluster's
zoom come from the ``right`` map, while the popup and tooltip themselves, the
marker and the camera stay on the main map. A click's ``hidden_features`` come
from the other map, the one the shown half covers there.
Drawing takes input in both halves, and the ``right`` map draws a copy of
what Terra Draw renders, handles included, in source ``psm-draw-mirror``
and layers ``psm-draw-mirror-fill``, ``-line`` and ``-point``, above its
owned layers.

Clicks. A ``click`` carries the view's ``lnglat`` (longitude wrapped into
[-180, 180]), its ``zoom``, ``settled``, ``features`` and ``hidden_features``.
``settled`` is true when the view has marked the latest state's revision on its root (see the end
of this docstring), or when everything but the layers in error (a rejected style
operation, a payload that failed to decode) is on the map: such a layer does not
hold ``settled`` back, though the mark itself waits for it. Each feature is ``{"id", "instance", "properties"}``: the
layer id and instance come from the feature's own source id, so a hit on a
replaced instance names the old one. The view sends at most 5 features per
layer and 20 in all, but always the first of each layer, top first, and none
while drawing is interactive. ``hidden_features`` holds, in the same form and
under the same caps, the hits of the map the shown one covers at the click in
compare, and is empty outside it. Python accepts a click only from a mounted
view, with finite ``lnglat`` (latitude in [-90, 90]), ``zoom``, a boolean
``settled`` and lists of hits (a missing ``hidden_features`` is empty). It
drops hits, in both lists, that are not objects or whose ``(id, instance)`` is
not the current published one, names the layers of the latter in
``ClickEvent.stale``, and queues the ``ClickEvent`` to every ``on_click``
callback under the lock, like ``on_view``.

Cursor and marker. ``cursor`` (``""``, ``"crosshair"``, ``"pointer"`` or
``"wait"``) is a writable trait: ``""`` leaves MapLibre's own cursor. A view
shows ``pointer`` instead over a feature of a layer with a popup, a tooltip
or clusters, and leaves the cursor to the drawing tools while they are
interactive. ``marker`` is read-only: ``{}`` or ``{"lnglat": [lng, lat],
"color": str}``, set with ``set_marker`` and ``clear_marker``; each view shows
one marker for it. ``Controls.coordinates`` shows the pointer's ``lat, lng``
at the bottom left.

Pins and clusters. ``VectorPaint.marker`` is ``"circle"`` (default) or ``"pin"``: a
pin replaces a point's circle by a symbol anchored at its tip, tinted with the
fill (else the stroke) colour and sized by ``point_radius``. A ``GeoJSONSource`` may
carry a ``Cluster(radius, max_zoom)``, part of the source, so changing it gives a
new instance. A clustered source must hold only points: MapLibre's cluster index
drops lines and polygons, and a property ``cluster`` that is true is reserved
on it. The view draws count bubbles in the stroke colour, with the count as
white text (local glyphs, nothing is fetched); a click on one zooms into it and
sends no click or popup, and clusters are never hits or tooltips. The click
is a bubble's when the top feature of the popup, tooltip and cluster layers
there is one (the layers that show the ``pointer`` cursor), whatever other
layer draws above it. A bubble also hides the popups and tooltips of the features it covers. The
view draws pins on a canvas and registers them as images with ids
``psm-pin:<color>`` (the colour escaped as ``encodeURIComponent`` does). The marker option does nothing on raster layers.

Colours by class. ``VectorPaint(color_by=name, class_colors=...)`` colours one
layer's features by the value of their property ``name``: ``class_colors`` is a
mapping or a sequence of ``(value, colour)`` pairs, given together with
``color_by``. Values are unique and all strings or all integers (no bools, at
most 2**53 - 1 in absolute value). The view turns the fill, line and circle colours and
the pin image into MapLibre ``match`` expressions on ``["get", name]``. A
feature whose value is in no class, is of the other type (``"1"`` is not
``1``), is null or is missing keeps the colour the paint gives without classes:
the fill (else the stroke) for polygons, circles and pins, the stroke for
lines. Circle outlines and cluster bubbles keep the stroke. Like any paint
change, changing the classes keeps the instance.

Popups and tooltips. A vector layer may carry an ``Interaction``, which is part
of the state but not of its instance identity, so changing it keeps the
instance. ``popup`` and ``tooltip`` are each ``None`` (off), ``()`` (every
property, in the feature's order), a tuple naming the properties to show, in
that order, or a mapping from each name to the non-empty label shown for it
(a plain name is its own label); names are non-empty strings, and a raster
layer takes no interaction. A click opens one popup per view, at the click, for the top
feature among layers with a popup: a two-column table with a row per named
property the feature has, headed by its label, and nothing when there is no row. A new popup
replaces the old one. The pointer shows one tooltip, updated once per
animation frame, for the top feature among layers with a tooltip: a single
named property shows only its value, otherwise one ``label: value`` line each. It
hides when nothing is hit and when the pointer leaves the map. Values are
strings as they are, numbers with ``str``, ``null`` as empty and objects or
arrays as JSON, each cut at 200 characters, and are inserted as text, never
HTML. Both are off while drawing is interactive, and close when it becomes
so. Each remembers the source id of its feature and closes when that source is
no longer declared, its layer is hidden, or the layer no longer declares it.
The click message is sent whether or not a popup opens.

Drawing. ``drawing`` declares the tools: ``session``, ``modes`` (empty while
no session is active, else drawing modes with ``select`` last when editing is
on), ``color`` and ``labels``, the toolbar's label of each drawing mode, of
``select`` and of ``clear``, which ``draw.set_labels`` sets. Python holds the
tools through sessions, one at a time: ``draw.begin`` ends the active session
and begins the next, numbered in ``session`` from 1 (0 before the first), and
``DrawSession.end`` clears the drawing and hides the tools. The browser owns
the drawn features, like the camera. ``begin``, ``end`` and a session's
``set`` and ``clear`` write ``draw_request``, ``{"seq", "features"}``, whose
``seq`` only grows from 0; ``begin`` and ``end`` write it with ``drawing`` in
one message, ``end`` with no features, so the reports of an ended session are
dropped. ``drawn``, ``{"request_seq", "features"}``, mirrors the last accepted
report. Python checks the shapes it requests: one closed ring of 4 positions
or more per polygon, lines of 2 or more, finite positions on the globe and
JSON properties. It splits Multi* geometries and keeps ids, properties and
coordinates as given.

The browser holds the active tool too. While ``modes`` is not empty, each view
shows the draw toolbar in its top-left corner, after the controls already
there: one ``maplibregl-ctrl-group`` with a ``button.psm-draw-tool`` per mode,
``data-mode`` naming it and ``aria-pressed`` true on the active one, then a
``button.psm-draw-clear``. A click on a tool makes it the view's active tool, a
click on the active one leaves it for ``static``, and the clear button removes
every drawn feature and sends a ``user`` report, even of a drawing that was
already empty. Drawing is interactive while a view's active tool is not
``static``. ``DrawSession.start`` and ``stop`` write ``draw_tool``,
``{"seq", "session", "mode"}``, whose ``seq`` only grows from 0. A view
holds its tool apart from Terra Draw's mode, and a new session starts with
none. A restart in one session, after a style replacement, enters the view's
tool again and reads no ``draw_tool``. Only a view's first start in a session
reads it: it applies the request when it names that session and no view of
the page applied it yet, so a ``start`` made before any view shows reaches the
first one, and a view shown later, or shown again, starts with no tool. A view
running the session applies each request for it newer than the last it
applied, so every running view follows one ``start``.

Each view runs its own Terra Draw 1.39 while ``modes`` is not empty, with every
drawing mode registered, and prepares each feature before it adds it: it
rounds the coordinates to 9 decimals, drops Terra Draw's reserved property
names but ``mode``, replaces a ``mode`` that does not draw the geometry with
the geometry's own, and replaces an id that is not a UUID4 string, or repeats
one of the batch, with ``SSSSSSSS-0000-4000-8000-IIIIIIIIIIII``: the batch's
seq in 8 hex digits and the feature's index in 12. The seq is the request's,
or ``drawn.request_seq`` on a restore, so every view gives the same ids. On its
first start a view restores ``drawn`` when ``drawn.request_seq >=
draw_request.seq``, else applies the request. A new ``session`` stops its
Terra Draw, drops its features and starts it empty, then applies the request
if it is newer than the last one the view applied, which ``begin`` always
makes it. ``modes`` going empty stops it and drops its features. A restart in
one session, after a style replacement, restores the view's own features
unless a newer request came. A view applies a request only while it runs the
session ``drawing`` names, with tools. Applying a request replaces its
features and sends a ``draw_report`` with cause ``request``; a user's finished
drawing or edit, or deletion, sends one with cause ``user``, on the request it
last applied. A report carries ``request_seq``, ``cause`` and ``features``:
committed Polygon, LineString and Point features only (no helper or
in-progress geometry, no reserved names but ``mode``), each moved by whole
turns so its first vertex lies in [-180, 180] and rounded to 9 decimals; one
that still crosses the antimeridian is left out. Python accepts a report only
from a mounted view on the current request; once a user report was accepted
on it, an acknowledgement from any view is dropped. A feature whose shape
Python would not request is dropped from a report, and a user report runs the
active session's ``on_change``. Terra Draw's sources and layers have ids
starting with ``psm-draw-`` and stay above every owned layer.

Insets. ``insets`` holds the CSS pixels other UI covers on each side of the
map element, as ``left``, ``right``, ``top`` and ``bottom``, all 0 at first. A
view applies them as the map's padding before it restores the camera, and
moves its control corners in by as much. Its usable area is what they leave:
the reported center is its middle, the reported ``bounds`` its corners, and a
fit stays inside it. When they change, the map keeps its place on screen and
the view reports the new middle as a ``resize``. While its map is fullscreen,
a view uses no insets, and the center keeps its place in the area as it enters
or leaves fullscreen.

A view marks its root element with ``data-psm-revision`` once its owned style
matches that revision and every GeoJSON source has loaded its data, on both
maps when the state at that revision compares. Its
fullscreen control fills the closest ancestor marked
``data-psm-fullscreen-root``, else the root element, and marks that element
with ``data-psm-fullscreen`` while it is fullscreen.

The same element, the fullscreen root, holds the height in CSS pixels of each
control corner, which the view measures each time a corner changes size. They
are set inline as ``--psm-controls-top-left``, ``--psm-controls-top-right``,
``--psm-controls-bottom-left`` and ``--psm-controls-bottom-right``, with
``data-psm-controls`` set to the view's id, so a host's overlays can clear
the controls. A view removes them when it goes, unless a newer view has
measured there since. While compare is on, the same element also holds
``--psm-divider-x``, the divider's x in CSS pixels from its left edge, which
follows every move of the divider and is removed under the same rule. A host
must not bind the fullscreen root's ``style``: rewriting it drops them.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import itertools
import logging
import math
import os
import threading
import time
import uuid
import weakref
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import anywidget
import traitlets

from ._callbacks import CallbackQueue, running_loop
from ._camera import INSET_SIDES, MAX_ZOOM, _bounds_request, _center_request, _insets
from ._draw import DEFAULT_COLOR, DRAW_LABELS, STATIC, Draw, report_features
from ._events import ClickEvent, FeatureHit
from .state import GeoJSONSource, LayerStatus, MapState, _finite

_STATIC = Path(__file__).parent / "static"

logger = logging.getLogger("pysepal_map")


def _close_part(part: str, close: Callable[[], None]) -> None:
    """Run one step of a close, and log its failure instead of raising it.

    Solara closes a kernel's widgets in one loop with no guard
    (``Widget.close_all``): a raise would stop it and leak the kernel.
    """
    try:
        close()
    except Exception:
        logger.exception("pysepal-map: closing the map's %s failed", part)


def _asset(name: str) -> str | Path:
    """A bundled asset for anywidget: its text, or its path while hot reload is on.

    anywidget turns a path into a class-level ``FileContents`` and connects every
    instance to its change signal with a strong reference, so no widget would ever
    be collected. ``ANYWIDGET_HMR=1`` is anywidget's own switch for watching files.
    """
    path = _STATIC / name
    if os.getenv("ANYWIDGET_HMR") == "1":
        return path
    return path.read_text(encoding="utf-8")


#: The maps a view mounts: ``main``, and the ``right`` one beside it in compare.
SIDES = ("main", "right")
STATUSES = ("loading", "ready", "error")
#: What moved a view's camera: a user, a request, anything else, or a linked map's
#: move that no user made.
CAUSES = ("user", "request", "resize", "link")
#: The causes that take the camera: an acknowledgement or a resize does not replace them.
_TAKING = ("user", "link")
#: What changed a view's drawing: a user, or applying a request.
DRAW_CAUSES = ("user", "request")
#: A mounted view repeats ``view_open`` every 20 s, and any message from it
#: renews it; one silent this long is late. Chrome runs the timers of a
#: hidden tab as rarely as once a minute.
VIEW_EXPIRY_S = 150.0
#: How long a late view has left. A cell that holds the loop past every
#: deadline makes them all late at once; the messages queued behind it then
#: renew them within this grace.
VIEW_GRACE_S = 10.0

StatusCallback = Callable[[Mapping[str, LayerStatus]], object]
ViewCallback = Callable[[dict], Any]
ClickCallback = Callable[[ClickEvent], object]
CURSORS = ("", "crosshair", "pointer", "wait")
View = tuple[str, str]


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _numbers(value, count: int) -> list[float] | None:
    """``value`` as a list of ``count`` finite numbers, or None."""
    if not isinstance(value, (list, tuple)) or len(value) != count:
        return None
    if not all(
        isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value
    ):
        return None
    return [float(x) for x in value]


def _sides_drawing(side: str, compare: bool) -> tuple[str, ...]:
    """The views that draw a layer of ``side``; outside compare, all on ``main``."""
    if not compare:
        return ("main",)
    return {"left": ("main",), "right": ("right",), "both": ("main", "right")}[side]


def _reduce_status(
    current: Mapping[str, tuple[int, int]],
    expected: Mapping[str, Sequence[View]],
    reports: Mapping[View, Mapping[str, LayerStatus]],
) -> dict[str, LayerStatus]:
    """Reduce the views' reports to one status per layer.

    ``current`` maps each layer id to its ``(token, instance)`` and
    ``expected`` to the mounted ``(view, side)`` pairs that draw it. A layer
    no mounted view draws has no status. A view that has not yet reported
    on the current instance counts as loading. Across views an error wins
    over loading and loading over ready, so a layer is ready only once every
    view drawing it is; the first failing view, in enrolment order, names
    the error.
    """
    out: dict[str, LayerStatus] = {}
    for layer_id, (token, instance) in current.items():
        views = expected.get(layer_id, ())
        if not views:
            continue
        failed: LayerStatus | None = None
        loading = False
        for view in views:
            report = reports.get(view, {}).get(layer_id)
            if report is None or report.instance != instance:
                loading = True
            elif report.status == "error":
                failed = report
                break
            elif report.status == "loading":
                loading = True
        if failed is not None:
            out[layer_id] = LayerStatus("error", failed.error, token, instance)
        else:
            status = "loading" if loading else "ready"
            out[layer_id] = LayerStatus(status, None, token, instance)
    return out


#: The link scope of maps built with no kernel running.
_PROCESS = uuid.uuid4().hex
# The link scope of each kernel, held weakly.
_KERNEL_SCOPES: weakref.WeakKeyDictionary[object, str] = weakref.WeakKeyDictionary()
# Guards the registries below; never held together with a widget's lock.
_LINK_LOCK = threading.Lock()
# token -> the maps of that group
_LINK_MEMBERS: dict[str, weakref.WeakSet[MapWidget]] = {}
# token -> the group's camera as (lng, lat, zoom)
_LINK_CAMERAS: dict[str, tuple[float, float, float]] = {}
# Orders the requests set_center and fit_bounds make, across every map.
_STAMPS = itertools.count(1)
# Only guards _STAMPS, and nothing is taken under it.
_STAMP_LOCK = threading.Lock()


def _stamp() -> int:
    """The stamp of a request ``set_center`` or ``fit_bounds`` makes now."""
    with _STAMP_LOCK:
        return next(_STAMPS)


def _current_kernel() -> object | None:
    """The kernel running now, found as Solara's ``Comm`` finds it, or None.

    Under Solara this relies on its patch of ``Kernel.instance()`` and
    ``Kernel.initialized()`` (``solara/server/patch.py``), which is not public API.
    pysepal's tests fail if two kernel contexts stop giving different kernels.
    """
    try:
        import ipykernel.kernelbase
    except ImportError:
        return None
    kernel = ipykernel.kernelbase.Kernel
    return kernel.instance() if kernel.initialized() else None


def _kernel_scope() -> str:
    """The link scope of the kernel running now, else of the process."""
    kernel = _current_kernel()
    if kernel is None:
        return _PROCESS
    with _LINK_LOCK:
        return _KERNEL_SCOPES.setdefault(kernel, uuid.uuid4().hex)


def _group_name(value) -> str | None:
    if value is None or (isinstance(value, str) and value):
        return value
    raise ValueError(f"link_group must be a non-empty string or None, got {value!r}")


def _members(token: str) -> weakref.WeakSet[MapWidget] | None:
    """A group's live maps; a group with none is dropped. Call with ``_LINK_LOCK`` held."""
    members = _LINK_MEMBERS.get(token)
    if members:
        return members
    _LINK_MEMBERS.pop(token, None)
    _LINK_CAMERAS.pop(token, None)
    return None


def _join(token: str, widget: MapWidget) -> tuple[float, float, float] | None:
    """Add ``widget`` to a group, returning the group's camera; call with ``_LINK_LOCK`` held."""
    camera = _LINK_CAMERAS.get(token) if _members(token) else None
    _LINK_MEMBERS.setdefault(token, weakref.WeakSet()).add(widget)
    return camera


def _leave(token: str, widget: MapWidget) -> None:
    """Remove ``widget`` from a group; call with ``_LINK_LOCK`` held."""
    members = _LINK_MEMBERS.get(token)
    if members is not None:
        members.discard(widget)
    _members(token)


class MapWidget(anywidget.AnyWidget):
    """A MapLibre map whose persistent configuration lives in ``state``."""

    _esm = _asset("widget.js")
    _css = _asset("widget.css")

    state = traitlets.Dict(read_only=True).tag(sync=True)
    view = traitlets.Dict(read_only=True).tag(sync=True)
    view_request = traitlets.Dict(read_only=True).tag(sync=True)
    insets = traitlets.Dict(dict.fromkeys(INSET_SIDES, 0), read_only=True).tag(sync=True)
    marker = traitlets.Dict(read_only=True).tag(sync=True)
    drawing = traitlets.Dict(read_only=True).tag(sync=True)
    draw_request = traitlets.Dict(read_only=True).tag(sync=True)
    drawn = traitlets.Dict(read_only=True).tag(sync=True)
    draw_tool = traitlets.Dict(read_only=True).tag(sync=True)
    cursor = traitlets.Enum(CURSORS, "").tag(sync=True)
    height = traitlets.Unicode("400px").tag(sync=True)
    _link = traitlets.Dict(read_only=True).tag(sync=True)

    def __init__(
        self,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        zoom: float = 2.0,
        height: str = "400px",
        loop: asyncio.AbstractEventLoop | None = None,
        link_group: str | None = None,
        **kwargs,
    ):
        """Create an empty map of the given CSS height, at ``center`` and ``zoom``.

        ``center`` is ``(lng, lat)``. ``loop`` is the loop callbacks run on,
        and the timer that expires silent views. It defaults to the loop
        running now, else the one running when the first message from a
        view arrives, and a message that finds it closed, as after a
        reconnect, adopts the loop running then. Leave it unset under
        Solara; pass one only for a host other than Solara. ``link_group``
        is the first :attr:`link_group`; a group that has a camera replaces
        ``center`` and ``zoom`` with it.
        """
        # Set before anything can raise, since close() reads them.
        self._lock = threading.RLock()
        self._closed = False
        self._link_name: str | None = None
        self._loop = loop if loop is not None else running_loop()
        self._callbacks = CallbackQueue()
        # The Layout ipywidgets builds is the widget's own; a given one is the caller's.
        self._owns_layout = "layout" not in kwargs
        self._expiry: asyncio.TimerHandle | None = None
        # (view_id, side) -> monotonic deadline of each mounted view
        self._views: dict[View, float] = {}
        # The views past their deadline, now in their grace period.
        self._late: set[View] = set()
        # (view_id, side) -> layer id -> that view's report on the layer
        self._reports: dict[View, dict[str, LayerStatus]] = {}
        self._link_scope = _kernel_scope()
        self._status: dict[str, LayerStatus] = {}
        self._status_callbacks: list[StatusCallback] = []
        self._view_callbacks: list[ViewCallback] = []
        self._click_callbacks: list[ClickCallback] = []
        # The request a user report was accepted on: acknowledgements of it lose.
        self._draw_user_seq: int | None = None
        self._draw = Draw(self)
        # The last request issued, and the one the last accepted report applied.
        self._issued = 1
        self._acknowledged = 0
        # The seq and stamp of the last request set_center or fit_bounds made.
        self._stamped = (0, 0)
        # The view whose user or link move on that request gave the camera in ``view``.
        self._user_view: str | None = None
        lng, lat = center
        # Set before super().__init__(), which opens the comm with this request.
        self._first_request = {"seq": 1, **_center_request(lng, lat, _finite("zoom", zoom))}
        self._link_member = uuid.uuid4().hex
        name = _group_name(link_group)
        camera = None
        if name is not None:
            self._link_name = name
            # One hold reads the camera and joins, so no forward falls between them.
            with _LINK_LOCK:
                camera = _join(self._token(name), self)
            if camera is not None:
                self._first_request = {"seq": 1, **_center_request(*camera)}
        # The last zoom asked for, until a report says what the views show.
        self._zoom: float | None = self._first_request["zoom"]
        try:
            super().__init__(height=height, **kwargs)
        except BaseException:
            # Left here, since the close() of a failed widget runs in __del__.
            self._leave_group()
            raise
        self._payloads: dict[str, bytes] = {}
        self._revision = 0
        self._next_instance = 1
        # id -> (identity, instance) of the last published snapshot
        self._instances: dict[str, tuple[tuple, int]] = {}
        # id -> (token, instance) of the last published snapshot
        self._current: dict[str, tuple[int, int]] = {}
        # id -> the sides drawing it, from the same publish
        self._drawn_on: dict[str, tuple[str, ...]] = {}
        self.on_msg(self._on_message)
        if name is not None:
            # A forward before the comm opened skipped this map.
            self._catch_up(self._token(name), camera)

    @traitlets.default("view_request")
    def _default_view_request(self) -> dict:
        return self._first_request

    @traitlets.default("_link")
    def _default_link(self) -> dict:
        if self._link_name is None:
            return {}
        return self._link_on(self._token(self._link_name), self._first_request["seq"])

    @traitlets.default("drawing")
    def _default_drawing(self) -> dict:
        return {"session": 0, "modes": [], "color": DEFAULT_COLOR, "labels": dict(DRAW_LABELS)}

    @traitlets.default("draw_request")
    def _default_draw_request(self) -> dict:
        return {"seq": 0, "features": []}

    @traitlets.default("drawn")
    def _default_drawn(self) -> dict:
        return {"request_seq": 0, "features": []}

    @traitlets.default("draw_tool")
    def _default_draw_tool(self) -> dict:
        return {"seq": 0, "session": 0, "mode": STATIC}

    @property
    def draw(self) -> Draw:
        """The drawing tools of this map, and the features they drew."""
        return self._draw

    @property
    def link_group(self) -> str | None:
        """The name of the group of maps this one keeps one camera with, or None.

        Setting it joins that group and ``None`` leaves it; the name the map
        has already changes nothing. A name is a non-empty string, and
        anything else raises ``ValueError`` and changes nothing. A map that
        joins a group with a camera requests that camera; one that joins
        with a ``view`` while the group has no camera gives it that view's.
        ``close`` leaves the group, so a closed map reads None, and setting
        it there does nothing.
        """
        return self._link_name

    @link_group.setter
    def link_group(self, value: str | None) -> None:
        """Join the group ``value`` names, or leave the group for None."""
        name = _group_name(value)
        token = None if name is None else self._token(name)
        camera = seeded = None
        with _LINK_LOCK:
            old = self._link_name
            # close() sets _closed before it leaves, so a close never misses this join.
            if self._closed or name == old:
                return
            self._link_name = name
            if old is not None:
                _leave(self._token(old), self)
            if token is not None:
                camera = _join(token, self)
                view = self.view
                if camera is None and view:
                    seeded = _LINK_CAMERAS[token] = (*view["center"], view["zoom"])
        with self._lock:
            if self._link_name != name:
                # A later assignment on another thread won.
                return
            if token is None:
                self.set_trait("_link", {})
            elif camera is not None:
                self._take_camera(token, *camera)
            else:
                self.set_trait("_link", self._link_on(token, self.view_request["seq"]))
        if token is not None:
            # A forward before _link was written skipped this map.
            self._catch_up(token, camera or seeded)

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        """The loop the widget runs its callbacks and expiry timer on now.

        It is the constructor's ``loop``, else the loop running at
        construction, else the one running when the first message from a
        view arrives. A message that finds that loop closed adopts the loop
        running then. None until there is one.
        """
        return self._loop

    @property
    def layer_status(self) -> Mapping[str, LayerStatus]:
        """Each drawn layer's status in the mounted views, read-only.

        Empty while no view is mounted.
        """
        return MappingProxyType(self._status)

    def on_status(self, callback: StatusCallback, remove: bool = False) -> None:
        """Call ``callback(layer_status)`` each time ``layer_status`` changes.

        ``remove=True`` unregisters it.
        """
        with self._lock:
            if remove:
                if callback in self._status_callbacks:
                    self._status_callbacks.remove(callback)
            elif callback not in self._status_callbacks:
                self._status_callbacks.append(callback)

    def on_view(self, callback: ViewCallback, remove: bool = False) -> None:
        """Call ``callback(view)`` with the new ``view`` on each accepted report.

        ``remove=True`` unregisters it.
        """
        with self._lock:
            if remove:
                if callback in self._view_callbacks:
                    self._view_callbacks.remove(callback)
            elif callback not in self._view_callbacks:
                self._view_callbacks.append(callback)

    def on_click(self, callback: ClickCallback, remove: bool = False) -> None:
        """Call ``callback(event)`` with a ``ClickEvent`` on each accepted click.

        ``remove=True`` unregisters it.
        """
        with self._lock:
            if remove:
                if callback in self._click_callbacks:
                    self._click_callbacks.remove(callback)
            elif callback not in self._click_callbacks:
                self._click_callbacks.append(callback)

    def set_marker(self, lng: float, lat: float, color: str = "#3388ff") -> None:
        """Show the one highlight marker at ``(lng, lat)`` in ``color``, in every view."""
        lnglat = _numbers([lng, lat], 2)
        if lnglat is None or not -90 <= lnglat[1] <= 90:
            raise ValueError("the marker needs a finite lng and a lat in [-90, 90]")
        if not isinstance(color, str):
            raise ValueError("the marker color must be a string")
        self.set_trait("marker", {"lnglat": lnglat, "color": color})

    def clear_marker(self) -> None:
        """Remove the highlight marker."""
        self.set_trait("marker", {})

    def set_center(
        self, lng: float, lat: float, zoom: float | None = None, *, animate: bool = False
    ) -> None:
        """Ask every view to center on ``(lng, lat)``; no zoom keeps theirs.

        Until a view reports, a new view has no zoom to keep, so no zoom
        means the last one asked for. With ``animate``, the views fly there.
        """
        self._center(lng, lat, zoom, stamped=True, animate=animate)

    def _center(
        self, lng: float, lat: float, zoom: float | None, stamped: bool, animate: bool = False
    ) -> None:
        request = _center_request(lng, lat, zoom, animate)
        with self._lock:
            if zoom is None:
                request["zoom"] = self._zoom
            elif self._zoom is not None:
                self._zoom = request["zoom"]
            self._request(request, stamped)

    def fit_bounds(
        self,
        bounds: tuple[float, float, float, float],
        padding: int = 20,
        max_zoom: float | None = None,
        *,
        animate: bool = False,
    ) -> None:
        """Ask every view to fit ``(west, south, east, north)``, ``padding`` px in.

        The fit stays inside the insets, zooms in no further than
        ``max_zoom`` (in [0, 24]; None is the map's maximum). A west east of
        east crosses the antimeridian. A view without a usable area fits
        once it has one. With ``animate``, the views fly there.
        """
        self._request(_bounds_request(bounds, padding, max_zoom, animate))

    def set_insets(self, *, left: int = 0, right: int = 0, top: int = 0, bottom: int = 0) -> None:
        """Declare how many CSS pixels of each side of the map other UI covers.

        The views center, fit and report bounds inside the rest, and move
        their controls in by as much; the map itself keeps its place on
        screen, as under a panel that opens over it. A side left out is 0; a value that is
        not a non-negative int raises ``ValueError`` and changes nothing.
        """
        self.set_trait("insets", _insets(left, right, top, bottom))

    def close(self) -> None:
        """Close the widget and the layout it built, and leave its link group.

        Later messages from its views do nothing. A part that fails to close
        is logged, and the rest still closes.
        """
        with self._lock:
            self._closed = True
            _close_part("view expiry", self._cancel_expiry)
            self._views.clear()
            self._late.clear()
            self._reports.clear()
            self._status = {}
        _close_part("link group", self._leave_group)
        _close_part("callbacks", self._callbacks.close)
        # _trait_values, not self.layout: reading an unset trait would build one
        layout = self._trait_values.get("layout") if self._owns_layout else None
        _close_part("widget", super().close)
        if layout is not None:
            _close_part("layout", layout.close)

    def _request(self, request: dict, stamped: bool = True) -> None:
        # Under the lock, so requests from several threads go out in seq order.
        with self._lock:
            self._issued += 1
            if stamped:
                self._stamped = (self._issued, _stamp())
            self.set_trait("view_request", {"seq": self._issued, **request})

    def _token(self, name: str) -> str:
        return f"{self._link_scope}:{name}"

    def _link_on(self, token: str, seq: int) -> dict:
        """The ``_link`` of this map in group ``token``, written on request ``seq``."""
        return {"group": token, "seq": seq, "member": self._link_member}

    def _leave_group(self) -> None:
        """Leave the link group once; call without the widget lock.

        A later call takes no lock: ipywidgets' ``__del__`` closes the widget
        again on whatever thread collects it, which may hold ``_LINK_LOCK``.
        """
        if self._link_name is None:
            return
        with _LINK_LOCK:
            name, self._link_name = self._link_name, None
            if name is not None:
                _leave(self._token(name), self)

    def _take_camera(self, token: str, lng: float, lat: float, zoom: float) -> None:
        """Request a group's camera and link on that request, in one message."""
        with self._lock, self.hold_sync():
            self._center(lng, lat, zoom, stamped=False)
            self.set_trait("_link", self._link_on(token, self.view_request["seq"]))

    def _catch_up(self, token: str, seen: tuple[float, float, float] | None) -> None:
        """Take the group's camera if it is no longer ``seen``; call without the lock."""
        with _LINK_LOCK:
            camera = _LINK_CAMERAS.get(token)
        if camera is None or camera == seen:
            return
        with self._lock:
            if not self._closed and self._link.get("group") == token:
                self._take_camera(token, *camera)

    def _follow(
        self, token: str, lng: float, lat: float, zoom: float, stamp: int | None = None
    ) -> None:
        """Take a peer's camera, unless this map left ``token``, shows a view or holds a newer request.

        ``stamp`` is the stamp of the request the peer's camera acknowledges,
        None when a move gave it.
        """
        with self._lock:
            if (
                self._closed
                # Not open yet: the constructor catches up once it is.
                or self.comm is None
                or self._link.get("group") != token
                or any(side == "main" for _, side in self._views)
                or (stamp is not None and self._holds_newer(stamp))
            ):
                return
            self._take_camera(token, lng, lat, zoom)

    def _holds_newer(self, stamp: int) -> bool:
        """Whether this map's request is its own, newer than its link and ``stamp``; call with the lock.

        Such a request moves the group once a view shows it.
        """
        seq, own = self._stamped
        return seq == self._issued and seq > self._link.get("seq", 0) and own > stamp

    def _follow_peers(
        self, token: str, center: list[float], zoom: float, stamp: int | None
    ) -> None:
        """Move the group's other maps that show no view to this camera; call without the lock.

        A camera the group holds already moves nobody, so a hidden map gets
        one request per move, however many members report it. ``stamp`` is
        as for ``_follow``.
        """
        camera = (center[0], center[1], zoom)
        with _LINK_LOCK:
            members = _members(token)
            if members is None or _LINK_CAMERAS.get(token) == camera:
                return
            _LINK_CAMERAS[token] = camera
            peers = [m for m in members if m is not self]
        for peer in peers:
            try:
                peer._follow(token, *camera, stamp)
            except Exception:
                logger.exception("pysepal-map: a linked map could not follow")

    def _sides_of(self, layer_id: str) -> Sequence[str]:
        """The sides that draw a layer in the last publish; call with the lock held."""
        return self._drawn_on.get(layer_id, ())

    def _on_message(self, _widget, content, _buffers) -> None:
        if self.comm is None or not isinstance(content, dict):
            return
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                # A dead loop took its timer along; the next arm makes one.
                self._loop = running_loop()
                self._expiry = None
            self._renew(content)
        kind = content.get("type")
        if kind == "pull":
            self._answer_pull(content.get("digests"))
        elif kind == "view_open":
            self._view_open(content)
        elif kind == "view_close":
            self._view_close(content)
        elif kind == "status":
            self._report(content)
        elif kind == "view_report":
            self._view_report(content)
        elif kind == "click":
            self._click(content)
        elif kind == "draw_report":
            self._draw_report(content)

    def _answer_pull(self, digests) -> None:
        """Send each digest's bytes, or ``missing`` once a publish dropped them."""
        if not isinstance(digests, list):
            return
        for digest in dict.fromkeys(d for d in digests if isinstance(d, str)):
            data = self._payloads.get(digest)
            if data is None:
                self.send({"type": "data", "digest": digest, "missing": True}, [])
            else:
                self.send({"type": "data", "digest": digest}, [data])

    def _renew(self, content: dict) -> None:
        """Renew the known views a message came from; call with the lock held.

        A message without a side, such as ``view_report``, renews every side
        of its view.
        """
        view_id, side = content.get("view_id"), content.get("side")
        if not isinstance(view_id, str):
            return
        due = self._now() + VIEW_EXPIRY_S
        for view in self._views:
            if view[0] == view_id and side in (None, view[1]):
                self._views[view] = due
                self._late.discard(view)

    @staticmethod
    def _view_of(content: dict) -> View | None:
        view_id, side = content.get("view_id"), content.get("side")
        if not isinstance(view_id, str) or not view_id or side not in SIDES:
            return None
        return view_id, side

    def _view_open(self, content: dict) -> None:
        view = self._view_of(content)
        if view is None:
            return
        with self._lock:
            if self._closed:
                return
            self._expire_due()
            enrolled = view not in self._views
            self._views[view] = self._now() + VIEW_EXPIRY_S
            if enrolled:
                self._reports[view] = {}
            self._arm_expiry()
        # A heartbeat only renews; a new or returning view replays its reports.
        if enrolled:
            self.send({"type": "status_request", "view_id": view[0], "side": view[1]})
        self._refresh()

    def _view_close(self, content: dict) -> None:
        view = self._view_of(content)
        with self._lock:
            if view not in self._views:
                return
            del self._views[view]
            self._late.discard(view)
            self._reports.pop(view, None)
            if not self._views:
                self._cancel_expiry()
        self._refresh()

    def _report(self, content: dict) -> None:
        """Keep one view's report on the current instance of a layer.

        Reports from views that are not mounted, about layers or instances
        no longer drawn, or about a style operation of an earlier publish are
        stale and ignored.
        """
        view = self._view_of(content)
        layer_id = content.get("id")
        token, instance = content.get("token"), content.get("instance")
        status, error = content.get("status"), content.get("error")
        style_revision = content.get("style_revision")
        if (
            view is None
            or not isinstance(layer_id, str)
            or status not in STATUSES
            or not (error is None or isinstance(error, str))
            or not (_is_int(token) and _is_int(instance))
            or not (style_revision is None or _is_int(style_revision))
        ):
            return
        with self._lock:
            self._expire_due()
            if (
                view in self._views
                and self._current.get(layer_id) == (token, instance)
                and (style_revision is None or style_revision == self._revision)
                and view[1] in self._sides_of(layer_id)
            ):
                error = error if status == "error" else None
                report = LayerStatus(status, error, token, instance)
                self._reports[view][layer_id] = report
        self._refresh()

    def _view_report(self, content: dict) -> None:
        """Mirror one view's camera in ``view`` and tell the callbacks.

        A report of a view that is not mounted, or on a request older than
        the one the last accepted report applied, is stale and ignored, and
        so is one with a latitude outside [-90, 90] or a zoom outside [0, 24].
        On the same request, a camera a user move or a link move gave is kept
        for redisplay: a later user or link move replaces it, and so does a
        resize of the view that moved, which keeps that camera. An
        acknowledgement, or another view's resize, does not. An accepted
        report that is not a resize then moves the linked maps that show no
        view, but an acknowledgement moves none that holds a newer request of
        its own (see ``_holds_newer``).
        """
        view_id, seq = content.get("view_id"), content.get("request_seq")
        center = _numbers(content.get("center"), 2)
        zoom = _numbers([content.get("zoom")], 1)
        bounds = _numbers(content.get("bounds"), 4)
        cause = content.get("cause")
        if (
            not isinstance(view_id, str)
            or not (_is_int(seq) and seq >= 0)
            or center is None
            or not -90 <= center[1] <= 90
            or zoom is None
            or not 0 <= zoom[0] <= MAX_ZOOM
            or bounds is None
            or cause not in CAUSES
        ):
            return
        forward = stamp = None
        with self._lock:
            self._expire_due()
            same = seq == self._acknowledged and self._user_view is not None
            own_resize = same and cause == "resize" and view_id == self._user_view
            kept = same and cause not in _TAKING and not own_resize
            if (
                not self._closed
                and any(v[0] == view_id for v in self._views)
                and self._acknowledged <= seq <= self._issued
                and not kept
            ):
                self._acknowledged = seq
                if cause in _TAKING:
                    self._user_view = view_id
                elif not own_resize:
                    self._user_view = None
                # A new view now restores this camera, zoom included.
                self._zoom = None
                view = {"center": center, "zoom": zoom[0], "bounds": bounds}
                view["request_seq"] = seq
                view["cause"] = cause
                # Under the lock, so reports on other threads cannot reorder it.
                self.set_trait("view", view)
                for callback in self._view_callbacks:
                    self._callbacks.put(callback, copy.deepcopy(view))
                # A resize keeps the camera, and could undo a newer fit on a hidden map.
                if cause != "resize":
                    forward = self._link.get("group")
                if cause == "request":
                    # Only the last set_center or fit_bounds keeps its stamp: one
                    # it replaced is reported just before it.
                    stamped_seq, own = self._stamped
                    stamp = own if seq == stamped_seq else 0
        if forward:
            self._follow_peers(forward, center, zoom[0], stamp)
        # Expiring a view can change the status too.
        self._refresh()

    def _click(self, content: dict) -> None:
        """Queue a click from a mounted view to the click callbacks.

        Hits that are not objects, or not on the current instance of their
        layer, are dropped; a layer whose hit was on a retired instance is
        named in ``stale``.
        """
        view = self._view_of(content)
        lnglat = _numbers(content.get("lnglat"), 2)
        zoom = _numbers([content.get("zoom")], 1)
        settled, hits = content.get("settled"), content.get("features")
        hidden = content.get("hidden_features", [])
        if (
            view is None
            or lnglat is None
            or not -90 <= lnglat[1] <= 90
            or zoom is None
            or not isinstance(settled, bool)
            or not isinstance(hits, list)
            or not isinstance(hidden, list)
        ):
            return
        with self._lock:
            self._expire_due()
            if self._closed or view not in self._views:
                return
            stale: set[str] = set()
            features, under = self._hits(hits, stale), self._hits(hidden, stale)
            event = ClickEvent(
                lnglat[0], lnglat[1], zoom[0], settled, features, frozenset(stale), view[0], under
            )
            for callback in self._click_callbacks:
                self._callbacks.put(callback, event)
        self._callbacks.flush(self._loop)

    def _hits(self, hits: list, stale: set[str]) -> tuple[FeatureHit, ...]:
        """The well-formed hits on current instances; the layers of retired ones go in ``stale``."""
        features: list[FeatureHit] = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            layer_id, instance = hit.get("id"), hit.get("instance")
            properties = hit.get("properties")
            if (
                not isinstance(layer_id, str)
                or not _is_int(instance)
                or not isinstance(properties, dict)
            ):
                continue
            if self._current.get(layer_id, (None, None))[1] != instance:
                stale.add(layer_id)
                continue
            features.append(
                FeatureHit(layer_id, instance, MappingProxyType(copy.deepcopy(properties)))
            )
        return tuple(features)

    def _draw_report(self, content: dict) -> None:
        """Mirror one view's drawn features in ``drawn``, and tell the session a user's.

        Only a report of a mounted view on the current request counts, and on
        that request, once a user report was accepted, an acknowledgement from
        any view is dropped. Features ``check_features`` refuses are dropped.
        """
        view = self._view_of(content)
        seq, cause, features = (content.get(k) for k in ("request_seq", "cause", "features"))
        if (
            view is None
            or not (_is_int(seq) and seq >= 0)
            or cause not in DRAW_CAUSES
            or not isinstance(features, list)
        ):
            return
        with self._lock:
            self._expire_due()
            if (
                not self._closed
                and view in self._views
                and seq == self.draw_request["seq"]
                and not (cause == "request" and self._draw_user_seq == seq)
            ):
                accepted = report_features(features)
                if cause == "user":
                    self._draw_user_seq = seq
                    # The current request is the active session's, since begin
                    # and end each write a new one.
                    callback = self._draw._change_callback()
                    # Before ``drawn`` is written: a report that an observer of
                    # it gets accepted then runs its callback after this one.
                    if callback is not None:
                        collection = {"type": "FeatureCollection", "features": accepted}
                        self._callbacks.put(callback, copy.deepcopy(collection))
                self.set_trait("drawn", {"request_seq": seq, "features": accepted})
        self._refresh()

    def _refresh(self) -> None:
        """Reduce the reports again, tell the callbacks if that changed.

        Also runs whatever callbacks are queued.
        """
        with self._lock:
            if not self._closed:
                expected = {
                    layer_id: [v for v in self._views if v[1] in self._sides_of(layer_id)]
                    for layer_id in self._current
                }
                status = _reduce_status(self._current, expected, self._reports)
                if status != self._status:
                    self._status = status
                    snapshot = MappingProxyType(status)
                    # Queued as the snapshot is taken: they run in its order.
                    for callback in self._status_callbacks:
                        self._callbacks.put(callback, snapshot)
        self._callbacks.flush(self._loop)

    def _now(self) -> float:
        loop = self._loop
        return time.monotonic() if loop is None else loop.time()

    def _expire_due(self) -> None:
        """Drop views silent through their grace; call with the lock held.

        A view found past its deadline is late, not gone: it has
        ``VIEW_GRACE_S`` more, and any message from it meanwhile renews it.
        """
        now = self._now()
        for view, due in list(self._views.items()):
            if due > now:
                continue
            if view in self._late:
                del self._views[view]
                self._late.discard(view)
                self._reports.pop(view, None)
            else:
                self._late.add(view)
                self._views[view] = now + VIEW_GRACE_S
        if not self._views:
            self._cancel_expiry()

    def _arm_expiry(self) -> None:
        """Point the one expiry timer at the earliest deadline, under the lock.

        A renewed deadline, or a grace, is only ever later, so neither re-arms
        it: the timer re-arms itself for the next deadline when it fires.
        """
        loop = self._loop
        if self._expiry is not None or not self._views:
            return
        if loop is None or loop.is_closed():
            return
        if loop.is_running() and running_loop() is not loop:
            # A message handled off the owner loop's thread.
            loop.call_soon_threadsafe(self._arm_expiry_locked)
            return
        delay = max(0.0, min(self._views.values()) - loop.time())
        self._expiry = loop.call_later(delay, self._on_expiry)

    def _arm_expiry_locked(self) -> None:
        with self._lock:
            if not self._closed:
                self._arm_expiry()

    def _on_expiry(self) -> None:
        with self._lock:
            self._expiry = None
            if self._closed:
                return
            self._expire_due()
            self._arm_expiry()
        self._refresh()

    def _cancel_expiry(self) -> None:
        handle, self._expiry = self._expiry, None
        if handle is None:
            return
        loop = self._loop
        if loop is not None and loop.is_running() and running_loop() is not loop:
            loop.call_soon_threadsafe(handle.cancel)
        else:
            handle.cancel()

    def add_payload(self, data: bytes) -> str:
        """Keep GeoJSON bytes for the next publish and return their sha256 digest.

        The next ``publish`` drops every payload its state does not reference,
        including ones added since the publish before it, so add payloads right
        before the publish that uses them.
        """
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            self._payloads[digest] = bytes(data)
        return digest

    def has_payload(self, digest: str) -> bool:
        """Whether the widget still holds the bytes of ``digest``."""
        with self._lock:
            return digest in self._payloads

    def publish(self, state: MapState) -> None:
        """Publish ``state`` as the next snapshot; a failure changes nothing.

        Every GeoJSON digest in ``state`` must come from ``add_payload``. The
        publish then drops the payloads ``state`` does not reference, even ones
        added since the last publish: add each payload right before the publish
        that uses it. Publishes from several threads publish one at a time.
        Observers of ``state`` run under the widget lock, so a publish they make
        publishes after this one.
        """
        if not isinstance(state, MapState):
            raise TypeError("publish expects a MapState")
        # One publish at a time from validation to prune, so concurrent publishes
        # publish in revision order and never share an instance.
        with self._lock:
            referenced = {
                layer.source.digest
                for layer in state.layers
                if isinstance(layer.source, GeoJSONSource)
            }
            missing = sorted(referenced - self._payloads.keys())
            if missing:
                raise KeyError(f"payloads never added: {', '.join(missing)}")

            data = state.to_json()
            instances: dict[str, tuple[tuple, int]] = {}
            next_instance = self._next_instance
            for layer, entry in zip(state.layers, data["layers"]):
                identity = (layer.source, layer.attribution, layer.token)
                previous = self._instances.get(layer.id)
                if previous is not None and previous[0] == identity:
                    instance = previous[1]
                else:
                    instance = next_instance
                    next_instance += 1
                instances[layer.id] = (identity, instance)
                entry["instance"] = instance
            data["revision"] = self._revision + 1
            current = {layer.id: (layer.token, instances[layer.id][1]) for layer in state.layers}

            self._instances = instances
            self._next_instance = next_instance
            self._revision += 1
            self._current = current
            self._drawn_on = {
                layer.id: _sides_drawing(layer.side, state.compare) for layer in state.layers
            }
            # Retire reports on replaced and removed instances, and those of a
            # side that no longer draws the layer (the browser sends nothing
            # when it stops), before any view sees the new snapshot.
            for (_, side), reports in self._reports.items():
                for layer_id, report in list(reports.items()):
                    if current.get(layer_id) != (
                        report.token,
                        report.instance,
                    ) or side not in self._drawn_on.get(layer_id, ()):
                        del reports[layer_id]
            # Pruned first: a publish that a state observer makes prunes last.
            self._payloads = {d: b for d, b in self._payloads.items() if d in referenced}
            self.set_trait("state", data)
        # The callbacks run outside the lock.
        self._refresh()
