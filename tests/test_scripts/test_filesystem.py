"""Test the filesystem interface over the local disk and the SEPAL workspace."""

import asyncio
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from typing import Dict, List

import pytest
from pysepal_api.errors import Conflict

from pysepal.scripts.filesystem import (
    SANDBOX_ROOT,
    LocalFileSystem,
    PathOutsideRootError,
    SandboxFileSystem,
)


@pytest.fixture
def jail(tmp_path: Path) -> Path:
    """A root folder with a vector, a table, a hidden file and a sub folder."""
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "aoi.geojson").write_text("{}")
    (root / "plots.csv").write_text("id,lat,lon\n")
    (root / ".hidden").write_text("")
    (tmp_path / "outside.csv").write_text("")
    return root


def test_local_resolves_relative_paths_against_the_root(jail: Path) -> None:
    """A relative path lands under the root; an absolute one inside it is kept."""
    fs = LocalFileSystem(jail)

    assert fs.resolve("plots.csv") == PurePosixPath(jail / "plots.csv")
    assert fs.resolve(jail / "sub") == PurePosixPath(jail / "sub")
    assert fs.contains(jail / "plots.csv")


@pytest.mark.parametrize("escape", ["..", "../outside.csv", "sub/../../outside.csv", "/etc"])
def test_local_refuses_paths_outside_the_root(jail: Path, escape: str) -> None:
    """``..`` and absolute paths are resolved before the check."""
    fs = LocalFileSystem(jail)

    assert not fs.contains(escape)
    with pytest.raises(PathOutsideRootError):
        fs.read_bytes(escape)


def test_local_refuses_a_symlink_out_of_the_root(jail: Path) -> None:
    """A link inside the root is followed before the check."""
    (jail / "escape").symlink_to(jail.parent / "outside.csv")

    assert not LocalFileSystem(jail).contains(jail / "escape")


def test_local_list_gives_absolute_paths_folders_first(jail: Path) -> None:
    """Entries are absolute, hidden files are skipped and extensions filter files only."""
    listing = LocalFileSystem(jail).list(jail, extensions=[".csv"])

    assert [(f.name, f.type) for f in listing.files] == [
        ("sub", "directory"),
        ("plots.csv", "file"),
    ]
    assert listing.files[1].path == str(jail / "plots.csv")


def test_local_round_trip(jail: Path) -> None:
    """Write, read back in every form, and refuse to overwrite unless asked."""
    fs = LocalFileSystem(jail)

    created = fs.mkdir("out/nested")
    fs.write("out/nested/spec.json", json.dumps({"a": 1}))

    assert created == PurePosixPath(jail / "out" / "nested")
    assert fs.read_json("out/nested/spec.json") == {"a": 1}
    assert fs.read_text("out/nested/spec.json") == '{"a": 1}'
    assert fs.read_bytes("out/nested/spec.json") == b'{"a": 1}'
    with pytest.raises(FileExistsError):
        fs.write("out/nested/spec.json", b"{}")
    fs.write("out/nested/spec.json", b"{}", overwrite=True)
    assert fs.read_json("out/nested/spec.json") == {}


def test_local_copy_is_the_file_itself(jail: Path) -> None:
    """Nothing to download on the local disk."""
    with LocalFileSystem(jail).local_copy("plots.csv") as path:
        assert path == jail / "plots.csv"


def test_async_twins_match_the_sync_calls(jail: Path) -> None:
    """Every operation has an ``*_async`` twin with the same result."""
    fs = LocalFileSystem(jail)

    async def run():
        await fs.mkdir_async("a")
        await fs.write_async("a/x.txt", "hi")
        listing = await fs.list_async("a")
        async with fs.local_copy_async("a/x.txt") as path:
            copied = path.read_text()
        return (
            await fs.read_text_async("a/x.txt"),
            await fs.read_bytes_async("a/x.txt"),
            [f.name for f in listing.files],
            copied,
        )

    assert asyncio.run(run()) == ("hi", b"hi", ["x.txt"], "hi")


