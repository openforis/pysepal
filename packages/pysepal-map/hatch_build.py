"""Build hook: install the locked JS dependencies and bundle the widget assets."""

import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

TARGETS = ("src/pysepal_map/static/widget.js", "src/pysepal_map/static/widget.css")


class JSBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        root = Path(self.root)
        # A wheel built from a populated sdist has no JS toolchain inputs.
        if all((root / t).exists() for t in TARGETS):
            return
        # `npm ci` installs exactly package-lock.json; `npm install` could rewrite it.
        subprocess.run(["npm", "ci"], cwd=root, check=True)
        subprocess.run(["npm", "run", "build"], cwd=root, check=True)
        missing = [t for t in TARGETS if not (root / t).exists()]
        if missing:
            raise RuntimeError(f"JS build did not produce {missing}")
