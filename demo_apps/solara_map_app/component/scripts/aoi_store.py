"""Persist the AOI selection between visits, per user.

``AoiView`` hands out two things. ``value`` is an ``AoiResult`` holding a
GeoDataFrame and an ``ee`` object -- what the app computes with, and not something
that can be written to disk. ``spec`` is an ``AoiSpec``: the small JSON record of
what the user picked. Saving the spec and passing it back is what lets a module
reopen on the AOI its user left behind, geometry and all.

Saving is a user action here, not a side effect of picking: the app holds the
spec in memory and only calls this module when the user asks for it. A module
that wants the selection to follow its user automatically can call ``save_spec``
from ``on_spec`` instead -- the storage does not care which.

One process serves many users on SEPAL, so the file is keyed by username. A single
shared path would let one user's AOI open in another user's session.
"""

import json
from pathlib import Path
from typing import Optional

from pysepal.scripts.scratch import scratch_root
from pysepal.solara import get_current_session_info
from pysepal.solara.components.aoi import AoiSpec


def saved_aoi_path() -> Path:
    """Return this user's AOI file.

    Returns:
        A path under the scratch root, keyed by username so sessions never
        collide. Falls back to ``anonymous`` before a session resolves.
    """
    info = get_current_session_info()
    username = getattr(info, "username", None) or "anonymous"
    return scratch_root() / f"aoi_spec_{username}.json"


def has_saved_spec() -> bool:
    """Whether this user has a stored selection.

    Returns:
        True when the file exists. Its contents are not validated here; a payload
        that turns out to be unreadable surfaces on ``load_spec``.
    """
    return saved_aoi_path().exists()


def save_spec(spec: AoiSpec) -> None:
    """Write the selection for this user.

    Args:
        spec: The selection to persist.
    """
    path = saved_aoi_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec.to_dict(), indent=2))


def load_spec() -> Optional[AoiSpec]:
    """Return this user's persisted selection, or None when there is none usable.

    A payload from a newer pysepal, or one corrupted by hand, counts as absent: a
    module that refuses to open because of a stale file is worse than one that
    opens empty.

    Returns:
        The restored spec, or None.
    """
    path = saved_aoi_path()
    if not path.exists():
        return None
    try:
        return AoiSpec.from_dict(json.loads(path.read_text()))
    except (ValueError, json.JSONDecodeError, OSError):
        return None
