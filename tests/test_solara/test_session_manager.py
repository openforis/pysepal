"""Tests for Solara SessionManager runtime scoping."""

from unittest.mock import patch

import pytest

from pysepal.solara.runtime_context import PROCESS_SCOPE, UnsupportedSolaraRuntimeError
from pysepal.solara.session_manager import SessionManager


def test_session_manager_scope_id_uses_shared_runtime_resolver():
    manager = SessionManager()

    with patch(
        "pysepal.solara.session_manager.resolve_scope_id",
        return_value="voila:kernel-1",
    ):
        assert manager.get_scope_id() == "voila:kernel-1"


def test_the_session_registry_refuses_to_resolve_without_a_runtime():
    """A credential store must have no fallback scope.

    ``ScopeRegistry``'s default resolver answers ``PROCESS_SCOPE`` when no
    per-connection runtime exists -- right for UI state, a cross-user leak
    here: a call that forgot its ``scope_id`` would read and write one
    connection's credentials in the bucket every other runtime shares. The
    session registry is built with the raising resolver so that fails loudly.

    Pinned on the accessor rather than on ``resolve()`` beneath it: reading a
    session is the operation that must not silently land on the shared scope.
    """
    manager = SessionManager()

    with pytest.raises(UnsupportedSolaraRuntimeError):
        manager._registry.get()


def test_session_scope_ids_replaces_handing_out_the_session_dicts():
    """``list_sessions`` handed callers the live payloads, credentials included."""
    manager = SessionManager()
    manager._registry.set({"username": "alice", "gee_interface": object()}, "kernel-a")

    assert manager.session_scope_ids() == ("kernel-a",)
    assert not hasattr(manager, "list_sessions")


def test_per_connection_getters_raise_when_the_session_is_missing():
    """A Solara-server route without @with_sepal_sessions is a bug, not a fallback.

    The pre-v4 version of this test asked whether headers were present. Header
    presence no longer decides anything: topology does, before any header is
    read.
    """
    import pytest

    from pysepal.solara import session_manager as sm
    from pysepal.solara import utils
    from pysepal.solara._topology import SessionPlan, SessionSource
    from pysepal.solara.errors import SepalSessionError

    plan = SessionPlan(SessionSource.PER_CONNECTION, "test")
    with (
        patch.object(sm, "_current_plan", return_value=plan),
        patch.object(SessionManager, "get_scope_id", return_value="kernel-a"),
    ):
        for getter in (utils.get_current_gee_interface, utils.get_current_drive_interface):
            with pytest.raises(SepalSessionError, match="with_sepal_sessions"):
                getter()


def test_session_dict_no_longer_carries_theme_state():
    """Theme is UI state; it must not live behind an auth-gated session."""
    manager = SessionManager()
    manager._registry.set({"username": "alice", "gee_interface": object()}, "kernel-a")

    info = manager.get_session_info("kernel-a")

    assert "theme_state" not in manager._registry.get("kernel-a")
    assert info.session_ready is True


def test_explicit_process_scope_does_not_expose_the_process_session():
    manager = SessionManager()
    manager._registry.set(
        {
            "username": "devauth-operator",
            "sepal_clients": {"secret_module": object()},
            "active_module_name": "secret_module",
            "session_ready": True,
        },
        scope_id=PROCESS_SCOPE,
    )

    info = manager.get_session_info(scope_id=PROCESS_SCOPE)

    assert info.username is None
    assert info.module_names == ()
    assert info.session_ready is False
