"""One interface for user files, on the local disk or in the SEPAL workspace.

Paths are absolute POSIX paths under :attr:`FileSystem.root`; a relative path is
taken from the root. The local root defaults to the home folder and the
workspace root is ``/home/sepal-user``, which is also the home folder of a SEPAL
sandbox, so the same path names the same file on both. Every path is checked
against the root before it is used, and a path outside it raises
:class:`PathOutsideRootError`.

Each operation has an ``*_async`` twin that runs it in a worker thread. The
twins do pure I/O, so they are safe off the Solara kernel context.
"""

import asyncio
import json
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path, PurePosixPath
from typing import (
    Any,
    AsyncIterator,
    Iterator,
    List,
    Literal,
    Optional,
    Sequence,
    Union,
)

from natsort import natsorted
from pydantic import BaseModel
from pysepal_api.errors import Conflict
from pysepal_api.paths import BASE_REMOTE_PATH

PathLike = Union[str, os.PathLike]

SANDBOX_ROOT = PurePosixPath(BASE_REMOTE_PATH)
"The root of a user's SEPAL workspace, and the home folder of their sandbox."


class FileDetails(BaseModel):
    name: str
    path: str
    type: Literal["directory", "file", "symlink"]
    size: int
    modified_time: Optional[float] = 0.0


class ListDirectoryResponse(BaseModel):
    path: str
    files: List[FileDetails]

    def sorted(self) -> "ListDirectoryResponse":
        """Returns a new ListDirectoryResponse instance with the files sorted using human sorting, placing directories before files."""
        sorted_files = natsorted(
            self.files, key=lambda x: (0 if x.type == "directory" else 1, x.name.lower())
        )
        return ListDirectoryResponse(path=self.path, files=sorted_files)


class PathOutsideRootError(ValueError):
    """A path resolves outside the root of its filesystem."""


class FileSystem(ABC):
    """Read and write user files without knowing where they live."""

    root: PurePosixPath

    @abstractmethod
    def resolve(self, path: PathLike) -> PurePosixPath:
        """Return the absolute path, or raise :class:`PathOutsideRootError`."""

    def contains(self, path: PathLike) -> bool:
        """Whether ``path`` resolves inside the root."""
        try:
            self.resolve(path)
        except PathOutsideRootError:
            return False
        return True

    @abstractmethod
    def list(
        self, folder: Optional[PathLike] = None, extensions: Optional[Sequence[str]] = None
    ) -> ListDirectoryResponse:
        """List a folder, the root by default. ``extensions`` filters files only."""

    @abstractmethod
    def read_bytes(self, path: PathLike) -> bytes:
        """Return the content of a file."""

    def read_text(self, path: PathLike) -> str:
        """Return the content of a file decoded as UTF-8."""
        return self.read_bytes(path).decode("utf-8")

    def read_json(self, path: PathLike) -> Any:
        """Return the content of a file parsed as JSON."""
        return json.loads(self.read_text(path))

    @abstractmethod
    def write(
        self, path: PathLike, content: Union[str, bytes], overwrite: bool = False
    ) -> PurePosixPath:
        """Write a file in an existing folder. Raises FileExistsError unless ``overwrite``."""

    @abstractmethod
    def mkdir(self, path: PathLike, parents: bool = True) -> PurePosixPath:
        """Create a folder; an existing one is not an error."""

    @abstractmethod
    @contextmanager
    def local_copy(self, path: PathLike) -> Iterator[Path]:
        """Yield a local path to the file, for readers that only open local files.

        A shapefile comes with its sidecar files (same name, other extensions).
        """

    async def list_async(
        self, folder: Optional[PathLike] = None, extensions: Optional[Sequence[str]] = None
    ) -> ListDirectoryResponse:
        """Async twin of :meth:`list`."""
        return await asyncio.to_thread(self.list, folder, extensions)

    async def read_bytes_async(self, path: PathLike) -> bytes:
        """Async twin of :meth:`read_bytes`."""
        return await asyncio.to_thread(self.read_bytes, path)

    async def read_text_async(self, path: PathLike) -> str:
        """Async twin of :meth:`read_text`."""
        return await asyncio.to_thread(self.read_text, path)

    async def read_json_async(self, path: PathLike) -> Any:
        """Async twin of :meth:`read_json`."""
        return await asyncio.to_thread(self.read_json, path)

    async def write_async(
        self, path: PathLike, content: Union[str, bytes], overwrite: bool = False
    ) -> PurePosixPath:
        """Async twin of :meth:`write`."""
        return await asyncio.to_thread(self.write, path, content, overwrite)

    async def mkdir_async(self, path: PathLike, parents: bool = True) -> PurePosixPath:
        """Async twin of :meth:`mkdir`."""
        return await asyncio.to_thread(self.mkdir, path, parents)

    @asynccontextmanager
    async def local_copy_async(self, path: PathLike) -> AsyncIterator[Path]:
        """Async twin of :meth:`local_copy`."""
        context = self.local_copy(path)
        local = await asyncio.to_thread(context.__enter__)
        try:
            yield local
        finally:
            await asyncio.to_thread(context.__exit__, None, None, None)


