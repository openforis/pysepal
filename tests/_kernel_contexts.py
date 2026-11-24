"""A real Solara kernel context, without running a Solara server.

State that solara isolates per virtual kernel -- the locale reactive, the
theme store -- can only be tested against real contexts: a fake scope id
proves nothing about storage solara keys by its own kernel context.
"""

from collections import UserDict

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

    # A Solara server keys ipywidgets' registry by kernel (solara.server.patch);
    # without that, a context's close() closes every kernel's widgets.
    import ipywidgets.widgets.widget as widget_module
    from solara.server.kernel_context import get_current_context, has_current_context

    class PerKernelWidgets(UserDict):
        def __init__(self, unscoped):
            self.unscoped = unscoped

        @property
        def data(self):
            return get_current_context().widgets if has_current_context() else self.unscoped

    monkeypatch.setattr(widget_module, "_instances", PerKernelWidgets(widget_module._instances))

    # Likewise for ipyvue's .vue templates: a template built in a context closes with it.
    import ipyvue  # noqa: F401

    template_module = sys.modules["ipyvue.Template"]

    class PerKernelTemplates(UserDict):
        def __init__(self, unscoped):
            self.unscoped = unscoped

        @property
        def data(self):
            return get_current_context().templates if has_current_context() else self.unscoped

    monkeypatch.setattr(
        template_module, "template_registry", PerKernelTemplates(template_module.template_registry)
    )
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


@pytest.fixture
def kernel_comms(monkeypatch):
    """Give each widget's comm the kernel of the context it was built in, as a Solara server does.

    Off any context, as on a pool worker, the comm gets no kernel: the widget never reaches
    the browser.
    """
    import ipykernel.kernelbase
    from solara.server.kernel_context import get_current_context, has_current_context

    kernel_class = ipykernel.kernelbase.Kernel
    original_instance = kernel_class.instance.__func__
    original_initialized = kernel_class.initialized.__func__

    def instance(cls, *args, **kwargs):
        if has_current_context():
            return get_current_context().kernel
        return original_instance(cls, *args, **kwargs)

    def initialized(cls):
        return has_current_context() or original_initialized(cls)

    monkeypatch.setattr(kernel_class, "instance", classmethod(instance))
    monkeypatch.setattr(kernel_class, "initialized", classmethod(initialized))
