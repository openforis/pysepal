"""Keep several maps on one camera."""

import threading
import weakref
from collections.abc import Callable

from .widget import MapWidget

_lock = threading.Lock()
_linked: weakref.WeakSet[MapWidget] = weakref.WeakSet()


class _Member:
    """One linked widget, held weakly, and the highest seq the group issued on it."""

    def __init__(self, widget: MapWidget) -> None:
        self.ref = weakref.ref(widget)
        self.issued = 0
        self.callback: Callable[[dict], None] | None = None


def _issue(member: _Member, widget: MapWidget, send: Callable[[], None]) -> None:
    # Under the widget's lock, so a request from another thread cannot slip
    # between the call and reading its seq.
    with widget._lock:
        send()
        member.issued = widget.view_request["seq"]


def _forward(members: list[_Member], origin: _Member, view: dict) -> None:
    cause, seq = view["cause"], view["request_seq"]
    # Below the group's seq the report is superseded; a request at it is the echo.
    if cause == "user":
        if seq < origin.issued:
            return
    elif cause != "request" or seq <= origin.issued:
        return
    if cause == "request":
        # Another view of the origin may report the same request again.
        widget = origin.ref()
        if widget is not None:
            with widget._lock:
                origin.issued = max(origin.issued, seq)
    (lng, lat), zoom = view["center"], view["zoom"]
    for member in members:
        widget = member.ref()
        if member is not origin and widget is not None:
            _issue(member, widget, lambda w=widget: w.set_center(lng, lat, zoom))


def link_views(*widgets: MapWidget) -> Callable[[], None]:
    """Keep the cameras of two or more maps together; return the function that unlinks them.

    The others take the first map's view now, and from then on a user's
    move of any map, or a ``set_center`` or ``fit_bounds`` the app makes
    on one, moves the others to that center and zoom. A map holds one group
    at most, and the group holds no strong reference to its maps.
    """
    if len(widgets) < 2:
        raise ValueError("link_views needs at least two maps")
    if len({id(w) for w in widgets}) != len(widgets):
        raise ValueError("link_views got the same map twice")
    members = [_Member(w) for w in widgets]
    with _lock:
        if any(w in _linked for w in widgets):
            raise ValueError("a map can be in one linked group only")
        _linked.update(widgets)

    for member, widget in zip(members, widgets):
        with widget._lock:
            member.issued = widget.view_request["seq"]
    first = widgets[0]
    with first._lock:
        view = first.view
        pending = {k: v for k, v in first.view_request.items() if k != "seq"}
    for member, widget in list(zip(members, widgets))[1:]:
        if view:
            _issue(member, widget, lambda w=widget: w.set_center(*view["center"], view["zoom"]))
        else:
            _issue(member, widget, lambda w=widget: w._request(dict(pending)))

    for member in members:

        def on_view(view: dict, member=member) -> None:
            _forward(members, member, view)

        member.callback = on_view
        widget = member.ref()
        if widget is not None:
            widget.on_view(on_view)

    def unlink() -> None:
        for member in members:
            widget = member.ref()
            if widget is not None and member.callback is not None:
                widget.on_view(member.callback, remove=True)
                with _lock:
                    _linked.discard(widget)

    return unlink
