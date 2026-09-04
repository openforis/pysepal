"""GEEInterface class for Earth Engine operations."""

import asyncio
import threading
import traceback
from pathlib import PurePosixPath
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, Union

import ee
from eeclient.client import EESession
from eeclient.data import MapTileOptions
from eeclient.export.image import ImageFileFormat
from eeclient.export.table import TableFileFormat
from eeclient.tasks import Task

from pysepal.logger import log
from pysepal.scripts.gee_task import GEETask, R, TaskState


def _refuse_ambient_session_per_connection() -> None:
    """Refuse to resolve machine credentials where the process serves many users.

    Called only when no session was supplied, immediately before
    :meth:`EESession.from_default` resolves one from the machine. That reads
    ``~/.config/earthengine/credentials``, which in an app-launcher container is
    the *platform* service-account key -- so the interface would answer for the
    platform rather than for the user whose connection asked.

    ``from_default(allow_service_account_file=False)`` refuses that key on its
    own, and in a ``sepal-user`` home it takes a SEPAL-file-only branch that a
    service-account JSON fails to validate. This guard is the topology-level
    decision in front of both: the source of a session is chosen by what kind of
    process this is, never by what the credential store happens to contain.

    This is the chokepoint rather than the callers on purpose. An interface with
    no session is reached from five places across four subpackages --
    ``mapping.SepalMap``, ``solara.components.aoi.admin``, ``aoi.AoiModel`` and
    the ``sepalwidgets`` asset inputs (twice) -- each a quiet
    ``gee_interface or GEEInterface()`` or a ``gee_session`` that is allowed to
    be None. Guarding them one at a time is a list that silently grows every
    time somebody adds a sixth.

    Only ``PER_CONNECTION`` is refused: a notebook, a script, pytest or a SEPAL
    sandbox owns its machine credentials, and resolving them there is correct.

    Raises:
        SepalSessionError: This runtime serves one identity per connection.
    """
    # Local: pysepal.solara.session_manager imports this module, so neither of
    # these can be a module-level import.
    from pysepal.solara.errors import SepalSessionError
    from pysepal.solara.session_manager import _current_plan, _is_scoped_per_connection

    # The same rule the session layer scopes by, so the guard can never disagree
    # with where the session actually lives. That also covers a dev-auth runtime
    # serving a real connection: it mimics production, so it must refuse what
    # production refuses.
    if not _is_scoped_per_connection(_current_plan()):
        return

    raise SepalSessionError(
        "A GEEInterface built with no session resolves the machine's own Earth "
        "Engine credentials, and this runtime serves one identity per connection "
        "-- so it would answer with the container's platform service account "
        "instead of this user. Build it from the connection's session with "
        "get_current_gee_interface(), pass it down to the component explicitly, "
        "or turn Earth Engine off for the component that does not need it (for "
        "example SepalMap(gee=False))."
    )


def _resolve_create_folder_paths(asset_root: str, folder_path: str) -> tuple[str, str]:
    """Normalize folder creation paths for both session and legacy EE clients.

    Accepts either a path relative to ``asset_root`` or an absolute
    ``projects/.../assets/...`` path, and rejects paths outside ``asset_root``.

    Args:
        asset_root: The user's current asset root (e.g. ``projects/foo/assets``).
        folder_path: Relative or absolute folder path requested by the caller.

    Returns:
        A tuple ``(relative_path, absolute_path)`` — the first suited to the
        session client, the second to the legacy ``ee.data.createAsset`` API.

    Raises:
        ValueError: If ``folder_path`` resolves outside ``asset_root``.
    """
    root = PurePosixPath(str(asset_root).rstrip("/"))
    requested = (folder_path or "").strip().strip("/")

    if not requested:
        return "", str(root)

    requested_path = PurePosixPath(requested)
    absolute_path = (
        str(requested_path) if requested.startswith("projects/") else str(root / requested_path)
    )

    absolute_parts = PurePosixPath(absolute_path).parts
    root_parts = root.parts
    if absolute_parts[: len(root_parts)] != root_parts:
        raise ValueError(f"Folder `{folder_path}` is outside the current asset root `{root}`.")

    relative_parts = absolute_parts[len(root_parts) :]
    relative_path = str(PurePosixPath(*relative_parts)) if relative_parts else ""
    return relative_path, absolute_path


