"""pysepal 5 removed the ipyvuetify 1 widget layer; what an old import gets instead.

Each check runs in a fresh interpreter, from the repo root: a test elsewhere
changes the working directory and never restores it, and ``python -c`` imports
pysepal from its working directory.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Everything an app built on the Solara layer imports.
SOLARA_SURFACE = [
    "pysepal",
    "pysepal.solara",
    "pysepal.solara.components.map_app",
    "pysepal.solara.components.locale_select",
    "pysepal.solara.components.inputs",
    "pysepal.solara.components.aoi",
    "pysepal.solara.components.export",
    "pysepal.solara.components.task_button",
    "pysepal.solara.components.legend",
    "pysepal.solara.notifications",
    "pysepal.mapping",
    "pysepal.aoi",
    "pysepal.planetapi",
]


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )


def test_sepalwidgets_import_says_what_to_do():
    result = _run("import pysepal.sepalwidgets")

    assert result.returncode != 0
    assert "ImportError: pysepal.sepalwidgets was removed in pysepal 5.0" in result.stderr
    assert 'pin "pysepal<5"' in result.stderr


@pytest.mark.parametrize(
    "module,name",
    [
        ("pysepal.aoi", "AoiView"),
        ("pysepal.aoi", "AoiTile"),
        ("pysepal.planetapi", "PlanetView"),
        ("pysepal.mapping", "AoiControl"),
    ],
)
def test_removed_widget_names_say_what_to_do(module, name):
    import importlib

    package = importlib.import_module(module)
    with pytest.raises(AttributeError, match="removed in pysepal 5.0"):
        getattr(package, name)


def test_unknown_names_still_raise_the_usual_error():
    import pysepal.aoi

    with pytest.raises(AttributeError, match="has no attribute 'nope'"):
        pysepal.aoi.nope  # noqa: B018


def test_the_solara_surface_imports():
    imports = "; ".join(f"import {name}" for name in SOLARA_SURFACE)
    result = _run(f"import sys; {imports}")
    assert result.returncode == 0, result.stderr


def test_models_import_without_widgets():
    result = _run("from pysepal.aoi import AoiModel; from pysepal.planetapi import PlanetModel")
    assert result.returncode == 0, result.stderr
