"""The scope primitives live above pysepal.solara; the old paths still work.

Importing them used to execute ``pysepal/solara/__init__.py``, which pulls in
session management and notifications. ``pysepal.i18n`` needs a runtime scope
and nothing else, so the implementation moved to private top-level modules and
the old paths became re-export shims.
"""

import subprocess
import sys
from pathlib import Path

import pysepal
import pysepal._runtime_context as runtime_context
import pysepal._scope_registry as scope_registry
from pysepal.solara import runtime_context as solara_runtime_context
from pysepal.solara import scope_registry as solara_scope_registry

PROBE = "import sys, pysepal._scope_registry; print('pysepal.solara' in sys.modules)"


def test_the_scope_layer_does_not_import_pysepal_solara():
    # cwd pinned to the repo root: -c puts cwd on sys.path first, and pysepal
    # is installed editable against a different checkout, so an inherited cwd
    # elsewhere would probe that checkout instead of this one.
    probe = subprocess.run(
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        check=True,
        cwd=Path(pysepal.__file__).parent.parent,
    )
    assert probe.stdout.strip().splitlines()[-1] == "False", probe.stderr


def test_the_old_runtime_context_path_re_exports_the_same_objects():
    assert solara_runtime_context.current_scope_id is runtime_context.current_scope_id
    assert solara_runtime_context.resolve_scope_id is runtime_context.resolve_scope_id
    assert solara_runtime_context.PROCESS_SCOPE is runtime_context.PROCESS_SCOPE
    assert (
        solara_runtime_context.UnsupportedSolaraRuntimeError
        is runtime_context.UnsupportedSolaraRuntimeError
    )


def test_the_old_registry_path_re_exports_the_same_objects():
    assert solara_scope_registry.ScopeRegistry is scope_registry.ScopeRegistry
    assert solara_scope_registry.current_scope_id is runtime_context.current_scope_id
