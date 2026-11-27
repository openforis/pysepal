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


@pytest.mark.parametrize(
    "module",
    [
        "pysepal.sepalwidgets",
        "pysepal.mapping.layers_control",
        "pysepal.mapping.draw_control",
        "pysepal.mapping.inspector_control",
        "pysepal.mapping.zoom_control",
        "pysepal.mapping.fullscreen_control",
        "pysepal.mapping.layer_state_control",
        "pysepal.mapping.menu_control",
        "pysepal.mapping.legend_control",
        "pysepal.mapping.aoi_control",
        "pysepal.mapping.layer",
        "pysepal.mapping.marker_cluster",
        "pysepal.mapping.geojson_utils",
    ],
)
def test_removed_module_import_says_what_to_do(module):
    result = _run(f"import {module}")

    assert result.returncode != 0
    assert f"ImportError: {module} was removed in pysepal 5.0" in result.stderr
    assert 'pin "pysepal<5"' in result.stderr
    assert "migrating-to-pysepal-5" in result.stderr


REMOVED_NAMES = [
    ("pysepal.aoi", "AoiView"),
    ("pysepal.aoi", "AoiTile"),
    ("pysepal.planetapi", "PlanetView"),
    ("pysepal.mapping", "AoiControl"),
    ("pysepal.mapping", "LayersControl"),
    ("pysepal.mapping", "DrawControl"),
    ("pysepal.mapping", "GeomanDrawControl"),
    ("pysepal.mapping", "InspectorControl"),
    ("pysepal.mapping", "ValueInspector"),
    ("pysepal.mapping", "ZoomControl"),
    ("pysepal.mapping", "FullScreenControl"),
    ("pysepal.mapping", "LayerStateControl"),
    ("pysepal.mapping", "MenuControl"),
    ("pysepal.mapping", "LegendControl"),
    ("pysepal.mapping", "EELayer"),
    ("pysepal.mapping", "MarkerCluster"),
    ("pysepal.mapping", "get_ipygeojson"),
]


@pytest.mark.parametrize("module,name", REMOVED_NAMES)
def test_removed_widget_names_say_what_to_do(module, name):
    import importlib

    package = importlib.import_module(module)
    with pytest.raises(AttributeError, match="removed in pysepal 5.0"):
        getattr(package, name)


@pytest.mark.parametrize("module,name", REMOVED_NAMES)
def test_from_import_of_a_removed_name_says_what_to_do(module, name):
    with pytest.raises(ImportError, match="removed in pysepal 5.0"):
        exec(f"from {module} import {name}")


@pytest.mark.parametrize(
    "code",
    [
        "from pysepal.mapping import draw_control",
        "from pysepal.mapping.draw_control import DrawControl",
        "from pysepal import sepalwidgets",
        "from pysepal.sepalwidgets import vue_app",
    ],
)
def test_every_import_form_of_a_removed_module_says_what_to_do(code):
    with pytest.raises(ImportError, match="removed in pysepal 5.0"):
        exec(code)


def test_a_removed_name_is_absent_for_hasattr():
    import pysepal.mapping

    assert not hasattr(pysepal.mapping, "DrawControl")
    assert not hasattr(pysepal.mapping, "draw_control")


@pytest.mark.parametrize(
    "name,cause",
    [
        ("LayersControl", "with the ipyvuetify 1 widget layer"),
        ("LegendControl", "with the move to MapLibre"),
        ("DrawControl", "with the move to MapLibre"),
    ],
)
def test_removed_mapping_names_say_what_removed_them(name, cause):
    import pysepal.mapping

    with pytest.raises(AttributeError, match=cause):
        getattr(pysepal.mapping, name)


@pytest.mark.parametrize("member", ["add_legend", "add_colorbar", "show_dc"])
def test_removed_sepal_map_members_say_what_to_do(member):
    from pysepal.mapping import SepalMap

    with pytest.raises(AttributeError, match="removed in pysepal 5.0") as error:
        getattr(SepalMap(gee=False), member)
    assert "migrating-to-pysepal-5" in str(error.value)


def test_unknown_names_still_raise_the_usual_error():
    import pysepal.aoi

    with pytest.raises(AttributeError, match="has no attribute 'nope'"):
        pysepal.aoi.nope
    with pytest.raises(ModuleNotFoundError, match="No module named 'pysepal.mapping.nope'"):
        import pysepal.mapping.nope
    with pytest.raises(ImportError, match="cannot import name 'nope'"):
        from pysepal.mapping import nope  # noqa: F401


def test_the_solara_surface_imports():
    imports = "; ".join(f"import {name}" for name in SOLARA_SURFACE)
    result = _run(f"import sys; {imports}")
    assert result.returncode == 0, result.stderr


def test_models_import_without_widgets():
    result = _run("from pysepal.aoi import AoiModel; from pysepal.planetapi import PlanetModel")
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "module,replacement",
    [
        ("pysepal.mapping.draw_control", "m.draw.begin(modes) and the DrawSession it returns"),
        ("pysepal.mapping.inspector_control", "SepalMap(inspector=True)"),
    ],
)
def test_removed_stubs_name_their_replacement(module, replacement):
    assert replacement in _run(f"import {module}").stderr
