"""Session status is a read-only value object, not a mutable dict."""

import dataclasses
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from pysepal import _runtime_context as runtime_context
from pysepal.solara import ui_state, utils
from pysepal.solara.runtime_context import PROCESS_SCOPE, UnsupportedSolaraRuntimeError
from pysepal.solara.session_info import SessionInfo, SessionsOverview
from pysepal.solara.session_manager import SessionManager
from pysepal.solara.theme import ThemeState


@contextmanager
def scope(scope_id: str):
    """Pin the runtime's scope id for every ``current_scope_id`` caller.

    Patching upstream on ``resolve_scope_id`` -- not on any module's copy of
    ``current_scope_id`` -- reaches those callers regardless of import style:
    every ``current_scope_id()`` is the one function object defined in
    ``runtime_context``, so its own lookup of ``resolve_scope_id`` always runs
    against ``runtime_context``'s globals, wherever the call came from.

    It does NOT reach callers that imported ``resolve_scope_id`` directly --
    notably ``SessionManager.get_scope_id`` -- because those resolve the bare
    name against their own module globals. Patch
    ``pysepal.solara.session_manager.resolve_scope_id`` for those.
    """
    with patch.object(runtime_context, "resolve_scope_id", return_value=scope_id):
        yield


def test_session_info_is_frozen():
    info = SessionInfo(scope_id="kernel-a")
    with pytest.raises(dataclasses.FrozenInstanceError):
        info.username = "mallory"


def test_session_info_carries_no_ui_state_fact():
    """has_theme_state was a UI-scope fact inside an authentication payload."""
    names = {f.name for f in dataclasses.fields(SessionInfo)}
    assert "has_theme_state" not in names
    assert names == {
        "scope_id",
        "username",
        "has_gee_interface",
        "has_sepal_client",
        "has_drive_interface",
        "active_module_name",
        "module_names",
        "session_ready",
    }


def test_current_session_info_reports_the_real_scope_without_a_manager():
    """Scope id is a runtime fact; it must not depend on a session existing."""
    assert SessionManager.is_initialized() is False
    with scope("kernel-a"):
        info = utils.get_current_session_info()
    assert info.scope_id == "kernel-a"
    assert info.session_ready is False


def test_current_session_info_does_not_construct_the_manager():
    assert SessionManager._instance is None
    utils.get_current_session_info()
    assert SessionManager._instance is None


def test_current_session_info_uses_the_process_scope_in_a_script():
    with scope(PROCESS_SCOPE):
        assert utils.get_current_session_info().scope_id == PROCESS_SCOPE


def test_touching_the_theme_does_not_change_the_session_payload():
    with scope("kernel-a"):
        ui_state.get_scoped_state("theme_state", ThemeState)
        info = utils.get_current_session_info()
    assert info.session_ready is False
    assert ui_state.has_scoped_state("theme_state", "kernel-a") is True


def test_overview_derives_its_counts():
    overview = SessionsOverview(
        sessions=(
            SessionInfo(scope_id="a", session_ready=True),
            SessionInfo(scope_id="b"),
        )
    )
    assert overview.total_sessions == 2
    assert overview.ready_sessions == 1


def test_overview_hands_out_no_mutable_session_dicts():
    """The debt was a live reference into the private session dict, not the type.

    ``list_sessions`` is already gone (superseded by ``session_scope_ids``), so
    asserting its absence alone would be vacuous; pin instead that
    ``module_names`` is a snapshot, not a live view onto the session's
    ``sepal_clients`` dict -- mutating that dict after the fact must not
    retroactively change an already-built SessionInfo.
    """
    manager = SessionManager()
    live_session = {
        "username": "alice",
        "gee_interface": object(),
        "sepal_clients": {"route_a": object()},
    }
    manager._registry.set(live_session, "kernel-a")
    overview = utils.get_sessions_overview()
    assert all(isinstance(s, SessionInfo) for s in overview.sessions)

    live_session["sepal_clients"]["route_b"] = object()
    assert overview.sessions[0].module_names == ("route_a",)


def test_the_overview_still_shows_the_process_session_with_real_data():
    """The overview enumerates the registry's own keys; it is not a caller-supplied scope.

    ``get_session_info(PROCESS_SCOPE)`` refuses a *caller-supplied* reserved
    scope (see the ``get_session_info`` docstring and
    :meth:`SessionManager.get_sepal_client`'s equivalent guard) -- but under
    PROCESS/DEV_AUTH topology the process session is the process's only
    session, and ``session_scope_ids()`` legitimately includes
    ``PROCESS_SCOPE`` once it exists (pinned by
    ``test_process_session.py::test_the_process_session_is_keyed_at_the_process_scope``).
    The overview must still show it with real data, not a blanked row.
    """
    manager = SessionManager()
    manager._registry.set(
        {
            "username": "devauth-operator",
            "gee_interface": object(),
            "sepal_clients": {"secret_module": object()},
            "active_module_name": "secret_module",
        },
        scope_id=PROCESS_SCOPE,
    )

    overview = utils.get_sessions_overview()

    assert [s.scope_id for s in overview.sessions] == [PROCESS_SCOPE]
    process_info = overview.sessions[0]
    assert process_info.username == "devauth-operator"
    assert process_info.session_ready is True
    assert process_info.module_names == ("secret_module",)


def test_scope_less_caller_does_not_see_the_process_session():
    """An unresolvable runtime must not read the shared process/dev-auth session.

    A background export task or a callback on GEEInterface's private loop has
    no per-connection scope to resolve, but the process/dev-auth session it
    could easily land on belongs to a different identity. Falling back to
    PROCESS_SCOPE and then reading it would leak that identity's username,
    module set and readiness to a caller that isn't it -- the same door
    :meth:`SessionManager.get_sepal_client` already refuses for its
    ``scope_id`` parameter.
    """
    manager = SessionManager()
    manager._registry.set(
        {
            "username": "devauth-operator",
            "gee_interface": object(),
            "sepal_clients": {"secret_module": object()},
            "drive_interface": object(),
            "active_module_name": "secret_module",
        },
        PROCESS_SCOPE,
    )

    err = UnsupportedSolaraRuntimeError("no runtime")
    with patch.object(SessionManager, "get_scope_id", side_effect=err):
        info = manager.get_session_info()

    assert info.scope_id == PROCESS_SCOPE
    assert info.username is None
    assert info.session_ready is False
    assert info.has_gee_interface is False
    assert info.has_sepal_client is False
    assert info.has_drive_interface is False
    assert info.module_names == ()
    assert info.active_module_name is None
