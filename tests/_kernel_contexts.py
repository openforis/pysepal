"""A real Solara kernel context, without running a Solara server.

State that solara isolates per virtual kernel -- the locale reactive, the
theme store -- can only be tested against real contexts: a fake scope id
proves nothing about storage solara keys by its own kernel context.
"""

import pytest


@pytest.fixture
def kernel_contexts(monkeypatch, tmp_path):
    """Return a factory creating Solara kernel contexts, closed at teardown."""
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
