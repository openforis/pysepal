"""Test the build hook that bundles the JS widget."""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

HOOK = Path(__file__).parents[1] / "hatch_build.py"


@pytest.fixture
def hook_class(monkeypatch):
    """The hook class, on a stand-in for hatchling's base, which it only subclasses."""
    interface = types.ModuleType("hatchling.builders.hooks.plugin.interface")

    class BuildHookInterface:
        def __init__(self, root):
            self.root = root

    interface.BuildHookInterface = BuildHookInterface
    parents = ["hatchling", "hatchling.builders", "hatchling.builders.hooks"]
    for name in [*parents, "hatchling.builders.hooks.plugin"]:
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, interface.__name__, interface)
    spec = importlib.util.spec_from_file_location("hatch_build", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.JSBuildHook


def test_a_source_build_without_npm_says_what_it_needs(hook_class, tmp_path, monkeypatch):
    empty = tmp_path / "bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(RuntimeError, match="Node 22") as error:
        hook_class(str(tmp_path)).initialize("standard", {})
    assert "npm" in str(error.value)
    assert "wheels and sdists" in str(error.value)
