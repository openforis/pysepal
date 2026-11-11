"""Folder-per-project storage: one subfolder of ``root`` per project, each with a manifest file."""

import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("sepalui.project")

_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]+$")


@dataclass(frozen=True)
class ProjectInfo:
    name: str
    updated_at: Optional[datetime] = None
    chips: tuple[tuple[str, bool], ...] = ()  # (label, accent)
    subtitle: Optional[str] = None
    subtitle_icon: Optional[str] = None
    readable: bool = True


class ProjectStore:
    def __init__(self, root: Path, manifest: str = "project.json"):
        self.root = Path(root)
        self.manifest = manifest

    def folder(self, name: str) -> Path:
        """The project folder; ValueError unless ``name`` is a direct child of root."""
        if name in ("", ".", "..") or Path(name).name != name:
            raise ValueError(f"unsafe project name: {name!r}")
        return self.root / name

    def manifest_path(self, name: str) -> Path:
        return self.folder(name) / self.manifest.format(name=name)

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return [d.name for d in self.root.iterdir() if d.is_dir()]

    def infos(self) -> list[ProjectInfo]:
        infos = []
        for name in sorted(self.names(), key=str.casefold):
            if not self.manifest_path(name).is_file():
                continue
            try:
                info = self.describe(name, self.folder(name))
            except Exception:
                logger.warning("cannot describe project %r", name, exc_info=True)
                infos.append(ProjectInfo(name, readable=False))
                continue
            if info is not None:
                infos.append(info)
        return infos

    def describe(self, name: str, folder: Path) -> Optional[ProjectInfo]:
        """App hook: return None to hide the project, raise to list it as unreadable."""
        mtime = self.manifest_path(name).stat().st_mtime
        return ProjectInfo(name, updated_at=datetime.fromtimestamp(mtime))

    def validate_name(self, name: str, exclude: Optional[str] = None) -> Optional[str]:
        text = (name or "").strip()
        if not text:
            return "empty"
        if not _NAME_RE.match(text):
            return "chars"
        taken = {n.casefold() for n in self.names() if n != exclude}
        return "exists" if text.casefold() in taken else None

    def size(self, name: str) -> int:
        total = 0
        for dirpath, _, files in os.walk(self.folder(name)):  # os.walk does not follow dir links
            for f in files:
                p = os.path.join(dirpath, f)
                if not os.path.islink(p):
                    total += os.path.getsize(p)
        return total

    def rename(self, old: str, new: str) -> None:
        src, dst = self.folder(old), self.folder(new)
        if dst.exists():  # os.rename would silently replace an empty folder
            raise FileExistsError(str(dst))
        os.rename(src, dst)
        old_manifest, new_manifest = dst / self.manifest.format(name=old), self.manifest_path(new)
        if old_manifest != new_manifest and old_manifest.exists():
            os.rename(old_manifest, new_manifest)

    def delete(self, name: str) -> None:
        """Contents first, manifest last: a half-deleted folder no longer lists as a project."""
        folder = self.folder(name)
        if folder.is_symlink():  # the link goes, never what it points to
            folder.unlink()
            return
        manifest = self.manifest_path(name)
        for child in list(folder.iterdir()):
            if child == manifest:
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        manifest.unlink(missing_ok=True)
        folder.rmdir()

    def delete_blocked(self, name: str) -> Optional[str]:
        """App hook: a reason string while the project must not be deleted, else None."""
        return None
