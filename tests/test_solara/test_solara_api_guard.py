"""Two private solara APIs are load-bearing; their loss must be loud at import.

``solara.scope.get_kernel_id`` and ``solara._using_solara_server`` are not part
of solara's public surface, so a rename can land in a patch release. Losing the
first one is the dangerous case: ``resolve_scope_id`` would raise
``UnsupportedSolaraRuntimeError``, ``current_scope_id`` would answer
``PROCESS_SCOPE``, and every connection in a multi-user container would share
one scope for theme, UI state and the notification bus.

Each module is re-executed into a *fresh* module object rather than reloaded,
so a failing import cannot leave the live ``pysepal.solara`` half-built.
"""

import importlib.util

import pytest
import solara
import solara.scope


def exec_fresh(module_name: str) -> None:
    """Execute a module's source again, into a throwaway module object.

    Args:
        module_name: Dotted name of an already-importable module.

    Raises:
        ImportError: The module's own import-time guard rejected the
            environment -- which is what these tests assert.
    """
    spec = importlib.util.find_spec(module_name)
    assert spec is not None and spec.loader is not None, module_name
    spec.loader.exec_module(importlib.util.module_from_spec(spec))


@pytest.mark.parametrize(
    ("module_name", "owner", "symbol"),
    [
        ("pysepal._runtime_context", solara.scope, "get_kernel_id"),
        ("pysepal.solara._topology", solara, "_using_solara_server"),
    ],
)
def test_a_missing_solara_symbol_fails_the_import(module_name, owner, symbol, monkeypatch):
    monkeypatch.delattr(owner, symbol)
    with pytest.raises(ImportError, match=symbol):
        exec_fresh(module_name)


@pytest.mark.parametrize(
    "module_name",
    ["pysepal._runtime_context", "pysepal.solara._topology"],
)
def test_the_guard_passes_against_the_installed_solara(module_name):
    """Otherwise the tests above would pass on any module that raises anything."""
    exec_fresh(module_name)
