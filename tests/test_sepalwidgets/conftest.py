"""Shared fixtures for the sepalwidgets test-suite."""

import pytest

from pysepal._ui_state import _registry


@pytest.fixture(autouse=True)
def _clear_scopes():
    """Keep scope-keyed state from leaking between tests.

    Two files here fake scope ids and set the locale, and one writes into the
    real process fallback that every unpatched test reads from. Clearing the
    registry is how ``tests/test_solara/`` and ``tests/test_i18n/`` already solve
    this.
    """
    _registry.clear()
    yield
    _registry.clear()
