"""Async export engine for Earth Engine, Google Drive, and SEPAL."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import Awaitable, Callable, Optional

import httpx
from eeclient.exceptions import EERestException
from pysepal_api import AsyncSepalClient, SepalClient
from pysepal_api.paths import sanitize_write_path

from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface

from . import drive
from .models import (
    FAILED_TASK_STATES,
    REMOTE_CANCEL_TIMEOUT_SECONDS,
    SUCCESS_TASK_STATES,
    ExportBackend,
    ExportRequest,
    ExportResult,
    RemoteCancelCallback,
    RemoteCancelOutcome,
    RemoteSubmittedCallback,
    StatusCallback,
    _build_result_message,
    extract_task_id,
    get_task_state_name,
    notify,
    resolve_sepal_folder,
    validate_asset_id_under_root,
)
from .prepare import prepared_image
from .taskmanager import select_backend, submit_taskmanager_export

# ee-client retries these, so an earlier attempt may have created the task.
_RETRIED_EE_CODES = frozenset({401, 429})


class _RemoteExportFailed(RuntimeError):
    """The Earth Engine task ended in a failed state and will write nothing more."""


async def _ensure_asset_folder_exists(
    gee_interface: GEEInterface,
    folder_path: str,
) -> None:
    """Create missing folders below the user's asset root before export."""
    path = PurePosixPath(folder_path.rstrip("/"))
    if "assets" not in path.parts:
        return

    root_index = path.parts.index("assets")
    current = PurePosixPath(*path.parts[: root_index + 1])

    for part in path.parts[root_index + 1 :]:
        current = current / part
        asset_info = await gee_interface.get_asset_async(str(current), not_exists_ok=True)
        if asset_info is None:
            await gee_interface.create_folder_async(str(current))


