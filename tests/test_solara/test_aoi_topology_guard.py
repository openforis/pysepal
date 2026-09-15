"""The AOI methods inherit the ``GEEInterface`` guard rather than binding the global ``ee``.

``process_admin`` already resolves an interface before ``su.init_ee()``, so a
per-connection runtime refuses it while the global ``ee`` is still untouched.
The other four methods went straight to ``su.init_ee()``, which reads
``~/.config/earthengine/credentials`` -- the platform service-account key in an
app-launcher container -- and never constructs the interface that carries the
refusal. These tests pin that every method now inherits it, and that it lands
*before* ``init_ee()``.

``AoiView`` is covered too: its mount effect called ``init_ee()`` before any
method was chosen, so the door opened whether or not the user ever selected one.
"""

import asyncio
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import reacton

import pysepal.solara.components.aoi.asset as asset_mod
from pysepal.scripts import utils as su
from pysepal.solara import session_manager as session_manager_module
from pysepal.solara._topology import SessionPlan, SessionSource
from pysepal.solara.components.aoi.aoi_view import AoiView
from pysepal.solara.components.aoi.asset import process_asset
from pysepal.solara.components.aoi.draw import process_draw
from pysepal.solara.components.aoi.points import process_points
from pysepal.solara.components.aoi.shape import process_shape
from pysepal.solara.errors import SepalSessionError

DATA = Path(__file__).resolve().parents[1] / "data" / "aoi_manual"
GEOJSON = DATA / "manual_polygons.geojson"
CSV = DATA / "manual_points.csv"

PER_CONNECTION = SessionPlan(SessionSource.PER_CONNECTION, "test")
PROCESS = SessionPlan(SessionSource.PROCESS, "test")

DRAWN = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
        }
    ],
}


@contextmanager
def _topology(plan):
    """Stage a runtime with only the Earth Engine calls stubbed.

    The connection is given a scope id but no session, which is the shape that
    matters: the refusal under test is "this connection has no session", not
    "this runtime has no scope".

    ``GEEInterface`` is deliberately left real: it is the thing carrying the
    guard, and a mock would make every test here pass whether the method
    resolves one or not.
    """
    init_ee = MagicMock()

    with (
        patch.object(session_manager_module, "_current_plan", return_value=plan),
        patch.object(
            session_manager_module.SessionManager,
            "get_scope_id",
            lambda _self: "kernel-test",
        ),
        patch.object(su, "init_ee", init_ee),
        patch.object(su, "geojson_to_ee", MagicMock()),
        patch.object(asset_mod, "ee", MagicMock()),
    ):
        yield SimpleNamespace(init_ee=init_ee)


def _render(component):
    """Render a component to completion and return its root widget."""

    async def _runner():
        root, rc = reacton.render(component, handle_error=False)
        rc.close()
        return root

    return asyncio.run(_runner())


# -- a per-connection runtime refuses every method, before init_ee ------------


def test_a_per_connection_runtime_refuses_process_draw():
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="platform service account"):
            process_draw(DRAWN, name="plot", gee=True)

    assert stubs.init_ee.call_count == 0


def test_a_per_connection_runtime_refuses_process_shape():
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="platform service account"):
            asyncio.run(process_shape(str(GEOJSON), gee=True))

    assert stubs.init_ee.call_count == 0


def test_a_per_connection_runtime_refuses_process_points():
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="platform service account"):
            asyncio.run(
                process_points(
                    str(CSV),
                    id_column="site_id",
                    lat_column="latitude",
                    lng_column="longitude",
                    gee=True,
                )
            )

    assert stubs.init_ee.call_count == 0


def test_a_per_connection_runtime_refuses_process_asset():
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="platform service account"):
            asyncio.run(process_asset("projects/x/assets/y", asset_type="TABLE"))

    assert stubs.init_ee.call_count == 0


def test_a_per_connection_runtime_refuses_the_aoi_view_on_mount():
    """The mount effect ran before any method was picked -- the earliest door.

    The view has no interface to be handed, so it resolves the connection's own
    and inherits that refusal, which names the fix an app author needs.
    """
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="with_sepal_sessions"):
            _render(AoiView(gee=True))

    assert stubs.init_ee.call_count == 0


# -- what must keep working ---------------------------------------------------


def test_an_explicit_interface_is_always_allowed():
    """The fix the error names: hand the method the session's own interface."""
    supplied = MagicMock()

    with _topology(PER_CONNECTION) as stubs:
        result = process_draw(DRAWN, name="plot", gee=True, gee_interface=supplied)

    assert result.method == "DRAW"
    assert stubs.init_ee.call_count == 1


def test_gee_false_never_reaches_earth_engine():
    with _topology(PER_CONNECTION) as stubs:
        result = process_draw(DRAWN, name="plot", gee=False)

    assert result.feature_collection is None
    assert stubs.init_ee.call_count == 0


def test_a_single_identity_runtime_keeps_the_default():
    """A notebook, a script, pytest or a SEPAL sandbox owns its machine credentials."""
    with _topology(PROCESS) as stubs:
        result = process_draw(DRAWN, name="plot", gee=True)

    assert result.method == "DRAW"
    assert stubs.init_ee.call_count == 1
