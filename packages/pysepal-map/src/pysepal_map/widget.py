"""The MapLibre map widget, and the rules between it and its views.

``state.py`` declares and validates the state. This module publishes it and
keeps the rest of the contract, summed up here for whoever drives a widget or
writes a front end for it.

Draws. ``MapWidget.draw`` publishes a whole ``MapState`` in the ``state``
trait, with a ``revision`` one above the last. Each layer gets an
``instance``, an integer that grows over the widget's life, given in input
order from 1. A layer gets a new one when it first appears, when it comes back
after a draw without it, and when its source, source attribution or token
changes; visibility, opacity, paint, zooms, zone and order keep it. A draw that
raises publishes nothing and changes no counter.

Style ids. A view owns every source and layer whose id starts with ``psm:``. A
layer's source is ``psm:<id>:<instance>``, with the id escaped as
``encodeURIComponent`` does, and its layers add a part: ``:fill``, ``:line``
and ``:circle``, or ``:raster``. The basemap's source and layer are
``psm:basemap``. A new instance is a new source, so nothing reported about the
old one counts for it. Owned layers stay below every other layer, and the view
never changes those.

Messages. Each mounted view has a unique ``view_id`` and a side (``main``;
``left`` and ``right`` are kept for a compare view). It sends JSON messages
with a ``type``: ``view_open`` on mount and every 20 s, ``view_close``,
``pull`` with the GeoJSON digests it lacks, ``status`` on one layer instance,
and ``view_report`` with its camera. A ``status`` on a rejected style operation
also carries its ``style_revision``, which counts only for the current draw.
Python answers each pulled digest with a ``data`` message that carries the
UTF-8 GeoJSON as one buffer, or ``missing: true`` once a draw dropped it, and
sends ``status_request`` to ask one view and side to send its statuses again.
Python's messages reach every view, so each ignores what it did not ask for.
Any message renews its view; one silent for ``VIEW_EXPIRY_S`` and then
``VIEW_GRACE_S`` is dropped with its reports.

Camera. The browser owns it. ``set_center`` and ``fit_bounds`` write
``view_request`` with a ``seq`` that only grows. A new view first restores the
camera saved in ``view``, then applies each request newer than the last one it
applied, and every report names that request and its ``cause``: ``user``,
``request`` or ``resize``. ``view`` mirrors the last accepted report. Reports
from views not mounted, or on an older request, are dropped, and on the same
request a user's camera is kept over an acknowledgement or another view's
resize.

A view marks its root element with ``data-psm-revision`` once its owned style
matches that revision and every GeoJSON source has loaded its data.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import math
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

import anywidget
import traitlets

from ._callbacks import CallbackQueue, running_loop
from .state import GeoJSONSource, LayerStatus, MapState, _finite

_STATIC = Path(__file__).parent / "static"

#: The sides a view can render: ``main``, or one half of a compare view.
SIDES = ("main", "left", "right")
STATUSES = ("loading", "ready", "error")
#: What moved a view's camera: a user, a request, or anything else.
CAUSES = ("user", "request", "resize")
#: A mounted view repeats ``view_open`` every 20 s, and any message from it
#: renews it; one silent this long is late. Chrome runs the timers of a
#: hidden tab as rarely as once a minute.
VIEW_EXPIRY_S = 150.0
#: How long a late view has left. A cell that holds the loop past every
#: deadline makes them all late at once; the messages queued behind it then
#: renew them within this grace.
VIEW_GRACE_S = 10.0
#: The map's maximum zoom.
MAX_ZOOM = 24

StatusCallback = Callable[[Mapping[str, LayerStatus]], object]
ViewCallback = Callable[[dict], Any]
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


def _latitude(name: str, value) -> float:
    if not -90 <= _finite(name, value) <= 90:
        raise ValueError(f"{name} must be in [-90, 90], got {value!r}")
    return float(value)


def _center_request(lng, lat, zoom) -> dict:
    center = [float(_finite("lng", lng)), _latitude("lat", lat)]
    if zoom is not None and not 0 <= _finite("zoom", zoom) <= MAX_ZOOM:
        raise ValueError(f"zoom must be in [0, {MAX_ZOOM}], got {zoom!r}")
    return {"center": center, "zoom": None if zoom is None else float(zoom)}


def _bounds_request(bounds, padding) -> dict:
    corners = tuple(bounds)
    if len(corners) != 4:
        raise ValueError(f"bounds must be (west, south, east, north), got {bounds!r}")
    west, south, east, north = corners
    box = [
        float(_finite("west", west)),
        _latitude("south", south),
        float(_finite("east", east)),
        _latitude("north", north),
    ]
    if box[1] > box[3]:
        raise ValueError(f"south must not be above north, got {bounds!r}")
    if not _is_int(padding) or padding < 0:
        raise ValueError(f"padding must be a whole number of pixels, got {padding!r}")
    return {"bounds": box, "padding": padding}


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


class MapWidget(anywidget.AnyWidget):
    """A MapLibre map whose persistent configuration lives in ``state``."""

    _esm = _STATIC / "widget.js"
    _css = _STATIC / "widget.css"

    state = traitlets.Dict().tag(sync=True)
    view = traitlets.Dict().tag(sync=True)
    view_request = traitlets.Dict().tag(sync=True)
    height = traitlets.Unicode("400px").tag(sync=True)

    def __init__(
        self,
        *,
        center: tuple[float, float] = (0.0, 0.0),
        zoom: float = 2.0,
        height: str = "400px",
        loop: asyncio.AbstractEventLoop | None = None,
        **kwargs,
    ):
        """Create an empty map of the given CSS height, at ``center`` and ``zoom``.

        ``center`` is ``(lng, lat)``. ``loop`` is the session loop: callbacks
        run there, and so does the timer that expires silent views. It
        defaults to the loop running now, else the one running when the
        first message from a view arrives. A Solara render can run with no
        loop running, so pass the session loop there.
        """
        # Set before anything can raise, since close() reads them.
        self._lock = threading.RLock()
        self._closed = False
        self._loop = loop if loop is not None else running_loop()
        self._callbacks = CallbackQueue()
        self._expiry: asyncio.TimerHandle | None = None
        # (view_id, side) -> monotonic deadline of each mounted view
        self._views: dict[View, float] = {}
        # The views past their deadline, now in their grace period.
        self._late: set[View] = set()
        # (view_id, side) -> layer id -> that view's report on the layer
        self._reports: dict[View, dict[str, LayerStatus]] = {}
        self._status: dict[str, LayerStatus] = {}
        self._status_callbacks: list[StatusCallback] = []
        self._view_callbacks: list[ViewCallback] = []
        # The last request issued, and the one the last accepted report applied.
        self._issued = 1
        self._acknowledged = 0
        # The view whose user move on that request gave the camera in ``view``.
        self._user_view: str | None = None
        lng, lat = center
        first = {"seq": 1, **_center_request(lng, lat, _finite("zoom", zoom))}
        # The last zoom asked for, until a report says what the views show.
        self._zoom: float | None = first["zoom"]
        super().__init__(height=height, view_request=first, **kwargs)
        self._payloads: dict[str, bytes] = {}
        self._revision = 0
        self._next_instance = 1
        # id -> (identity, instance) of the last published snapshot
        self._instances: dict[str, tuple[tuple, int]] = {}
        # id -> (token, instance) of the last published snapshot
        self._current: dict[str, tuple[int, int]] = {}
        self.on_msg(self._on_message)

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

    def set_center(self, lng: float, lat: float, zoom: float | None = None) -> None:
        """Ask every view to center on ``(lng, lat)``; no zoom keeps theirs.

        Until a view reports, a new view has no zoom to keep, so no zoom
        means the last one asked for.
        """
        request = _center_request(lng, lat, zoom)
        with self._lock:
            if zoom is None:
                request["zoom"] = self._zoom
            elif self._zoom is not None:
                self._zoom = request["zoom"]
            self._request(request)

    def fit_bounds(self, bounds: tuple[float, float, float, float], padding: int = 20) -> None:
        """Ask every view to fit ``(west, south, east, north)``, ``padding`` px in.

        A west east of east crosses the antimeridian. A view without a size
        fits once it has one.
        """
        self._request(_bounds_request(bounds, padding))

    def close(self) -> None:
        """Close the widget; later messages from its views do nothing."""
        with self._lock:
            self._closed = True
            self._cancel_expiry()
            self._views.clear()
            self._late.clear()
            self._reports.clear()
            self._status = {}
        self._callbacks.close()
        super().close()

    def _request(self, request: dict) -> None:
        # Under the lock, so requests from several threads go out in seq order.
        with self._lock:
            self._issued += 1
            self.view_request = {"seq": self._issued, **request}

    def _sides_of(self, layer_id: str) -> Sequence[str]:
        """The sides that draw a layer; every Phase 1 layer is on ``main``."""
        return ("main",)

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

    def _answer_pull(self, digests) -> None:
        """Send each digest's bytes, or ``missing`` once a draw dropped them."""
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
        no longer drawn, or about a style operation of an earlier draw are
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
        the one the last accepted report applied, is stale and ignored. On
        the same request, a camera a user move gave is kept for redisplay:
        a later user move replaces it, and so does a resize of the view the
        user moved, which keeps it that user's camera. An acknowledgement,
        or another view's resize, does not.
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
            or zoom is None
            or bounds is None
            or cause not in CAUSES
        ):
            return
        with self._lock:
            self._expire_due()
            same = seq == self._acknowledged and self._user_view is not None
            own_resize = same and cause == "resize" and view_id == self._user_view
            kept = same and cause != "user" and not own_resize
            if (
                not self._closed
                and any(v[0] == view_id for v in self._views)
                and self._acknowledged <= seq <= self._issued
                and not kept
            ):
                self._acknowledged = seq
                if cause == "user":
                    self._user_view = view_id
                elif not own_resize:
                    self._user_view = None
                # A new view now restores this camera, zoom included.
                self._zoom = None
                view = {"center": center, "zoom": zoom[0], "bounds": bounds}
                view["request_seq"] = seq
                # Under the lock, so reports on other threads cannot reorder it.
                self.view = view
                for callback in self._view_callbacks:
                    self._callbacks.put(callback, copy.deepcopy(view))
        # Expiring a view can change the status too.
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
        """Keep GeoJSON bytes for the next draw and return their sha256 digest.

        The next ``draw`` drops every payload its state does not reference,
        including ones added since the draw before it, so add payloads right
        before the draw that uses them.
        """
        digest = hashlib.sha256(data).hexdigest()
        with self._lock:
            self._payloads[digest] = bytes(data)
        return digest

    def draw(self, state: MapState) -> None:
        """Publish ``state`` as the next snapshot; a failure changes nothing.

        Every GeoJSON digest in ``state`` must come from ``add_payload``. The
        draw then drops the payloads ``state`` does not reference, even ones
        added since the last draw: add each payload right before the draw
        that uses it. Draws from several threads publish one at a time.
        """
        if not isinstance(state, MapState):
            raise TypeError("draw expects a MapState")
        # One draw at a time from validation to prune, so concurrent draws
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
            # Retire reports on replaced and removed instances before any
            # view sees the new snapshot.
            for reports in self._reports.values():
                for layer_id, report in list(reports.items()):
                    if current.get(layer_id) != (report.token, report.instance):
                        del reports[layer_id]
            self.state = data
            self._payloads = {d: b for d, b in self._payloads.items() if d in referenced}
        # The callbacks run outside the lock.
        self._refresh()
