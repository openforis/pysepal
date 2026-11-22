"""Keep several maps on one camera."""

import threading
import weakref
from collections.abc import Callable

from .widget import MapWidget

_lock = threading.Lock()


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


class _Group:
    def __init__(self, members: list[_Member]) -> None:
        self.members = members
        self.active = True
        self.unlink: Callable[[], None] = lambda: None

    def holds(self, widgets: tuple[MapWidget, ...]) -> bool:
        """Whether ``widgets`` are exactly its members still alive, in any order."""
        alive = {id(w) for m in self.members if (w := m.ref()) is not None}
        return alive == {id(w) for w in widgets}


# The group of each linked widget, held weakly.
_groups: "weakref.WeakKeyDictionary[MapWidget, _Group]" = weakref.WeakKeyDictionary()


def _release(group: _Group) -> None:
    """Free the widgets of ``group``; under ``_lock``."""
    group.active = False
    for member in group.members:
        widget = member.ref()
        if widget is not None and _groups.get(widget) is group:
            del _groups[widget]


def _forward(group: _Group, origin: _Member, view: dict) -> None:
    if not group.active:
        return
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
    for member in group.members:
        widget = member.ref()
        if member is not origin and widget is not None:
            _issue(member, widget, lambda w=widget: w.set_center(lng, lat, zoom))


def link_views(*widgets: MapWidget) -> Callable[[], None]:
    """Keep the cameras of two or more maps together; return the function that unlinks them.

    The others take the first map's view now, and from then on a user's
    move of any map, or a ``set_center`` or ``fit_bounds`` the app makes
    on one, moves the others to that center and zoom. A map holds one group
    at most, and the group holds no strong reference to its maps. Linking
    exactly the maps of a live group again, in any order, changes nothing and
    returns that group's unlink function; any other overlap raises.
    """
    if len(widgets) < 2:
        raise ValueError("link_views needs at least two maps")
    if len({id(w) for w in widgets}) != len(widgets):
        raise ValueError("link_views got the same map twice")
    members = [_Member(w) for w in widgets]
    group = _Group(members)

    def unlink() -> None:
        # Only the first call acts: a later one must not free widgets another group took.
        with _lock:
            if not group.active:
                return
            _release(group)
        for member in members:
            widget = member.ref()
            if widget is not None and member.callback is not None:
                widget.on_view(member.callback, remove=True)

    # Set before the group is visible, so a relink never returns a placeholder.
    group.unlink = unlink
    with _lock:
        found = {id(g): g for w in widgets if (g := _groups.get(w)) is not None}
        if len(found) == 1 and (same := next(iter(found.values()))).holds(widgets):
            return same.unlink
        if found:
            raise ValueError("a map can be in one linked group only; link all of them in one call")
        for widget in widgets:
            _groups[widget] = group

    try:
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
    except BaseException:
        with _lock:
            _release(group)
        raise

    for member in members:

        def on_view(view: dict, member=member) -> None:
            _forward(group, member, view)

        member.callback = on_view
        widget = member.ref()
        if widget is not None:
            widget.on_view(on_view)

    return unlink
