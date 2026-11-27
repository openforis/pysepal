"""pysepal 5 draws with MapLibre: importing it must not load ipyleaflet."""

import subprocess
import sys
import textwrap
from pathlib import Path

from tests.test_frontend.test_watcher_contract import SKIPPED

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_no_module_imports_ipyleaflet():
    # a fresh interpreter: another test may already have imported ipyleaflet.
    # The skipped modules are scaffolding and stubs that raise ImportError on purpose.
    code = f"""
        import importlib
        import pkgutil
        import sys

        import pysepal

        skipped = {tuple(SKIPPED)!r}

        for info in pkgutil.walk_packages(pysepal.__path__, "pysepal."):
            if info.name.startswith(skipped):
                continue
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
