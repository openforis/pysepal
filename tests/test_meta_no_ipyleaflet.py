"""pysepal 5 draws with MapLibre: importing it must not load ipyleaflet."""

import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_no_module_imports_ipyleaflet():
    # a fresh interpreter: another test may already have imported ipyleaflet
    code = """
        import importlib
        import pkgutil
        import sys

        import pysepal
        import pysepal.mapping
        import pysepal.solara.components as components

        for info in pkgutil.walk_packages(components.__path__, "pysepal.solara.components."):
            importlib.import_module(info.name)

        loaded = [n for n in ("ipyleaflet", "jupyter_leaflet") if n in sys.modules]
        assert not loaded, loaded
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
