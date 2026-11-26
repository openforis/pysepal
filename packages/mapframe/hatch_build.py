"""Build hook: install the locked JS dependencies and bundle the widget assets."""

import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

TARGETS = ("src/mapframe/static/widget.js", "src/mapframe/static/widget.css")


class JSBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        """Build the JS bundle unless the sdist already carries it."""
        root = Path(self.root)
        # A wheel built from a populated sdist has no JS toolchain inputs.
        if all((root / t).exists() for t in TARGETS):
            return
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "Building mapframe from a source checkout bundles its JS widget, which needs "
                "Node 22+ and npm on PATH. The published wheels and sdists already contain the "
                "built files, so installing one of those needs neither."
            )
        # `npm ci` installs exactly package-lock.json; `npm install` could rewrite it.
        subprocess.run([npm, "ci"], cwd=root, check=True)
        subprocess.run([npm, "run", "build"], cwd=root, check=True)
        missing = [t for t in TARGETS if not (root / t).exists()]
        if missing:
            raise RuntimeError(f"JS build did not produce {missing}")
