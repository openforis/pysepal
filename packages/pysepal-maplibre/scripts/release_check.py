"""Check that the release artifacts work without the source tree or Node.

Builds an sdist from a copy of the repository, builds a wheel from that sdist
on a PATH with no Node, installs the wheel into a clean venv, and runs the
offline rendered-point browser test against that install from outside the
repository.

Needs network for PyPI and `npm ci`, and tests/browser/.build/harness.js
(`npm run build:harness`). `nox -s release-check` does both.

    python scripts/release_check.py
"""

import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent
STATIC = ("pysepal_map/static/widget.js", "pysepal_map/static/widget.css")
#: Shipped at the sdist root and among the wheel's dist-info license files.
NOTICES = ("LICENSE", "THIRD_PARTY_NOTICES.md")
#: Left out of the copy the sdist is built from: build outputs, tests, and the
#: repository's own tool and environment folders, which can be large.
IGNORED = shutil.ignore_patterns(
    "node_modules",
    "static",
    ".build",
    "__pycache__",
    "tests",
    ".git",
    ".nox",
    ".venv",
    "dist",
    "build",
    "*.egg-info",
    ".*_cache",
)
SMOKE_TEST = "browser/test_render.py::test_bundled_worker_renders_offline"


def run(*cmd, **kwargs):
    """Echo and run a command; a failure stops the check."""
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kwargs)


def make_venv(path):
    """Create a venv with pip and return its interpreter."""
    venv.create(path, with_pip=True)
    return path / "bin" / "python"


def main():
    """Build, install and smoke-test the release artifacts."""
    harness = PACKAGE / "tests/browser/.build/harness.js"
    if not harness.exists():
        sys.exit(f"{harness} is missing: run `npm run build:harness`")

    with tempfile.TemporaryDirectory(prefix="psm-release-") as tmp:
        tmp = Path(tmp)
        checkout, dist = tmp / "checkout", tmp / "dist"
        shutil.copytree(PACKAGE, checkout, ignore=IGNORED)

        builder = make_venv(tmp / "builder")
        run(builder, "-m", "pip", "install", "--quiet", "hatchling")
        run(builder, "-m", "hatchling", "build", "-t", "sdist", "-d", dist, cwd=checkout)
        [sdist] = dist.glob("*.tar.gz")
        with tarfile.open(sdist) as tar:
            members = {name.split("/", 1)[1] for name in tar.getnames() if "/" in name}
            tar.extractall(tmp / "unpacked", filter="data")
        missing = [f"src/{t}" for t in STATIC if f"src/{t}" not in members]
        missing += [n for n in NOTICES if n not in members]
        assert not missing, f"sdist lacks {missing}"
        [unpacked] = (tmp / "unpacked").iterdir()

        # The hook only runs npm when the assets are missing, so a PATH
        # with nothing on it proves the sdist alone is enough.
        bare = tmp / "bare-path"
        bare.mkdir()
        assert shutil.which("node", path=str(bare)) is None
        run(
            builder,
            "-m",
            "hatchling",
            "build",
            "-t",
            "wheel",
            "-d",
            tmp / "wheels",
            cwd=unpacked,
            env={**os.environ, "PATH": str(bare)},
        )
        [wheel] = (tmp / "wheels").glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
            [metadata] = [n for n in names if n.endswith(".dist-info/METADATA")]
            metadata = archive.read(metadata).decode()
        licenses = {Path(n).name for n in names if n.split("/", 1)[0].endswith(".dist-info")}
        missing = [t for t in STATIC if t not in names]
        missing += [n for n in NOTICES if n not in licenses]
        assert not missing, f"wheel lacks {missing}"
        assert "License: MIT" in metadata.splitlines(), "wheel metadata names no MIT license"

        python = make_venv(tmp / "clean")
        run(python, "-m", "pip", "install", "--quiet", f"{wheel}[test]")
        smoke = tmp / "smoke"
        shutil.copytree(
            PACKAGE / "tests/browser",
            smoke / "browser",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        located = subprocess.run(
            [python, "-c", "import pysepal_map; print(pysepal_map.__file__)"],
            check=True,
            capture_output=True,
            text=True,
            cwd=smoke,
        ).stdout.strip()
        site = tmp / "clean"
        assert Path(located).is_relative_to(site), f"imported {located}, not the installed wheel"
        installed = Path(located).parent / "static"
        assert all((installed / Path(t).name).stat().st_size for t in STATIC), "empty assets"
        print(f"installed {located}", flush=True)

        install_browser = [python, "-m", "playwright", "install"]
        if os.environ.get("CI"):
            install_browser.append("--with-deps")
        run(*install_browser, "chromium")
        run(
            python,
            "-m",
            "pytest",
            SMOKE_TEST,
            "-p",
            "no:cacheprovider",
            cwd=smoke,
            env={
                **os.environ,
                "SOLARA_TEST_RUNNERS": "solara",
                "SOLARA_TEST_VUETIFY_WARMUP": "false",
            },
        )
    print("release check passed")


if __name__ == "__main__":
    main()
