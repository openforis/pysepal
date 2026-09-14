"""One name for one concept: scope_id."""

import inspect

from pysepal.solara import runtime_context, session_manager
from pysepal.solara.notifications import bus
from pysepal.solara.session_info import SessionInfo


def test_runtime_context_exposes_both_resolvers():
    assert runtime_context.PROCESS_SCOPE == "process"
    assert callable(runtime_context.resolve_scope_id)
    assert callable(runtime_context.current_scope_id)
    assert not hasattr(runtime_context, "get_current_runtime_id")


def test_session_manager_speaks_scope_id():
    assert not hasattr(session_manager.SessionManager, "get_kernel_id")
    for name in (
        "get_sepal_client",
        "get_session_info",
        "cleanup_session",
    ):
        params = inspect.signature(getattr(session_manager.SessionManager, name)).parameters
        assert "kernel_id" not in params
        assert "scope_id" in params


def test_session_info_payload_key_is_scope_id():
    assert SessionInfo(scope_id="kernel-a").scope_id == "kernel-a"
    assert not hasattr(session_manager, "empty_session_info")


def test_bus_has_no_private_resolver():
    assert not hasattr(bus, "_get_kernel_id")