def _bbox_geometry(item: ee.ComputedObject) -> ee.Geometry:
    """Build the bounding-box geometry of an Earth Engine object without dissolving.

    ``ee.FeatureCollection.geometry()`` unions every feature into a single
    geometry, which trips Earth Engine's hard 2M-edge limit on dense
    collections. Reducing each feature to its own bounding box *first* yields an
    identical extent while keeping every intermediate geometry tiny (#996).

    Assumes no single feature on its own exceeds the 2M-edge limit.

    Args:
        item: an ``ee.Geometry``, ``ee.Feature``, ``ee.FeatureCollection`` or
            ``ee.Image`` (or subclass).

    Returns:
        the bounding-box geometry of ``item``.
    """
    if isinstance(item, ee.Geometry):
        geom = item
    elif isinstance(item, ee.FeatureCollection):
        # reduce each feature to its bbox before unioning (avoids the dissolve)
        geom = item.map(lambda f: ee.Feature(f.geometry().bounds())).geometry()
    else:
        # ee.Image / ee.Feature: a single geometry, no collection to dissolve
        geom = item.geometry()
    return geom.bounds()


class GEEInterface:
    def __init__(self, session: Optional[EESession] = None):
        """A unified interface for Earth Engine operations.

        If a session is provided at initialization, custom EESession-based calls are used.
        Otherwise, the default Earth Engine API methods are invoked.

        Args:
            session: The session every call is made on behalf of. Omitting it
                resolves one from the machine's own credentials, which is only
                accepted where topology says the process serves a single
                identity -- see :func:`_refuse_ambient_session_per_connection`.
        """
        # Before the loop thread below: a refused interface must not leak one.
        # Topology is decided here, eagerly; the credentials themselves are not.
        if session is None:
            _refuse_ambient_session_per_connection()

        self._session = session
        self._session_lock = threading.Lock()
        self._closed = False

        self._async_loop = asyncio.new_event_loop()
        self._async_loop.set_debug(True)  # Enable debug mode for the event loop
        self._async_thread = threading.Thread(target=self._async_loop.run_forever, daemon=True)
        self._async_thread.start()

    @property
    def session(self) -> EESession:
        """The session every call is made on behalf of, resolved on first use.

        Deliberately not resolved in ``__init__``. Resolution reads the machine's
        credential store, and constructing an interface must not require Earth
        Engine to be set up at all: ``SepalMap()`` is the documented notebook
        quickstart, 84 test sites build one without ever calling Earth Engine,
        and the unit lane runs on fork PRs where ``EARTHENGINE_TOKEN`` is empty.
        Resolving eagerly turns all three into ``CredentialsResolutionError`` at
        construction. Whether the machine's credentials may be read *at all* is a
        topology question, and that one is still answered eagerly, in ``__init__``.

        Returns:
            The session. Built from the machine's own credentials on first
            access when the caller supplied none.
        """
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    self._session = EESession.from_default(allow_service_account_file=False)
        return self._session

    def create_task(
        self,
        func: Callable[..., Coroutine[Any, Any, R]],
        key: Optional[str] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_done: Optional[Callable[[R], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        on_finally: Optional[Callable[[], None]] = None,
    ) -> GEETask[R]:
        """Factory for GEETask bound to this interface's loop, with callbacks wired."""
        task = GEETask(loop=self._async_loop, function=func, key=key, on_finally=on_finally)

        if on_progress:
            task.observe(
                lambda change: on_progress(change["new"], task.message),
                names="progress",
            )
        if on_done:

            def _done(change):
                if change["new"] is TaskState.FINISHED:
                    on_done(task.result)

            task.observe(_done, names="state")
        if on_error:

            def _err(change):
                if change["new"] is TaskState.ERROR:
                    on_error(task.error)

            task.observe(_err, names="state")

        return task

    def _log_thread_info(self, operation: str) -> None:
        """Log information about current thread context for debugging."""
        threading.current_thread()
        threading.main_thread()
        # log.debug(
        #     f"[{operation}] Current thread: {current_thread.name} (ID: {current_thread.ident})"
        # )
        # log.debug(f"[{operation}] Main thread: {main_thread.name} (ID: {main_thread.ident})")
        log.debug(
            f"[{operation}] GEEIterface ID: {id(self)} || GEE thread: {self._async_thread.name} (ID: {self._async_thread.ident})"
        )

    def _run_async_blocking(self, coro: Coroutine, timeout: Optional[float] = 305.0) -> Any:
        """Schedule `coro` in our private loop, block until done."""
        if self._closed:
            raise RuntimeError("GEEInterface is closed")

        # Check for potential deadlock: if we're already running in the GEE async thread,
        # calling run_coroutine_threadsafe on the same loop will deadlock
        current_thread = threading.current_thread()
        if current_thread.ident == self._async_thread.ident:
            raise RuntimeError(
                f"Deadlock detected: Cannot call blocking GEEInterface method from within "
                f"an async function running on the same event loop. "
                f"Current thread: {current_thread.name} (ID: {current_thread.ident}) "
                f"is the same as GEE async thread: {self._async_thread.name} (ID: {self._async_thread.ident}). "
                f"Use the async version of this method instead (e.g., get_info_async instead of get_info)."
            )

        operation = str(coro).split("(")[0].split(".")[-1] if "(" in str(coro) else str(coro)
        self._log_thread_info(f"STARTING {operation}")

        log.debug(f"Running sync coroutine: {coro}")

        try:
            future = asyncio.run_coroutine_threadsafe(coro, self._async_loop)
            result = future.result(timeout=timeout)
            log.debug(f"Sync coroutine completed successfully: {operation}")
            return result
        except asyncio.TimeoutError as e:
            log.error(f"Timeout ({timeout}s) running coroutine: {operation}")
            log.error(f"Traceback: {traceback.format_exc()}")
            # Cancel the future to clean up
            future.cancel()
            raise TimeoutError(f"Operation {operation} timed out after {timeout} seconds") from e
        except Exception as e:
            log.error(f"Error running sync coroutine {operation}: {type(e).__name__}: {e}")
            log.error(f"Full traceback: {traceback.format_exc()}")
            self._log_thread_info(f"ERROR in {operation}")
            # Re-raise the original exception to preserve the stack trace
            raise

    async def get_info_async(
        self, ee_object: ee.ComputedObject = None, tag: Any = None, serialized_object=None
    ) -> Dict:
        """Asynchronously get_info for an Earth Engine object."""
        try:
            return await self.session.operations.get_info_async(
                ee_object, tag, serialized_object=serialized_object
            )
        except Exception as e:
            log.error(f"Failed to get info for EE object: {type(e).__name__}: {e}")
            raise

    async def get_info_batch_async(self, ee_objects: List[ee.ComputedObject]) -> List:
        """Asynchronously get info for multiple Earth Engine objects in batch."""
        tasks = [self.get_info_async(obj) for obj in ee_objects]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def get_info_batch(
        self, ee_objects: List[ee.ComputedObject], timeout: Optional[float] = 305.0
    ) -> List:
        """Synchronously get info for multiple Earth Engine objects in batch."""
        return self._run_async_blocking(self.get_info_batch_async(ee_objects), timeout)

    async def get_bounds_async(self, item: ee.ComputedObject) -> Tuple[float, float, float, float]:
        """Asynchronously compute the extent of an Earth Engine object.

        Dense feature collections are reduced per-feature to avoid Earth Engine's
        2M-edge limit on ``FeatureCollection.geometry()`` (issue #996).

        Args:
            item: an ``ee.Geometry``, ``ee.Feature``, ``ee.FeatureCollection`` or
                ``ee.Image``.

        Returns:
            the bounding box as ``(minx, miny, maxx, maxy)``.
        """
        ring = _bbox_geometry(item).coordinates().get(0)
        coords = await self.get_info_async(ring)
        return (coords[0][0], coords[0][1], coords[2][0], coords[2][1])

    async def get_map_id_async(
        self,
        ee_image: ee.Image,
        vis_params: Optional[MapTileOptions] = None,
        bands: Optional[str] = None,
        format: Optional[str] = None,
    ) -> Dict:
        """Asynchronously get map ID for an Earth Engine image."""
        try:
            return await self.session.operations.get_map_id_async(
                ee_image, vis_params, bands, format
            )
        except Exception as e:
            log.error(f"Failed to get map ID for EE image: {type(e).__name__}: {e}")
            raise

    async def get_asset_async(self, asset_id: str, not_exists_ok: bool = False) -> Dict:
        """Asynchronously get an asset by its ID."""
        try:
            return await self.session.operations.get_asset_async(asset_id, not_exists_ok)
        except Exception as e:
            log.error(f"Failed to get asset {asset_id}: {type(e).__name__}: {e}")
            if not_exists_ok:
                return None
            raise

    async def get_assets_async(self, folder: str = "") -> List[Dict]:
        """Asynchronously get assets in a specified folder."""
        return await self.session.operations.get_assets_async(folder)

    async def get_folder_async(self) -> str:
        """Asynchronously get the assets folder path."""
        return await self.session.get_assets_folder()

    async def export_table_to_asset_async(
        self,
        collection: ee.FeatureCollection,
        asset_id: str,
        description: str = "myExportTableTask",
        selectors: Optional[list] = None,
        max_vertices: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> str:
        """Asynchronously export a FeatureCollection to an asset."""
        return await self.session.export.table_to_asset_async(
            collection=collection,
            asset_id=asset_id,
            description=description,
            selectors=selectors,
            max_vertices=max_vertices,
            priority=priority,
        )

    async def export_table_to_drive_async(
        self,
        collection,
        file_format: TableFileFormat,
        filename_prefix: str = "",
        folder: Optional[str] = None,
        description: str = "myExportTableTask",
        selectors: Optional[list] = None,
        max_vertices: Optional[int] = None,
        priority: Optional[int] = None,
    ):
        """Asynchronously export a FeatureCollection to Google Drive."""
        return await self.session.export.table_to_drive_async(
            collection=collection,
            filename_prefix=filename_prefix,
            file_format=file_format,
            folder=folder,
            description=description,
            selectors=selectors,
            max_vertices=max_vertices,
            priority=priority,
        )

    async def is_running_async(self, name: str) -> bool:
        """Asynchronously check if a task is running by its name."""
        task = await self.session.tasks.get_task_by_name_async(name)
        # ee-client returns a pydantic ``Task``, whose state lives on its
        # metadata. This read used to be ``task["state"]``, which no caller ever
        # reached: every GEE-lane caller held a session-less interface and took
        # the deleted global-ee branch instead.
        return bool(task and task.metadata.state in ("RUNNING", "READY"))

    async def get_task_async(self, task_id: str) -> Optional[Task]:
        """Asynchronously get a task by its ID."""
        return await self.session.tasks.get_task_async(task_id)

    async def create_folder_async(self, folder_path: str) -> Dict:
        """Asynchronously create a folder in Earth Engine assets."""
        asset_root = await self.get_folder_async()
        relative_path, absolute_path = _resolve_create_folder_paths(asset_root, folder_path)

        if not relative_path:
            return {"id": absolute_path}
        return await self.session.operations.create_folder_async(relative_path)

    async def export_image_to_asset_async(
        self,
        image: ee.Image,
        asset_id: str,
        description: str = "myExportTableTask",
        max_pixels: Optional[int] = None,
        grid: Optional[dict] = None,
        request_id: Optional[str] = None,
        workload_tag: Optional[str] = None,
        priority: Optional[int] = None,
        region: Union[ee.Geometry, ee.Geometry.LinearRing, ee.Geometry.Polygon, str] = None,
        scale: Optional[float] = None,
        crs: Optional[str] = None,
        crs_transform: Optional[dict] = None,
    ) -> str:
        """Asynchronously export an image to an asset."""
        return await self.session.export.image_to_asset_async(
            image=image,
            asset_id=asset_id,
            description=description,
            max_pixels=max_pixels,
            grid=grid,
            request_id=request_id,
            workload_tag=workload_tag,
            priority=priority,
            region=region,
            scale=scale,
            crs=crs,
            crs_transform=crs_transform,
        )

    async def export_image_to_drive_async(
        self,
        image: ee.Image,
        description: str = "myExportImageTask",
        folder: Optional[str] = None,
        filename_prefix: Optional[str] = None,
        region: Optional[ee.Geometry] = None,
        scale: Optional[float] = None,
        crs: Optional[str] = None,
        crs_transform: Optional[List[float]] = None,
        max_pixels: Optional[int] = None,
        file_format: Optional[str] = ImageFileFormat.GEO_TIFF,
        priority: Optional[int] = None,
    ) -> str:
        """Asynchronously export an image to Google Drive."""
        return await self.session.export.image_to_drive_async(
            image=image,
            filename_prefix=filename_prefix,
            folder=folder,
            file_format=file_format,
            description=description,
            max_pixels=max_pixels,
            region=region,
            scale=scale,
            crs=crs,
            crs_transform=crs_transform,
            priority=priority,
        )

    # From here on, methods are blocking versions that run the async methods synchronously

    def get_info(
        self,
        ee_object: ee.ComputedObject = None,
        tag: Any = None,
        timeout: Optional[float] = None,
        serialized_object=None,
    ) -> Dict:
        """Get info for an Earth Engine object, blocking until done."""
        return self._run_async_blocking(
            self.get_info_async(ee_object, tag, serialized_object=serialized_object), timeout
        )

    def get_bounds(
        self, item: ee.ComputedObject, timeout: Optional[float] = None
    ) -> Tuple[float, float, float, float]:
        """Compute the extent of an Earth Engine object, blocking until done.

        Dense feature collections are reduced per-feature to avoid Earth Engine's
        2M-edge limit on ``FeatureCollection.geometry()`` (issue #996).

        Args:
            item: an ``ee.Geometry``, ``ee.Feature``, ``ee.FeatureCollection`` or
                ``ee.Image``.
            timeout: optional seconds to wait for the blocking call.

        Returns:
            the bounding box as ``(minx, miny, maxx, maxy)``.
        """
        return self._run_async_blocking(self.get_bounds_async(item), timeout)

    def get_map_id(
        self,
        ee_image: ee.Image,
        vis_params: Optional[MapTileOptions] = None,
        bands: Optional[str] = None,
        format: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict:
        """Get map ID for an Earth Engine image, blocking until done."""
        return self._run_async_blocking(
            self.get_map_id_async(ee_image, vis_params, bands, format), timeout
        )

    def get_asset(self, asset_id: str, not_exists_ok: bool = False) -> Dict:
        """Get an asset by its ID, blocking until done."""
        return self._run_async_blocking(self.get_asset_async(asset_id, not_exists_ok))

    def get_assets(self, folder: str = "") -> Dict:
        """Get assets in a specified folder, blocking until done."""
        return self._run_async_blocking(self.get_assets_async(folder))

    def get_folder(self) -> str:
        """Get the assets folder path, blocking until done."""
        return self._run_async_blocking(self.get_folder_async())

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by its ID, blocking until done."""
        return self._run_async_blocking(self.get_task_async(task_id))

    def export_table_to_asset(
        self,
        collection: ee.FeatureCollection,
        asset_id: str,
        description: str = "myExportTableTask",
        selectors: Optional[list] = None,
        max_vertices: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> str:
        """Export a FeatureCollection to an asset, blocking until done."""
        return self._run_async_blocking(
            self.export_table_to_asset_async(
                collection=collection,
                asset_id=asset_id,
                description=description,
                selectors=selectors,
                max_vertices=max_vertices,
                priority=priority,
            )
        )

    def export_table_to_drive(
        self,
        collection,
        fileFormat: TableFileFormat,  # camelCase to match earthengine API
        fileNamePrefix: str = "",
        folder: Optional[str] = None,
        description: str = "myExportTableTask",
        selectors: Optional[list] = None,
        max_vertices: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> str:
        """Export a FeatureCollection to Google Drive, blocking until done."""
        return self._run_async_blocking(
            self.export_table_to_drive_async(
                collection=collection,
                filename_prefix=fileNamePrefix,
                file_format=fileFormat,
                folder=folder,
                description=description,
                selectors=selectors,
                max_vertices=max_vertices,
                priority=priority,
            )
        )

    def is_running(self, asset_name: str) -> bool:
        """Check if a task is running by its name, blocking until done."""
        return self._run_async_blocking(self.is_running_async(asset_name))

    def create_folder(self, folder_path: str) -> Dict:
        """Create a folder in Earth Engine assets, blocking until done."""
        return self._run_async_blocking(self.create_folder_async(folder_path))

    def export_image_to_asset(
        self,
        image: ee.Image,
        asset_id: str,
        description: str = "myExportImageTask",
        region: Optional[ee.Geometry] = None,
        scale: Optional[float] = None,
        crs: Optional[str] = None,
        crs_transform: Optional[List[float]] = None,
        max_pixels: Optional[int] = None,
        priority: Optional[int] = None,
    ) -> str:
        """Export an image to an asset, blocking until done."""
        return self._run_async_blocking(
            self.export_image_to_asset_async(
                image=image,
                asset_id=asset_id,
                description=description,
                region=region,
                scale=scale,
                crs=crs,
                crs_transform=crs_transform,
                max_pixels=max_pixels,
                priority=priority,
            )
        )

    def export_image_to_drive(
        self,
        image: ee.Image,
        description: str = "myExportImageTask",
        folder: Optional[str] = None,
        filename_prefix: Optional[str] = None,
        region: Optional[ee.Geometry] = None,
        scale: Optional[float] = None,
        crs: Optional[str] = None,
        crs_transform: Optional[List[float]] = None,
        max_pixels: Optional[int] = None,
        file_format: Optional[str] = ImageFileFormat.GEO_TIFF,
        priority: Optional[int] = None,
    ) -> str:
        """Export an image to Google Drive, blocking until done."""
        return self._run_async_blocking(
            self.export_image_to_drive_async(
                image=image,
                description=description,
                folder=folder,
                filename_prefix=filename_prefix,
                region=region,
                scale=scale,
                crs=crs,
                crs_transform=crs_transform,
                max_pixels=max_pixels,
                file_format=file_format,
                priority=priority,
            )
        )

    def close(self) -> None:
        """Close the GEEInterface and clean up resources."""
        if self._closed:
            return

        self._closed = True
        log.debug(f"Closing GEEInterface... {id(self)}")

        try:
            # Close the EESession HTTP client on the session's own loop BEFORE
            # stopping it: the httpx AsyncClient (HTTP/2 pool, sockets, TLS
            # state) must be released deterministically on kernel cull, not
            # whenever the garbage collector gets to it.
            if (
                getattr(self, "_session", None) is not None
                and hasattr(self._session, "aclose")
                and hasattr(self, "_async_loop")
                and self._async_loop.is_running()
            ):
                future = asyncio.run_coroutine_threadsafe(self._session.aclose(), self._async_loop)
                try:
                    future.result(timeout=5.0)
                except Exception as e:
                    log.warning(f"Failed to close EESession HTTP client: {e}")

            if hasattr(self, "_async_loop") and self._async_loop.is_running():
                self._async_loop.call_soon_threadsafe(self._async_loop.stop)
                if hasattr(self, "_async_thread") and self._async_thread.is_alive():
                    self._async_thread.join(timeout=5.0)
                    if self._async_thread.is_alive():
                        log.warning("Background thread did not stop within timeout")
                if not self._async_loop.is_closed():
                    self._async_loop.close()

            log.debug("GEEInterface closed successfully")
        except Exception as e:
            log.error(f"Error during GEEInterface cleanup: {e}")

    def __enter__(self):
        """Support for context manager protocol."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support for context manager protocol - automatically close resources."""
        self.close()

    def __del__(self):
        """Destructor to ensure resources are cleaned up."""
        try:
            if not self._closed:
                self.close()
        except Exception:
            # Ignore errors during cleanup in destructor
            pass
