"""The deprecated widget layer: a warning on ipyvuetify 1, a clear error on 3.

Each check runs in a fresh interpreter, because the warning fires once, when the
package is first imported.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from pysepal._vuetify import IPYVUETIFY_V3

# `python -c` imports pysepal from its cwd; a test elsewhere chdirs and never restores.
REPO_ROOT = Path(__file__).resolve().parents[1]

v2_only = pytest.mark.skipif(IPYVUETIFY_V3, reason="sepalwidgets needs ipyvuetify 1")
v3_only = pytest.mark.skipif(not IPYVUETIFY_V3, reason="checks the ipyvuetify 3 error")

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


@v3_only
def test_import_on_v3_raises_clear_error():
    result = _run("import pysepal.sepalwidgets")

    assert result.returncode != 0
    assert "ImportError: pysepal.sepalwidgets supports ipyvuetify 1 only" in result.stderr
    assert 'pin "ipyvuetify<3"' in result.stderr


@v2_only
def test_import_warns_on_v2():
    result = _run("""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            import pysepal.sepalwidgets
        messages = [str(w.message) for w in caught if w.category is DeprecationWarning]
        assert any("pysepal.sepalwidgets is deprecated" in m for m in messages), messages
        """)
    assert result.returncode == 0, result.stderr


def test_the_solara_surface_does_not_import_sepalwidgets():
    imports = "; ".join(f"import {name}" for name in SOLARA_SURFACE)
    result = _run(f"""
        import sys; {imports}
        loaded = sorted(m for m in sys.modules if m.startswith("pysepal.sepalwidgets"))
        assert not loaded, loaded
        """)
    assert result.returncode == 0, result.stderr


def test_models_import_without_their_widgets():
    result = _run("""
        import sys
        from pysepal.aoi import AoiModel
        from pysepal.planetapi import PlanetModel
        assert "pysepal.aoi.aoi_view" not in sys.modules
        assert "pysepal.planetapi.planet_view" not in sys.modules
        """)
    assert result.returncode == 0, result.stderr
