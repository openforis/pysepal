"""The user's GEE asset list, listed once per session and shared by every reader.

Listing walks every folder under the root and sends one request per folder, so
each asset field listing on its own mount made a form slow to open. The list now
lives in a per-kernel store: a page load lists it once, and only the refresh icon
(``GeeAssets.reload``) lists it again.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

import solara
import solara.toestand
from deprecated.sphinx import versionadded

from pysepal.solara.utils import get_current_gee_interface

__all__ = ["GeeAssets", "use_gee_assets"]

_Key = Tuple[int, str]


@dataclass(frozen=True)
class GeeAssets:
    """The asset list of one folder, as :func:`use_gee_assets` returns it.

    Attributes:
        assets: Every asset under the folder, at any depth, as the dicts
            ``get_assets_async`` returns (``id``, ``type``, ...). While a reload
            runs, this still holds the previous list.
        folder: The folder listed: the user's root folder when none was given,
            until the first listing resolves it.
        loading: Whether a listing is running.
        error: Why the last listing failed, or None.
        reload: Lists the folder again, for every reader of it in this session.
    """

    assets: Tuple[Dict[str, Any], ...] = ()
    folder: str = ""
    loading: bool = False
    error: Optional[BaseException] = None
    reload: Callable[[], None] = field(default=lambda: None, compare=False)


class _Listings:
    """One kernel's listings, keyed by interface and folder."""

    def __init__(self) -> None:
        # The interface is held next to its task so its id cannot be reused by
        # another interface while the entry lives.
        self.tasks: Dict[_Key, Tuple[Any, asyncio.Task]] = {}


_listings = solara.toestand.KernelStoreFactory(_Listings)

#: Reload count per key. Every reader depends on it, so a reload re-runs them all.
_revisions = solara.Reactive(solara.toestand.KernelStoreFactory(dict))


async def _list(gee_interface: Any, folder: str) -> Tuple[str, Tuple[Dict[str, Any], ...]]:
    folder_path = folder or await gee_interface.get_folder_async()
    return folder_path, tuple(await gee_interface.get_assets_async(folder_path))


def _reusable(task: Optional[asyncio.Task]) -> bool:
    if task is None:
        return False
    if task.done():
        # A failure is not kept: the next reader tries again.
        return not task.cancelled() and task.exception() is None
    # A listing left running on a closed loop would never finish.
    return task.get_loop() is asyncio.get_running_loop()


async def _shared_listing(gee_interface: Any, folder: str) -> Tuple[str, Tuple[Dict, ...]]:
    tasks = _listings.get().tasks
    key = (id(gee_interface), folder)
    held = tasks.get(key)
    task = held[1] if held else None
    if not _reusable(task):
        task = asyncio.get_running_loop().create_task(_list(gee_interface, folder))
        tasks[key] = (gee_interface, task)
    if task.done():
        return task.result()
    # Shielded: a reader that unmounts must not cancel the listing for the others.
    return await asyncio.shield(task)


def _reload(gee_interface: Any, folder: str) -> None:
    key = (id(gee_interface), folder)
    _listings.get().tasks.pop(key, None)
    revisions = dict(_revisions.peek())
    revisions[key] = revisions.get(key, 0) + 1
    _revisions.set(revisions)


@versionadded(version="4.2", reason="One asset list per session, shared by every field")
def use_gee_assets(folder: str = "", gee_interface: Any = None) -> GeeAssets:
    """Return the user's assets under ``folder``, listed once per session.

    Every reader of the same folder shares one listing: fields mounted together
    send one set of requests, and a field mounted later reads the list without
    any. A failed listing is not kept, so the next mount tries again.

    Args:
        folder: The GEE folder to list. Defaults to the user's root folder.
        gee_interface: The interface to list with. Defaults to the session's.

    Returns:
        The listing, which re-renders the caller when it changes.

    Example:
        ```python
        @solara.component
        def CollectionField(value: solara.Reactive[str]):
            listing = use_gee_assets()
            ids = [a["id"] for a in listing.assets if a["type"] == "IMAGE_COLLECTION"]
            solara.Select("Collection", values=ids, value=value)
            solara.Button("Refresh", on_click=listing.reload, disabled=listing.loading)
        ```
    """
    gee_interface = gee_interface or get_current_gee_interface()
    key = (id(gee_interface), folder)
    revision = _revisions.value.get(key, 0)

    async def fetch():
        # Returned, not raised: solara leaves a raised exception unretrieved on
        # its future, and asyncio logs that as an error.
        try:
            return await _shared_listing(gee_interface, folder), None
        except Exception as error:
            return None, error

    # Keep session-backed GEE coroutines on Solara's current event loop.
    task = solara.lab.use_task(
        fetch, dependencies=[key, revision], raise_error=False, prefer_threaded=False
    )

    def reload() -> None:
        _reload(gee_interface, folder)

    loading = not (task.finished or task.error or task.cancelled)
    listed, error = task.latest if task.latest is not None else (None, None)
    folder_path, assets = listed if listed is not None else (folder, ())
    return GeeAssets(
        assets=assets,
        folder=folder_path,
        loading=loading,
        error=None if loading else error,
        reload=reload,
    )
