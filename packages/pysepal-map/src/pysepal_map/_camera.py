"""Validate the camera requests and the insets before they reach the views."""

from __future__ import annotations

import numbers

from .state import _finite

#: The map's maximum zoom.
MAX_ZOOM = 24
#: The sides of the map element that other UI can cover, in ``insets`` order.
INSET_SIDES = ("left", "right", "top", "bottom")


def _pixels(name: str, value) -> int:
    """``value`` as a whole, non-negative number of CSS pixels; never a bool."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 0:
        raise ValueError(f"{name} must be a whole number of pixels, got {value!r}")
    return int(value)


def _latitude(name: str, value) -> float:
    if not -90 <= _finite(name, value) <= 90:
        raise ValueError(f"{name} must be in [-90, 90], got {value!r}")
    return float(value)


def _zoom(name: str, value) -> float:
    if not 0 <= _finite(name, value) <= MAX_ZOOM:
        raise ValueError(f"{name} must be in [0, {MAX_ZOOM}], got {value!r}")
    return float(value)


def _animated(request: dict, animate: bool) -> dict:
    """``request``, with ``animate: True`` when it flies; a jump carries no key."""
    return {**request, "animate": True} if animate else request


def _center_request(lng, lat, zoom, animate: bool = False) -> dict:
    center = [float(_finite("lng", lng)), _latitude("lat", lat)]
    request = {"center": center, "zoom": None if zoom is None else _zoom("zoom", zoom)}
    return _animated(request, animate)


def _bounds_request(bounds, padding, max_zoom, animate: bool = False) -> dict:
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
    request = {
        "bounds": box,
        "padding": _pixels("padding", padding),
        "max_zoom": None if max_zoom is None else _zoom("max_zoom", max_zoom),
    }
    return _animated(request, animate)


def _insets(left, right, top, bottom) -> dict[str, int]:
    """The four insets as plain ints, in ``INSET_SIDES`` order."""
    sides = dict(zip(INSET_SIDES, (left, right, top, bottom)))
    return {side: _pixels(side, value) for side, value in sides.items()}
