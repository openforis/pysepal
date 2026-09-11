"""Shared fixtures for the Solara test-suite."""

import pytest

from pysepal.solara import dev_auth as _dev_auth
from pysepal.solara import ui_state
from pysepal.solara.session_manager import SessionManager


@pytest.fixture
def empty_file_browser(monkeypatch):
    """Keep picker tests from listing the developer's home directory."""
    from pysepal.sepalwidgets import file_input

    monkeypatch.setattr(
        file_input,
        "get_local_files",
        lambda folder, **kwargs: file_input.ListDirectoryResponse(path=str(folder), files=[]),
    )


@pytest.fixture(autouse=True)
def _clean_ui_state():
    """Keep the process-wide UI-state registry from leaking across tests."""
    from pysepal.i18n import set_locale

    ui_state._registry.clear()
    set_locale("en")
    yield
    ui_state._registry.clear()
    set_locale("en")


@pytest.fixture(autouse=True)
def _reset_session_manager():
    """Give every test a pristine SessionManager singleton.

    Dropping the instance is enough: its session registry and its tombstone
    deque are both per-instance, so neither can leak into the next test.

    Plain assignment on purpose: ``monkeypatch.setattr`` would restore the
    stale singleton at teardown and leak it into the rest of the suite.
    """
    SessionManager._instance = None
    yield
    SessionManager._instance = None


@pytest.fixture(autouse=True)
def _clean_dev_auth(monkeypatch):
    """Never let a developer's PYSEPAL_DEV_AUTH or a cached login reach a test."""
    monkeypatch.delenv("PYSEPAL_DEV_AUTH", raising=False)
    _dev_auth._reset_dev_auth_cache()
    yield
    _dev_auth._reset_dev_auth_cache()
