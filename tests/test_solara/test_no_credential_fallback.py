"""The process-global credential fallbacks are gone, and must stay gone.

In an app-launcher multi-user container ``~/.config/earthengine/credentials``
holds the *platform* GEE service-account key -- ``ee.Initialize()`` needs it
there -- and that is the path ``eeclient.providers.resolve_default_provider``
reads. Any fallback that reaches it from a per-connection runtime silently
collapses every user of the container onto one identity.
"""

from unittest.mock import patch

import pytest

from pysepal.solara import session_manager as sm
from pysepal.solara import utils
from pysepal.solara._topology import SessionPlan, SessionSource
from pysepal.solara.errors import SepalSessionError
from pysepal.solara.session_manager import SessionManager

_PER_CONNECTION = SessionPlan(SessionSource.PER_CONNECTION, "test")


def test_the_fallback_symbols_no_longer_exist():
    assert not hasattr(utils, "_get_fallback_gee_interface")
    assert not hasattr(utils, "_get_fallback_drive_interface")
    assert not hasattr(utils, "_fallback_gee_interface")
    assert not hasattr(utils, "_fallback_drive_interface")


def test_can_create_sessions_is_gone():
    """Header presence must never decide a credential source."""
    assert not hasattr(sm, "can_create_sessions")
    assert "can_create_sessions" not in sm.__all__


def test_a_per_connection_runtime_never_resolves_process_credentials(monkeypatch):
    """The negative control for R2, and the reason this whole chunk exists."""
    import eeclient.providers as providers

    def _boom(*args, **kwargs):
        raise AssertionError("process credentials must never be resolved per-connection")

    monkeypatch.setattr(providers, "resolve_default_provider", _boom)

    with (
        patch.object(sm, "_current_plan", return_value=_PER_CONNECTION),
        patch.object(SessionManager, "get_scope_id", return_value="kernel-a"),
    ):
        with pytest.raises(SepalSessionError, match="with_sepal_sessions"):
            utils.get_current_gee_interface()
        with pytest.raises(SepalSessionError, match="with_sepal_sessions"):
            utils.get_current_drive_interface()
        assert utils.get_current_sepal_client() is None


def test_a_per_connection_session_is_read_from_the_registry():
    manager = SessionManager()
    manager._registry.set(
        {
            "gee_interface": "the-users-gee",
            "drive_interface": "the-users-drive",
            "sepal_clients": {"route_a": "the-users-client"},
            "active_module_name": "route_a",
        },
        "kernel-a",
    )

    with (
        patch.object(sm, "_current_plan", return_value=_PER_CONNECTION),
        patch.object(SessionManager, "get_scope_id", return_value="kernel-a"),
    ):
        assert utils.get_current_gee_interface() == "the-users-gee"
        assert utils.get_current_drive_interface() == "the-users-drive"
        assert utils.get_current_sepal_client() == "the-users-client"


def test_a_per_connection_runtime_reads_files_from_the_users_workspace():
    """The container's disk is nobody's: files go through the user's client."""
    from pysepal.scripts.filesystem import SandboxFileSystem

    manager = SessionManager()
    manager._registry.set(
        {"sepal_clients": {"route_a": "the-users-client"}, "active_module_name": "route_a"},
        "kernel-a",
    )

    with (
        patch.object(sm, "_current_plan", return_value=_PER_CONNECTION),
        patch.object(SessionManager, "get_scope_id", return_value="kernel-a"),
    ):
        fs = utils.get_current_filesystem()

    assert isinstance(fs, SandboxFileSystem)
    assert fs.client == "the-users-client"


def test_a_per_connection_runtime_without_a_client_has_no_files():
    """No fallback to the container's disk."""
    with (
        patch.object(sm, "_current_plan", return_value=_PER_CONNECTION),
        patch.object(SessionManager, "get_scope_id", return_value="kernel-a"),
    ):
        with pytest.raises(SepalSessionError, match="with_sepal_sessions"):
            utils.get_current_filesystem()


def test_a_single_user_runtime_reads_its_own_disk():
    """Voila, a notebook or a SEPAL sandbox: the home folder is the user's."""
    from pathlib import Path, PurePosixPath

    from pysepal.scripts.filesystem import LocalFileSystem

    fs = utils.get_current_filesystem()

    assert isinstance(fs, LocalFileSystem)
    assert fs.root == PurePosixPath(Path.home())
