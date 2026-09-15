"""Structural checks that every demo app stays runnable under both runtimes.

The demos under ``demo_apps/`` are the worked references the guides point at, so
the shape they share is load-bearing: UI in a plain component, a ``Page``
entrypoint for Solara, and a three-line ``ui.ipynb`` for Voila. These tests are
what stop a new demo from shipping without one of them.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

DEMO_ROOT = Path(__file__).resolve().parents[2] / "demo_apps"
DEMO_DIRS = sorted(path.parent for path in DEMO_ROOT.glob("*/app.py"))
DEMO_IDS = [path.name for path in DEMO_DIRS]

MAP_APP = DEMO_ROOT / "solara_map_app"
AOI_GEE_APP = DEMO_ROOT / "solara_aoi_gee_app"


def _decorator_name(decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Call):
        return _decorator_name(decorator.func)
    if isinstance(decorator, ast.Attribute):
        return decorator.attr
    if isinstance(decorator, ast.Name):
        return decorator.id
    return ""


def _functions(path: Path) -> dict:
    return {
        node.name: node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _notebook_source(demo: Path) -> str:
    notebook = json.loads((demo / "ui.ipynb").read_text())
    assert len(notebook["cells"]) == 1, "the Voila entrypoint is a single cell"
    cell = notebook["cells"][0]
    assert cell["cell_type"] == "code"
    return "".join(cell["source"])


def _shared_component_name(demo: Path) -> str:
    """The component ``ui.ipynb`` displays -- the demo's own name for its UI."""
    imports = [
        alias.name
        for node in ast.walk(ast.parse(_notebook_source(demo)))
        if isinstance(node, ast.ImportFrom) and node.module == "app"
        for alias in node.names
    ]
    assert len(imports) == 1, "the notebook imports exactly one component from app"
    return imports[0]


def test_demos_are_discovered():
    """Everything below is parametrized on the glob, so an empty one must fail here."""
    assert DEMO_DIRS, f"no demo found under {DEMO_ROOT}"
    assert MAP_APP in DEMO_DIRS


@pytest.mark.parametrize("demo", DEMO_DIRS, ids=DEMO_IDS)
def test_demo_has_both_runtime_entrypoints(demo: Path):
    """Neither runtime may be left behind: ``app.py`` for Solara, ``ui.ipynb`` for Voila."""
    assert (demo / "app.py").is_file()
    assert (demo / "ui.ipynb").is_file()


@pytest.mark.parametrize("demo", DEMO_DIRS, ids=DEMO_IDS)
def test_page_only_wraps_the_shared_component(demo: Path):
    """``Page`` is a thin Solara entrypoint; the UI itself is reusable by Voila."""
    functions = _functions(demo / "app.py")
    shared_name = _shared_component_name(demo)

    assert shared_name in functions, f"{demo.name}/ui.ipynb imports a missing component"
    shared = functions[shared_name]
    page = functions["Page"]

    assert "component" in [_decorator_name(item) for item in shared.decorator_list]
    assert "component" in [_decorator_name(item) for item in page.decorator_list]
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == shared_name
        for statement in page.body
        for node in ast.walk(statement)
    ), f"{demo.name}/app.py defines Page without delegating to {shared_name}"


@pytest.mark.parametrize("demo", DEMO_DIRS, ids=DEMO_IDS)
def test_voila_notebook_only_imports_and_displays(demo: Path):
    """The notebook stays a runtime entrypoint instead of a second copy of the UI."""
    source = _notebook_source(demo)
    shared_name = _shared_component_name(demo)

    assert source == f"from app import {shared_name}\n\ndisplay({shared_name}())\n"


@pytest.mark.parametrize("demo", DEMO_DIRS, ids=DEMO_IDS)
def test_demo_never_schedules_gee_work_on_a_second_event_loop(demo: Path):
    """Every async button must go through solara's loop, not GEEInterface's own.

    ``GEEInterface.create_task`` hands the coroutine to a private event loop running
    in its own thread, while ``solara.lab.use_task`` runs it on solara's. Mixing both
    in one app makes two loops share the single ``httpx.AsyncClient(http2=True)``
    cached on the eeclient session, and its asyncio primitives bind to whichever loop
    touched them first -- so a concurrent call from the other one dies mid-request.
    """
    offenders = [
        path.relative_to(demo)
        for path in sorted(demo.rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_task"
    ]

    assert offenders == []


def test_map_app_module_is_only_the_shell():
    """Logic belongs under ``component/``; ``app.py`` only opens and lays out the app.

    Guards the module boundaries against the map demo drifting back into one file.
    """
    defined = {
        node.name
        for node in ast.parse((MAP_APP / "app.py").read_text()).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    assert defined == {"on_kernel_start", "MapAppDemo", "Page"}


def test_map_app_page_authenticates():
    """Only the Solara page opens a SEPAL session -- the shared component must not."""
    functions = _functions(MAP_APP / "app.py")

    assert [_decorator_name(item) for item in functions["Page"].decorator_list] == [
        "component",
        "with_sepal_sessions",
    ]
    assert [_decorator_name(item) for item in functions["MapAppDemo"].decorator_list] == [
        "component"
    ]


def test_the_gee_aoi_demo_offers_what_a_spec_can_carry():
    """Its point is which methods survive being written down and read back.

    ASSET and DRAW are what the local demo cannot reach; SHAPE and POINTS persist
    a server-local pathname, which the next connection cannot resolve.
    """
    import importlib.util

    from pysepal.solara.components.aoi.aoi_view import resolve_methods

    spec = importlib.util.spec_from_file_location("_aoi_gee_demo", AOI_GEE_APP / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # map_ stands in for the demo's SepalMap: resolve_methods only tests it for None.
    offered = resolve_methods(module.METHODS, gee=True, map_=object())

    assert set(offered) == {"ADMIN0", "ADMIN1", "ADMIN2", "DRAW", "ASSET"}
