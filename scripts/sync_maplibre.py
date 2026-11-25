"""Mirror a commit of the pysepal-maplibre repository into packages/pysepal-maplibre.

Usage: python scripts/sync_maplibre.py PATH_TO_PYSEPAL_MAPLIBRE [REF]

The files pysepal tracks there are replaced by the files of REF (default HEAD), except
the repository's own CI and pre-commit config. Ignored files, such as node_modules and
the built bundle, stay. Commit the result with the commit it printed.
"""

import io
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "packages" / "pysepal-maplibre"
SKIPPED = (".github/", ".pre-commit-config.yaml")


def git(*args: str, cwd: Path) -> bytes:
    """Run git in ``cwd`` and return its output."""
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True).stdout


def main(source: Path, ref: str = "HEAD") -> None:
    """Replace the mirror with the files of ``ref`` in ``source``."""
    commit = git("rev-parse", "--short", f"{ref}^{{commit}}", cwd=source).decode().strip()
    archive = tarfile.open(fileobj=io.BytesIO(git("archive", commit, cwd=source)))

    tracked = git("ls-files", "-z", str(TARGET.relative_to(ROOT)), cwd=ROOT).split(b"\0")
    for name in filter(None, tracked):
        (ROOT / name.decode()).unlink(missing_ok=True)

    for member in archive.getmembers():
        if member.isfile() and not member.name.startswith(SKIPPED):
            path = TARGET / member.name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
            path.chmod(member.mode)

    print(f"packages/pysepal-maplibre is now pysepal-maplibre {commit}")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), *sys.argv[2:3])
