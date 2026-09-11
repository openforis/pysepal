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
    """Reset the reactive's process fallback between tests."""
    from pysepal.i18n import set_locale

    set_locale("en")
    yield
    set_locale("en")


@pytest.fixture
def kernel_contexts(monkeypatch, tmp_path):
    """Create and close real Solara kernel contexts without a server."""
    import asyncio
    import sys
    from uuid import uuid4

    monkeypatch.setenv("IPYTHONDIR", str(tmp_path / "ipython"))
    from solara.server.kernel import Kernel
    from solara.server.kernel_context import VirtualKernelContext

    monkeypatch.setattr(sys, "argv", ["solara"])
    contexts = []
    event_loop = asyncio.new_event_loop()

    def create():
        context = VirtualKernelContext(
            id=uuid4().hex, session_id="test", kernel=Kernel(), event_loop=event_loop
        )
        contexts.append(context)
        return context

    yield create
    for context in reversed(contexts):
        context.close()
    event_loop.close()
