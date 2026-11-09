"""The user's GEE asset list, listed once per session and shared by every reader.

Listing walks every folder under the root and sends one request per folder, so
each asset field listing on its own mount made a form slow to open. The list now
lives in a per-kernel store: a page load lists it once, and only a reload (the
refresh icon, or :func:`reload_gee_assets`) lists it again.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

import solara
import solara.toestand
from deprecated.sphinx import versionadded

from pysepal.solara.utils import get_current_gee_interface

__all__ = ["GeeAssets", "reload_gee_assets", "use_gee_assets"]


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
        reload: :func:`reload_gee_assets`, for a refresh icon.
    """

    assets: Tuple[Dict[str, Any], ...] = ()
    folder: str = ""
    loading: bool = False
    error: Optional[BaseException] = None
    reload: Callable[[], None] = field(default=lambda: None, compare=False)


class _Listings:
    """One kernel's listings, keyed by folder.

    A kernel serves one user, so the folder is the whole key. Keying by the
    interface too would make an app that builds one on each render list again on
    each render.
    """

    def __init__(self) -> None:
        self.tasks: Dict[str, asyncio.Task] = {}


_listings = solara.toestand.KernelStoreFactory(_Listings)

#: Reload count of the session. Every reader depends on it, so a reload re-runs them all.
_revision = solara.Reactive(solara.toestand.KernelStoreFactory(int))


async def _list(gee_interface: Any, folder: str) -> Tuple[str, Tuple[Dict[str, Any], ...]]:
    folder_path = folder or await gee_interface.get_folder_async()
    return folder_path, tuple(await gee_interface.get_assets_async(folder_path))


def _reusable(task: asyncio.Task) -> bool:
    if task.done():
        # A failure is not kept: the next reader tries again.
        return not task.cancelled() and task.exception() is None
    # A listing left running on a closed loop would never finish.
    return task.get_loop() is asyncio.get_running_loop()


async def _shared_listing(gee_interface: Any, folder: str) -> Tuple[str, Tuple[Dict, ...]]:
    tasks = _listings.get().tasks
    task = tasks.get(folder)
    if task is None or not _reusable(task):
        task = asyncio.get_running_loop().create_task(_list(gee_interface, folder))
        tasks[folder] = task
    if task.done():
        return task.result()
    # Shielded: a reader that unmounts must not cancel the listing for the others.
    return await asyncio.shield(task)


@versionadded(version="4.2", reason="Refresh every asset field of the session")
def reload_gee_assets() -> None:
    """List the assets again, for every asset field of this session.

    Every folder the session has listed is listed again, so a field on a
    subfolder never shows an older list than a field on the root. Call it from a
    callback or a task of the session.

    An export to an asset creates the asset only when its Earth Engine task
    completes. Reload then, not when the export starts.
    """
    _listings.get().tasks.clear()
    _revision.set(_revision.peek() + 1)


@versionadded(version="4.2", reason="One asset list per session, shared by every field")
def use_gee_assets(folder: str = "", gee_interface: Any = None) -> GeeAssets:
    """Return the user's assets under ``folder``, listed once per session.

    Every reader of the same folder shares one listing: fields mounted together
    send one set of requests, and a field mounted later reads the list without
    any. A failed listing is not kept, so the next mount tries again.

    Args:
        folder: The GEE folder to list. Defaults to the user's root folder.
        gee_interface: The interface to list with. Defaults to the session's. The
            list is shared by folder only: every field of the session reads the
            same list, whichever interface it passes.

    Returns:
        The listing, which re-renders the caller when it changes.

    Example:
        ```python
        @solara.component
        def CollectionField(value: solara.Reactive[str]):
            listing = use_gee_assets()
            ids = [a["id"] for a in listing.assets if a["type"] == "IMAGE_COLLECTION"]
            solara.Select("Collection", values=ids, value=value)
            solara.Button("Refresh", on_click=reload_gee_assets, disabled=listing.loading)
        ```
    """
    gee_interface = gee_interface or get_current_gee_interface()
    revision = _revision.value

    async def fetch():
        # Returned, not raised: solara leaves a raised exception unretrieved on
        # its future, and asyncio logs that as an error.
        try:
            return await _shared_listing(gee_interface, folder), None
        except Exception as error:
            return None, error

    # Keep session-backed GEE coroutines on Solara's current event loop.
    task = solara.lab.use_task(
        fetch, dependencies=[folder, revision], raise_error=False, prefer_threaded=False
    )

    loading = not (task.finished or task.error or task.cancelled)
    listed, error = task.latest if task.latest is not None else (None, None)
    folder_path, assets = listed if listed is not None else (folder, ())
    return GeeAssets(
        assets=assets,
        folder=folder_path,
        loading=loading,
        error=None if loading else error,
        reload=reload_gee_assets,
    )