class LocalFileSystem(FileSystem):
    """Files on the disk of this process, kept under ``root``."""

    def __init__(self, root: Optional[PathLike] = None):
        """Bound the filesystem to ``root``, the home folder by default."""
        root_path = Path(root) if root else Path.home()
        self.root = PurePosixPath(os.path.normpath(root_path.absolute()))
        self._resolved_root = root_path.resolve()

    def resolve(self, path: PathLike) -> PurePosixPath:
        """Return the absolute path; ``..`` and symlinks must stay inside the root."""
        candidate = Path(os.path.normpath(Path(self.root) / Path(path)))
        try:
            inside = candidate.resolve().is_relative_to(self._resolved_root)
        except (OSError, RuntimeError):
            inside = False
        if not inside:
            raise PathOutsideRootError(f"{path} is outside {self.root}")
        return PurePosixPath(candidate)

    def list(
        self, folder: Optional[PathLike] = None, extensions: Optional[Sequence[str]] = None
    ) -> ListDirectoryResponse:
        """List a folder, skipping hidden entries."""
        folder_path = Path(self.resolve(folder or self.root))
        files = []
        for entry in folder_path.iterdir():
            if entry.name.startswith("."):
                continue
            if entry.is_symlink():
                kind = "symlink"
            elif entry.is_dir():
                kind = "directory"
            else:
                kind = "file"
            if kind == "file" and extensions and entry.suffix not in extensions:
                continue
            try:
                stat = entry.stat()
                size, modified = stat.st_size, stat.st_mtime
            except OSError:
                size, modified = 0, 0.0
            files.append(
                FileDetails(
                    name=entry.name, path=str(entry), type=kind, size=size, modified_time=modified
                )
            )
        return ListDirectoryResponse(path=str(folder_path), files=files).sorted()

    def read_bytes(self, path: PathLike) -> bytes:
        """Return the content of a file."""
        return Path(self.resolve(path)).read_bytes()

    def write(
        self, path: PathLike, content: Union[str, bytes], overwrite: bool = False
    ) -> PurePosixPath:
        """Write a file in an existing folder."""
        target = Path(self.resolve(path))
        if target.exists() and not overwrite:
            raise FileExistsError(str(target))
        payload = content.encode("utf-8") if isinstance(content, str) else content
        target.write_bytes(payload)
        return PurePosixPath(target)

    def mkdir(self, path: PathLike, parents: bool = True) -> PurePosixPath:
        """Create a folder; an existing one is not an error."""
        target = self.resolve(path)
        Path(target).mkdir(parents=parents, exist_ok=True)
        return target

    @contextmanager
    def local_copy(self, path: PathLike) -> Iterator[Path]:
        """Yield the file itself: it is already local."""
        yield Path(self.resolve(path))


class SandboxFileSystem(FileSystem):
    """Files in a user's SEPAL workspace, through the SEPAL API.

    The API serves only the workspace of the client's user; paths are also
    checked here, so a bad one fails before a request is sent.
    """

    root = SANDBOX_ROOT

    def __init__(self, client: Any):
        """Wrap a ``pysepal_api.SepalClient``."""
        self.client = client

    def resolve(self, path: PathLike) -> PurePosixPath:
        """Return the absolute path; it must stay inside the workspace."""
        candidate = self.root / PurePosixPath(str(path))
        if ".." in candidate.parts or not candidate.is_relative_to(self.root):
            raise PathOutsideRootError(f"{path} is outside {self.root}")
        return candidate

    def list(
        self, folder: Optional[PathLike] = None, extensions: Optional[Sequence[str]] = None
    ) -> ListDirectoryResponse:
        """List a folder of the workspace."""
        folder_path = self.resolve(folder or self.root)
        listing = self.client.files.list(
            str(folder_path), extensions=list(extensions) if extensions else None
        )
        files = [
            FileDetails(
                name=entry.name,
                path=str(self.root / entry.path),
                type=entry.type if entry.type in ("directory", "symlink") else "file",
                size=entry.size,
                modified_time=entry.modified_time.timestamp() if entry.modified_time else 0.0,
            )
            for entry in listing.files
        ]
        return ListDirectoryResponse(path=str(folder_path), files=files).sorted()

    def read_bytes(self, path: PathLike) -> bytes:
        """Download a file."""
        return self.client.files.read_bytes(str(self.resolve(path)))

    def write(
        self, path: PathLike, content: Union[str, bytes], overwrite: bool = False
    ) -> PurePosixPath:
        """Upload a file into an existing folder."""
        target = self.resolve(path)
        try:
            self.client.files.write(str(target), content, overwrite=overwrite)
        except Conflict as error:
            raise FileExistsError(str(target)) from error
        return target

    def mkdir(self, path: PathLike, parents: bool = True) -> PurePosixPath:
        """Create a folder; an existing one is not an error."""
        target = self.resolve(path)
        self.client.files.mkdir(str(target), parents=parents)
        return target

    @contextmanager
    def local_copy(self, path: PathLike) -> Iterator[Path]:
        """Download the file, and a shapefile's sidecars, into a temporary folder."""
        source = self.resolve(path)
        sources = [source]
        if source.suffix.lower() == ".shp":
            siblings = self.list(source.parent).files
            sources += [
                PurePosixPath(f.path)
                for f in siblings
                if f.type == "file"
                and PurePosixPath(f.path).stem == source.stem
                and PurePosixPath(f.path) != source
            ]

        folder = Path(tempfile.mkdtemp(prefix="pysepal-"))
        try:
            for item in sources:
                (folder / item.name).write_bytes(self.read_bytes(item))
            yield folder / source.name
        finally:
            shutil.rmtree(folder, ignore_errors=True)
