"""Shared fixtures for the sepalwidgets test-suite."""

import pytest

from pysepal.solara.theme import _theme_store
from tests._kernel_contexts import kernel_contexts  # noqa: F401


@pytest.fixture(autouse=True)
def _clear_scopes():
    """Reset UI registries and the locale's process fallback between tests."""
    from pysepal.i18n import set_locale

    _theme_store.clear()
    set_locale("en")
    yield
    _theme_store.clear()
    set_locale("en")
