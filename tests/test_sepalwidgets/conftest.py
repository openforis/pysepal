"""Shared fixtures for the sepalwidgets test-suite."""

import pytest

from pysepal._ui_state import _registry


@pytest.fixture(autouse=True)
def _clear_scopes():
    """Reset UI registries and the locale's process fallback between tests."""
    from pysepal.i18n import set_locale

    _registry.clear()
    set_locale("en")
    yield
    _registry.clear()
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
