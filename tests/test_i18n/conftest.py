"""Shared fixtures for the catalogue tests."""

import json

import pytest

import pysepal.i18n.binding as binding


@pytest.fixture
def build_catalog(tmp_path):
    """Return a factory that writes ``{locale: {file stem: document}}`` to disk.

    Each test gets its own ``tmp_path``, so the module-level catalogue caches
    cannot carry one test's content into the next.
    """

    def build(layout):
        folder = tmp_path / "messages"
        for code, files in layout.items():
            (folder / code).mkdir(parents=True)
            for stem, document in files.items():
                (folder / code / f"{stem}.json").write_text(json.dumps(document))
        return folder

    return build


@pytest.fixture(autouse=True)
def _clear_catalog_caches():
    """The catalogue caches are module-level and outlive a test otherwise."""
    for cache in (binding._PARSED, binding._COMPOSITE, binding._FACADES):
        cache.clear()
    yield
    for cache in (binding._PARSED, binding._COMPOSITE, binding._FACADES):
        cache.clear()


@pytest.fixture(autouse=True)
def _reset_locale():
    """Clear every scope, not just the one the test happens to be in.

    ``set_locale("en")`` is not enough: a test that monkeypatches
    ``current_scope_id`` leaves that named scope holding its locale, and
    monkeypatch tears down before this fixture's teardown runs, so by then the
    scope is unreachable. ``tests/test_solara/conftest.py`` clears the registry
    for the same reason.
    """
    from pysepal._ui_state import _registry

    _registry.clear()
    yield
    _registry.clear()