class FakeFiles:
    """The ``client.files`` surface of pysepal-api, over an in-memory workspace.

    Like the server, listings return paths relative to the workspace root.
    """

    def __init__(self, content: Dict[str, bytes]):
        """Hold the workspace as ``{home-relative path: bytes}``."""
        self.content = content
        self.calls: List[tuple] = []

    @staticmethod
    def _relative(path: str) -> str:
        return str(PurePosixPath(path).relative_to(SANDBOX_ROOT))

    def list(self, folder, extensions=None, include_hidden=False):
        self.calls.append(("list", folder))
        rel = PurePosixPath(self._relative(folder))
        entries = {}
        for name in self.content:
            try:
                tail = PurePosixPath(name).relative_to(rel)
            except ValueError:
                continue
            child = rel / tail.parts[0]
            if len(tail.parts) > 1:
                entries[str(child)] = "directory"
            elif not extensions or child.suffix in extensions:
                entries[str(child)] = "file"
        files = [
            SimpleNamespace(name=PurePosixPath(p).name, path=p, type=t, size=1, modified_time=None)
            for p, t in entries.items()
        ]
        return SimpleNamespace(path=str(rel), files=files)

    def read_bytes(self, path):
        self.calls.append(("read_bytes", path))
        return self.content[self._relative(path)]

    def write(self, path, content, overwrite=False):
        rel = self._relative(path)
        if rel in self.content and not overwrite:
            raise Conflict(409, url="/api/user-files/setFile")
        self.content[rel] = content.encode() if isinstance(content, str) else content
        return SimpleNamespace(path=rel, size=len(self.content[rel]))

    def mkdir(self, path, parents=True):
        self.calls.append(("mkdir", path))
        return PurePosixPath(self._relative(path))


@pytest.fixture
def workspace() -> SandboxFileSystem:
    """A sandbox filesystem over a fake client holding a shapefile and a table."""
    files = FakeFiles(
        {
            "data/parcels.shp": b"shp",
            "data/parcels.dbf": b"dbf",
            "data/parcels.shx": b"shx",
            "data/parcels.prj": b"prj",
            "data/other.shp": b"other",
            "data/plots.csv": b"id,lat,lon\n",
        }
    )
    return SandboxFileSystem(SimpleNamespace(files=files))


def test_sandbox_root_is_the_sepal_home(workspace: SandboxFileSystem) -> None:
    """Paths look the same as on the sandbox's own disk."""
    assert workspace.root == PurePosixPath("/home/sepal-user")
    assert workspace.resolve("data/plots.csv") == PurePosixPath("/home/sepal-user/data/plots.csv")


@pytest.mark.parametrize("escape", ["/etc/passwd", "../x", "data/../../x"])
def test_sandbox_refuses_paths_outside_the_workspace(
    workspace: SandboxFileSystem, escape: str
) -> None:
    """Refused here, before any request leaves the process."""
    assert not workspace.contains(escape)
    with pytest.raises(PathOutsideRootError):
        workspace.read_bytes(escape)


def test_sandbox_list_gives_absolute_paths(workspace: SandboxFileSystem) -> None:
    """The server's relative entries come back absolute, like local ones."""
    listing = workspace.list("data", extensions=[".csv"])

    assert listing.path == "/home/sepal-user/data"
    assert [f.path for f in listing.files] == ["/home/sepal-user/data/plots.csv"]


def test_sandbox_write_refuses_to_overwrite(workspace: SandboxFileSystem) -> None:
    """The server's conflict surfaces as the same error the local disk raises."""
    with pytest.raises(FileExistsError):
        workspace.write("data/plots.csv", "x")
    workspace.write("data/plots.csv", "x", overwrite=True)
    assert workspace.read_text("data/plots.csv") == "x"


def test_sandbox_local_copy_brings_shapefile_sidecars(workspace: SandboxFileSystem) -> None:
    """A shapefile is unreadable without its sidecars, so they are downloaded too."""
    with workspace.local_copy("data/parcels.shp") as path:
        names = sorted(p.name for p in path.parent.iterdir())
        assert path.name == "parcels.shp"
        assert path.read_bytes() == b"shp"
    assert names == ["parcels.dbf", "parcels.prj", "parcels.shp", "parcels.shx"]
    assert not path.exists()


def test_sandbox_local_copy_of_a_single_file(workspace: SandboxFileSystem) -> None:
    """Other formats are one download."""
    with workspace.local_copy("/home/sepal-user/data/plots.csv") as path:
        assert path.read_bytes() == b"id,lat,lon\n"
        assert [p.name for p in path.parent.iterdir()] == ["plots.csv"]