async def _wait_for_remote_completion(
    gee_interface: GEEInterface,
    *,
    task_id: Optional[str],
    description: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
    on_update: StatusCallback = None,
) -> None:
    """Wait for an Earth Engine export to finish running remotely."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    previous_state = None

    while True:
        if loop.time() > deadline:
            raise TimeoutError(f"Timed out while waiting for Earth Engine export `{description}`.")

        state = None
        if task_id:
            task = await gee_interface.get_task_async(task_id)
            state = get_task_state_name(task)
        else:
            if not await gee_interface.is_running_async(description):
                return
            state = "RUNNING"

        if state and state != previous_state:
            notify(on_update, f"Waiting for Earth Engine ({state.lower()})")
            previous_state = state

        if state in SUCCESS_TASK_STATES:
            return
        # Earth Engine may still write after CANCEL_REQUESTED; wait for CANCELLED.
        if state in FAILED_TASK_STATES and state != "CANCEL_REQUESTED":
            raise _RemoteExportFailed(
                f"Earth Engine export `{description}` finished with state `{state}`."
            )
        await asyncio.sleep(poll_interval_seconds)


async def cancel_export_task(
    gee_interface: GEEInterface,
    task_id: Optional[str],
) -> RemoteCancelOutcome:
    """Cancel the Earth Engine task of an export, unless it has already ended.

    Never raises: a failure is returned as a ``"failed"`` outcome, so the
    caller can report it and still finish its own cancel.
    """
    if not task_id:
        return RemoteCancelOutcome(
            task_id=None, status="failed", error="Earth Engine returned no task id."
        )

    async def _ended_state() -> Optional[str]:
        state = get_task_state_name(await gee_interface.get_task_async(task_id))
        return state if state in SUCCESS_TASK_STATES | FAILED_TASK_STATES else None

    async def _cancel() -> RemoteCancelOutcome:
        state = await _ended_state()
        if state is not None:
            return RemoteCancelOutcome(task_id=task_id, status="finished", state=state)
        try:
            await gee_interface.cancel_task_async(task_id)
        except Exception:
            # Earth Engine refuses to cancel a task that ended after the read.
            state = await _ended_state()
            if state is None:
                raise
            return RemoteCancelOutcome(task_id=task_id, status="finished", state=state)
        return RemoteCancelOutcome(task_id=task_id, status="cancelled")

    try:
        return await asyncio.wait_for(_cancel(), REMOTE_CANCEL_TIMEOUT_SECONDS)
    except Exception as exc:
        return RemoteCancelOutcome(
            task_id=task_id, status="failed", error=str(exc) or type(exc).__name__
        )


def _created_no_task(exc: Exception) -> bool:
    """Whether a failed Earth Engine submission certainly created no task.

    Transport errors, timeouts and 5xx responses leave the outcome unknown. Any
    other error is a 4xx rejection or failed locally before the request.
    """
    if isinstance(exc, EERestException):
        return (
            isinstance(exc.code, int)
            and 400 <= exc.code < 500
            and exc.code not in _RETRIED_EE_CODES
        )
    return not isinstance(exc, (httpx.HTTPError, OSError, asyncio.TimeoutError))


async def _submit_export(
    gee_interface: GEEInterface,
    request: ExportRequest,
    *,
    asset_id: Optional[str] = None,
    drive_folder: Optional[str] = None,
) -> object:
    """Dispatch the export submission through ``GEEInterface``."""
    if request.export_kind == "image":
        image_to_export = prepared_image(request)
        if request.target == "gee":
            return await gee_interface.export_image_to_asset_async(
                image=image_to_export,
                asset_id=asset_id or "",
                description=request.name,
                region=request.region,
                scale=request.scale,
                max_pixels=request.max_pixels,
                priority=request.priority,
            )

        return await gee_interface.export_image_to_drive_async(
            image=image_to_export,
            description=request.name,
            folder=drive_folder,
            filename_prefix=request.name,
            region=request.region,
            scale=request.scale,
            max_pixels=request.max_pixels,
            priority=request.priority,
            file_format=request.image_file_format,
        )

    if request.target == "gee":
        return await gee_interface.export_table_to_asset_async(
            collection=request.ee_object,
            asset_id=asset_id or "",
            description=request.name,
            selectors=list(request.selectors) if request.selectors else None,
            max_vertices=request.max_vertices,
            priority=request.priority,
        )

    return await gee_interface.export_table_to_drive_async(
        collection=request.ee_object,
        description=request.name,
        folder=drive_folder,
        filename_prefix=request.name,
        file_format=request.table_file_format,
        selectors=list(request.selectors) if request.selectors else None,
        max_vertices=request.max_vertices,
        priority=request.priority,
    )


async def _submit_remote(
    gee_interface: GEEInterface,
    request: ExportRequest,
    *,
    asset_id: Optional[str] = None,
    drive_folder: Optional[str] = None,
    on_remote_submitted: RemoteSubmittedCallback,
    on_cancel: Callable[[Optional[str]], Awaitable[None]],
) -> Optional[str]:
    """Submit the export and return its task id, cancelling the task on a cancel."""
    submission = asyncio.ensure_future(
        _submit_export(gee_interface, request, asset_id=asset_id, drive_folder=drive_folder)
    )
    try:
        task_or_id = await asyncio.shield(submission)
    except asyncio.CancelledError:
        # The request may reach Earth Engine after the cancel: let it settle,
        # so the task it creates is cancelled too.
        done, _pending = await asyncio.wait({submission}, timeout=REMOTE_CANCEL_TIMEOUT_SECONDS)
        if not done:
            submission.cancel()
            await on_cancel(None)
        elif not submission.cancelled() and submission.exception() is None:
            task_id = extract_task_id(submission.result())
            notify(on_remote_submitted, task_id)
            await on_cancel(task_id)
        raise

    task_id = extract_task_id(task_or_id)
    notify(on_remote_submitted, task_id)
    return task_id


async def submit_export_request(
    request: ExportRequest,
    *,
    gee_interface: GEEInterface,
    drive_interface: GDriveInterface | None,
    sepal_client: SepalClient | None,
    async_sepal_client: AsyncSepalClient | None = None,
    backend: ExportBackend = "auto",
    on_step: StatusCallback = None,
    on_update: StatusCallback = None,
    on_remote_submitted: RemoteSubmittedCallback = None,
    on_remote_cancel: RemoteCancelCallback = None,
) -> ExportResult:
    """Submit an export request without any Solara-specific behavior.

    ``backend="auto"`` considers TaskManager only when ``async_sepal_client``
    is given (see ``select_backend``); the ``PYSEPAL_TASKMANAGER_EXPORTS`` flag
    applies to the dialog only.

    A cancel of this coroutine after the submission started also cancels the
    remote task. For a direct SEPAL export whose Earth Engine task had already
    finished, it deletes the Google Drive staging folder when
    ``request.cleanup_drive_after_sepal`` is set. ``on_remote_cancel`` then gets
    a :class:`RemoteCancelOutcome`, before the ``CancelledError`` propagates.
    """
    cleanup_folder_id: Optional[str] = None

    async def _cancel_remote(task_id: Optional[str], *, remote_done: bool = False) -> None:
        if remote_done:
            outcome = RemoteCancelOutcome(task_id=task_id, status="finished", state="COMPLETED")
        else:
            outcome = await cancel_export_task(gee_interface, task_id)

        if (
            cleanup_folder_id is not None
            and drive_interface is not None
            and request.cleanup_drive_after_sepal
            and outcome.status == "finished"
            and outcome.state in SUCCESS_TASK_STATES
        ):
            try:
                items = await asyncio.to_thread(
                    drive.find_items, drive_interface, cleanup_folder_id
                )
                await asyncio.to_thread(drive.delete_folder, drive_interface, cleanup_folder_id)
                outcome = replace(
                    outcome, deleted_drive_items=tuple(item["name"] for item in items)
                )
            except Exception as exc:
                outcome = replace(outcome, drive_cleanup_error=str(exc) or type(exc).__name__)

        notify(on_remote_cancel, outcome)

    notify(on_step, "Validating export settings")

    selected = select_backend(
        backend,
        request,
        sepal_client=sepal_client,
        async_sepal_client=async_sepal_client,
        opted_in=False,
    )
    if selected == "taskmanager":
        return await submit_taskmanager_export(
            request,
            async_sepal_client,
            sepal_client=sepal_client,
            on_step=on_step,
            on_update=on_update,
            on_remote_submitted=on_remote_submitted,
            on_remote_cancel=on_remote_cancel,
        )
    if request.target == "gee":
        notify(on_step, "Preparing Earth Engine destination")
        asset_id = (request.gee_asset_id or "").strip()
        if not asset_id:
            raise ValueError("Earth Engine export requires an asset id.")

        root_folder = await gee_interface.get_folder_async()
        root_error = validate_asset_id_under_root(asset_id, str(root_folder or ""))
        if root_error:
            raise ValueError(root_error)

        existing = await gee_interface.get_asset_async(asset_id, not_exists_ok=True)
        if existing is not None:
            raise FileExistsError(
                f"An Earth Engine asset already exists at `{asset_id}`. "
                "Edit the asset id or pick a different path."
            )

        asset_folder = str(PurePosixPath(asset_id).parent)
        await _ensure_asset_folder_exists(gee_interface, asset_folder)

        notify(on_step, "Submitting Earth Engine export")
        task_id = await _submit_remote(
            gee_interface,
            request,
            asset_id=asset_id,
            on_remote_submitted=on_remote_submitted,
            on_cancel=_cancel_remote,
        )
        result = ExportResult(
            target="gee",
            export_kind=request.export_kind,
            name=request.name,
            task_id=task_id,
            asset_id=asset_id,
            message="",
        )
        return replace(result, message=_build_result_message(result))

    if request.target == "drive":
        notify(on_step, "Submitting Google Drive export")
        task_id = await _submit_remote(
            gee_interface,
            request,
            drive_folder=request.drive_folder or None,
            on_remote_submitted=on_remote_submitted,
            on_cancel=_cancel_remote,
        )
        result = ExportResult(
            target="drive",
            export_kind=request.export_kind,
            name=request.name,
            task_id=task_id,
            drive_folder=request.drive_folder,
            message="",
        )
        return replace(result, message=_build_result_message(result))

    if sepal_client is None:
        raise ValueError("SEPAL export requires a session-backed SepalClient.")
    if drive_interface is None:
        raise ValueError("Direct workspace exports require a Google Drive interface.")
    if sepal_client.results_path is None:
        raise ValueError("Workspace exports require a module results directory.")
    destination_folder = resolve_sepal_folder(sepal_client, request.sepal_folder)
    sanitize_write_path(destination_folder)

    # Earth Engine writes into an existing Drive folder with the given name, so
    # a unique, pre-created leaf keeps lookup and cleanup inside it.
    staging_name = f"{request.name}_{datetime.now():%Y-%m-%d_%H:%M:%S.%f}"
    staging_id = await asyncio.to_thread(drive.create_staging_folder, drive_interface, staging_name)
    # The cancel path reads it to delete the folder of a finished task.
    cleanup_folder_id = staging_id
    notify(on_step, "Submitting Google Drive export")
    try:
        task_id = await _submit_remote(
            gee_interface,
            request,
            drive_folder=staging_name,
            on_remote_submitted=on_remote_submitted,
            on_cancel=_cancel_remote,
        )
    except Exception as exc:
        # With no task, nothing will ever land in the folder, whatever the cleanup setting.
        if _created_no_task(exc):
            await drive.discard_folder(drive_interface, staging_id)
        raise

    remote_done = False
    try:
        notify(on_step, "Waiting for Earth Engine export to finish")
        try:
            await _wait_for_remote_completion(
                gee_interface,
                task_id=task_id,
                description=request.name,
                poll_interval_seconds=request.poll_interval_seconds,
                timeout_seconds=request.timeout_seconds,
                on_update=on_update,
            )
        except _RemoteExportFailed:
            if request.cleanup_drive_after_sepal:
                await drive.discard_folder(drive_interface, staging_id)
            raise
        remote_done = True

        notify(on_step, "Copying Drive files into SEPAL")
        drive_items = await drive.wait_for_items(
            drive_interface,
            name=request.name,
            folder_id=staging_id,
            poll_interval_seconds=request.poll_interval_seconds,
            timeout_seconds=request.timeout_seconds,
            on_update=on_update,
        )

        # A cancel does not stop this thread. It runs to its end, or fails
        # when the cancel deletes the staging files it downloads.
        sepal_paths = await asyncio.to_thread(
            drive.copy_items_to_sepal,
            drive_interface,
            sepal_client,
            drive_items,
            destination_folder,
        )
    except asyncio.CancelledError:
        await _cancel_remote(task_id, remote_done=remote_done)
        raise

    cleanup_warning = None
    if request.cleanup_drive_after_sepal:
        notify(on_step, "Cleaning up Google Drive staging files")
        try:
            await asyncio.to_thread(drive.delete_folder, drive_interface, staging_id)
        except Exception as exc:  # pragma: no cover - defensive cleanup path
            cleanup_warning = str(exc)

    result = ExportResult(
        target="sepal",
        status="completed",
        export_kind=request.export_kind,
        name=request.name,
        task_id=task_id,
        drive_folder=str(PurePosixPath(*drive.STAGING_ROOT, staging_name)),
        drive_items=tuple(item["name"] for item in drive_items),
        sepal_paths=sepal_paths,
        message="",
    )
    message = _build_result_message(result)
    if cleanup_warning:
        message += (
            " The export was copied successfully, but Google Drive cleanup failed: "
            f"{cleanup_warning}"
        )
    return replace(result, message=message)


__all__ = ["cancel_export_task", "submit_export_request"]
