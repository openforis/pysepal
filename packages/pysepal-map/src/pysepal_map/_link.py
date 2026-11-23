"""Keep several maps on one camera."""

import threading
import uuid
import weakref
from collections.abc import Callable

from .widget import MapWidget

_lock = threading.Lock()


class _Group:
    def __init__(self, widgets: tuple[MapWidget, ...]) -> None:
        self.id = uuid.uuid4().hex
        self.refs = [weakref.ref(w) for w in widgets]
        self.active = True
        self.unlink: Callable[[], None] = lambda: None

    def holds(self, widgets: tuple[MapWidget, ...]) -> bool:
        """Whether ``widgets`` are exactly its members still alive, in any order."""
        alive = {id(w) for r in self.refs if (w := r()) is not None}
        return alive == {id(w) for w in widgets}


# The group of each linked widget, held weakly.
_groups: "weakref.WeakKeyDictionary[MapWidget, _Group]" = weakref.WeakKeyDictionary()


def _align(widgets: tuple[MapWidget, ...]) -> None:
    """Request the first map's view, or its pending request, on the others."""
    first = widgets[0]
    with first._lock:
        view = first.view
        pending = {k: v for k, v in first.view_request.items() if k != "seq"}
    for widget in widgets[1:]:
        if view:
            widget.set_center(*view["center"], view["zoom"])
        else:
            widget._request(dict(pending))


def link_views(*widgets: MapWidget) -> Callable[[], None]:
    """Keep the cameras of two or more maps together; return the function that unlinks them.

    The others take the first map's view now. From then on the browser
    keeps them together: every move of one map, by a user or a request,
    moves the others at once. A map holds one group at most, and the group
    holds no strong reference to its maps. Linking exactly the maps of a
    live group again, in any order, changes nothing and returns that group's
    unlink function; any other overlap raises.
    """
    if len(widgets) < 2:
        raise ValueError("link_views needs at least two maps")
    if len({id(w) for w in widgets}) != len(widgets):
        raise ValueError("link_views got the same map twice")
    group = _Group(widgets)

    def unlink() -> None:
        # Only the first call acts: a later one must not free maps another group took.
        with _lock:
            if not group.active:
                return
            group.active = False
            for ref in group.refs:
                widget = ref()
                if widget is not None and _groups.get(widget) is group:
                    del _groups[widget]
                    widget.set_trait("_link", {})

    group.unlink = unlink
    # Held throughout, so an unlink or another link cannot interleave its writes.
    with _lock:
        found = {id(g): g for w in widgets if (g := _groups.get(w)) is not None}
        if len(found) == 1 and (same := next(iter(found.values()))).holds(widgets):
            return same.unlink
        if found:
            raise ValueError("a map can be in one linked group only; link all of them in one call")
        _align(widgets)
        for widget in widgets:
            # Under the map's lock, so no request slips between the seq and the link.
            with widget._lock:
                link = {"group": group.id, "seq": widget.view_request["seq"]}
                widget.set_trait("_link", link)
            _groups[widget] = group
    return unlink
