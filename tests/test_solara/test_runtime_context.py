"""Tests for pysepal Solara runtime scope identity resolution.

``resolve_scope_id`` is a thin adapter over ``solara.scope.get_kernel_id``
(Solara's own Solara-server-or-IPython resolver), so these tests cover the
adapter contract: pass-through of the resolved id and translation of Solara's
failure modes into ``UnsupportedSolaraRuntimeError``.
"""

import os
from unittest.mock import patch

import pytest
from traitlets.config import Config

from pysepal.solara.runtime_context import (
    PROCESS_SCOPE,
    UnsupportedSolaraRuntimeError,
    current_scope_id,
    resolve_scope_id,
)


def test_resolve_scope_id_delegates_to_solara_scope():
    with patch("solara.scope.get_kernel_id", return_value="kernel-uuid") as get_kernel_id:
        assert resolve_scope_id() == "kernel-uuid"
        get_kernel_id.assert_called_once_with(ipython_fallback=True)


def test_resolve_scope_id_raises_typed_error_when_no_runtime():
    with patch("solara.scope.get_kernel_id", side_effect=RuntimeError("Not in a kernel")):
        with pytest.raises(UnsupportedSolaraRuntimeError, match="No supported"):
            resolve_scope_id()


def test_resolve_scope_id_raises_typed_error_on_unparseable_connection_file():
    # solara.scope.get_kernel_id() regex-parses the ipykernel connection filename
    # and raises AttributeError when it does not match (e.g. non-standard kernel
    # launchers); degrade cleanly to "unsupported" instead of crashing render.
    err = AttributeError("'NoneType' object has no attribute 'group'")
    with patch("solara.scope.get_kernel_id", side_effect=err):
        with pytest.raises(UnsupportedSolaraRuntimeError, match="No supported"):
            resolve_scope_id()


def test_resolve_scope_id_raises_typed_error_when_solaras_lazy_imports_fail():
    # solara.scope.get_kernel_id imports solara.server.kernel_context and IPython
    # inside the call; pysepal declares neither, so a thinned dependency tree
    # must degrade to "unsupported" rather than crash render.
    with patch("solara.scope.get_kernel_id", side_effect=ImportError("No module named 'IPython'")):
        with pytest.raises(UnsupportedSolaraRuntimeError, match="No supported"):
            resolve_scope_id()


def test_current_scope_id_falls_back_to_the_process_scope():
    """Scripts and pytest have no per-connection runtime; state still needs a key."""
    with patch("solara.scope.get_kernel_id", side_effect=RuntimeError("Not in a kernel")):
        assert current_scope_id() == PROCESS_SCOPE


class _FakeKernel:
    def __init__(self, config):
        self.config = config


class _FakeIPython:
    """Enough of an IPython shell for solara's ``ipython_fallback`` branch."""

    def __init__(self, config):
        self.kernel = _FakeKernel(config)


@pytest.mark.parametrize(
    ("name", "config"),
    [
        # traitlets auto-vivifies the missing key into a LazyConfigValue, so
        # solara's re.search() gets a non-string and raises TypeError.
        ("traitlets_config", Config()),
        # A mapping that does not auto-vivify raises KeyError instead.
        ("plain_dict", {"IPKernelApp": {}}),
    ],
)
def test_a_kernel_without_a_connection_file_is_an_unsupported_runtime(name, config):
    """Drive solara's real resolver, not a mocked exception.

    An embedded or in-process kernel presents ``ipython.kernel`` with no
    standard connection file. Mocking the exception type is what let this
    escape once already, so build the real config shapes and let
    ``solara.scope.get_kernel_id`` fail on its own terms.
    """
    with patch("IPython.get_ipython", return_value=_FakeIPython(config)):
        with pytest.raises(UnsupportedSolaraRuntimeError, match="No supported"):
            resolve_scope_id()


@pytest.mark.parametrize(
    ("name", "config"),
    [
        ("traitlets_config", Config()),
        ("plain_dict", {"IPKernelApp": {}}),
    ],
)
def test_current_scope_id_is_total_against_a_broken_kernel(name, config):
    """``current_scope_id`` promises a scope id *always*; a broken kernel is no exception.

    ``use_notifications`` and ``notify`` degrade to a no-op when no bus can be
    resolved, but only if resolution fails cleanly instead of raising through
    the render path.
    """
    with patch("IPython.get_ipython", return_value=_FakeIPython(config)):
        assert current_scope_id() == PROCESS_SCOPE


_KERNEL_PER_CONTEXT = """
import asyncio
from uuid import uuid4
import ipykernel.kernelbase
import solara.server.app  # imports the patch module in a working order
import solara.server.patch as patch
from solara.server.kernel import Kernel
from solara.server.kernel_context import VirtualKernelContext
from pysepal_map.widget import _current_kernel

ipykernel.kernelbase.Kernel.instance = classmethod(patch.kernel_instance_dispatch)
ipykernel.kernelbase.Kernel.initialized = classmethod(patch.kernel_initialized_dispatch)
loop = asyncio.new_event_loop()
seen = []
for _ in range(2):
    context = VirtualKernelContext(id=uuid4().hex, session_id="t", kernel=Kernel(), event_loop=loop)
    with context:
        seen.append(_current_kernel() is context.kernel)
print(seen)
"""


def test_each_solara_kernel_context_has_its_own_map_kernel(tmp_path):
    # pysepal-map scopes its links by ipykernel's Kernel.instance(), which only
    # Solara's patch makes per kernel context. This installs Solara's own
    # dispatchers in a fresh interpreter, so it fails if they are renamed or
    # stop telling contexts apart.
    import subprocess
    import sys

    run = subprocess.run(
        [sys.executable, "-c", _KERNEL_PER_CONTEXT],
        capture_output=True,
        text=True,
        env={**os.environ, "IPYTHONDIR": str(tmp_path)},
    )

    assert run.returncode == 0, run.stderr[-800:]
    assert run.stdout.strip().splitlines()[-1] == "[True, True]"
