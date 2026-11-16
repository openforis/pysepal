"""Async export engine for Earth Engine, Google Drive, and SEPAL."""

from __future__ import annotations

import asyncio
import io
from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import Awaitable, Callable, Optional, Sequence

from googleapiclient.http import MediaIoBaseDownload
from pysepal_api import SepalClient

from pysepal.mapping.visualization import set_viz_params
from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface

from .export_models import (
    FAILED_TASK_STATES,
    SUCCESS_TASK_STATES,
    ExportRequest,
    ExportResult,
    RemoteCancelOutcome,
    _build_result_message,
    extract_task_id,
    get_task_state_name,
    matches_drive_export_prefix,
    resolve_sepal_folder,
    validate_asset_id_under_root,
)

StatusCallback = Optional[Callable[[str], None]]
RemoteSubmittedCallback = Optional[Callable[[Optional[str]], None]]
RemoteCancelCallback = Optional[Callable[[RemoteCancelOutcome], None]]

# Upper bound on the Earth Engine calls made after a cancel, so a slow or
# unreachable API cannot keep a cancelled export alive.
REMOTE_CANCEL_TIMEOUT_SECONDS = 60.0


def _notify(callback: StatusCallback, message: str) -> None:
    if callback is not None:
        callback(message)


def _parse_drive_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
            _notify(on_update, f"Waiting for Earth Engine ({state.lower()})")
            previous_state = state

        if state in SUCCESS_TASK_STATES:
            return
        if state in FAILED_TASK_STATES:
            raise RuntimeError(
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


def _escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_drive_items_by_prefix(
    drive_interface: GDriveInterface,
    prefix: str,
    modified_after: Optional[datetime] = None,
) -> list[dict]:
    """Find Drive files that belong to an export prefix."""
    items: list[dict] = []
    page_token = None
    query = f"trashed = false and name contains '{_escape_drive_query(prefix)}'"
    fields = "nextPageToken, files(id, name, mimeType, modifiedTime)"

    while True:
        response = (
            drive_interface.service.files()
            .list(
                q=query,
                pageToken=page_token,
                pageSize=200,
                fields=fields,
            )
            .execute()
        )
        items.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    matched = []
    for item in items:
        filename = item.get("name", "")
        if not matches_drive_export_prefix(filename, prefix):
            continue

        modified = _parse_drive_timestamp(item.get("modifiedTime"))
        if modified_after and modified and modified < modified_after:
            continue

        matched.append(item)

    return sorted(matched, key=lambda item: item["name"])


def _download_drive_item_bytes(drive_interface: GDriveInterface, item_id: str) -> bytes:
    request = drive_interface.service.files().get_media(fileId=item_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _status, done = downloader.next_chunk()
    return fh.getvalue()


async def _wait_for_drive_items(
    drive_interface: GDriveInterface,
    *,
    prefix: str,
    modified_after: datetime,
    poll_interval_seconds: float,
    timeout_seconds: float,
    on_update: StatusCallback = None,
) -> list[dict]:
    """Wait until Drive files for an export prefix become visible."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while True:
        items = await asyncio.to_thread(
            _find_drive_items_by_prefix,
            drive_interface,
            prefix,
            modified_after,
        )
        if items:
            return items

        if loop.time() > deadline:
            raise FileNotFoundError(f"No Google Drive files were found for export `{prefix}`.")

        _notify(on_update, "Waiting for Google Drive files")
        await asyncio.sleep(poll_interval_seconds)


def _copy_drive_items_to_sepal(
    drive_interface: GDriveInterface,
    sepal_client: SepalClient,
    items: Sequence[dict],
    destination_folder: PurePosixPath,
) -> tuple[str, ...]:
    """Download Drive results and upload them into the SEPAL workspace."""
    created_folder = sepal_client.files.mkdir(str(destination_folder), parents=True)
    remote_root = PurePosixPath(sepal_client.BASE_REMOTE_PATH) / created_folder
    uploaded_paths = []

    for item in items:
        remote_path = remote_root / item["name"]
        payload = _download_drive_item_bytes(drive_interface, item["id"])
        sepal_client.files.write(str(remote_path), payload, overwrite=True)
        uploaded_paths.append(str(remote_path))

    return tuple(uploaded_paths)


def _delete_drive_items(drive_interface: GDriveInterface, items: Sequence[dict]) -> None:
    for item in items:
        drive_interface.service.files().delete(fileId=item["id"]).execute()


def _apply_viz_to_image(request: ExportRequest) -> object:
    """Return the export image with SEPAL visualization properties embedded.

    Apps that produce SEPAL-styled layers can pass ``vis_params`` on
    :class:`ResolvedExport` to keep the displayed styling on the exported asset.
    The properties are written via
    :func:`pysepal.mapping.visualization.set_viz_params` and survive on
    ``Export.image.toAsset`` outputs; Drive/SEPAL targets stage through a
    GeoTIFF where image properties become GDAL tags rather than EE properties,
    but applying them unconditionally is cheap and keeps downstream EE-asset
    consumers consistent.
    """
    if request.export_kind != "image" or not request.vis_params:
        return request.ee_object
    return set_viz_params(request.ee_object, **request.vis_params)


def _apply_band_selection(ee_object: object, request: ExportRequest) -> object:
    """Subset an image to the user-picked bands before export.

    Tables thread ``selectors`` directly through to the EE export call (where
    Earth Engine interprets them as feature property names). Images need an
    explicit ``image.select(...)`` because the image-export endpoints do not
    accept a selectors parameter — the band subset has to be baked into the
    image itself.
    """
    if request.export_kind != "image" or not request.selectors:
        return ee_object
    return ee_object.select(list(request.selectors))


async def _submit_export(
    gee_interface: GEEInterface,
    request: ExportRequest,
    *,
    asset_id: Optional[str] = None,
) -> object:
    """Dispatch the export submission through ``GEEInterface``."""
    if request.export_kind == "image":
        image_to_export = _apply_viz_to_image(request)
        image_to_export = _apply_band_selection(image_to_export, request)
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
            folder=request.drive_folder or None,
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
        folder=request.drive_folder or None,
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
    asset_id: Optional[str],
    on_remote_submitted: RemoteSubmittedCallback,
    on_cancel: Callable[[Optional[str]], Awaitable[None]],
) -> Optional[str]:
    """Submit the export and return its task id, cancelling the task on a cancel."""
    submission = asyncio.ensure_future(_submit_export(gee_interface, request, asset_id=asset_id))
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
            _notify(on_remote_submitted, task_id)
            await on_cancel(task_id)
        raise

    task_id = extract_task_id(task_or_id)
    _notify(on_remote_submitted, task_id)
    return task_id


async def submit_export_request(
    request: ExportRequest,
    *,
    gee_interface: GEEInterface,
    drive_interface: GDriveInterface,
    sepal_client: SepalClient | None,
    on_step: StatusCallback = None,
    on_update: StatusCallback = None,
    on_remote_submitted: RemoteSubmittedCallback = None,
    on_remote_cancel: RemoteCancelCallback = None,
) -> ExportResult:
    """Submit an export request without any Solara-specific behavior.

    A cancel of this coroutine after the submission started also cancels the
    Earth Engine task. For a SEPAL target whose Earth Engine task had already
    finished, it deletes the Google Drive staging files when
    ``request.cleanup_drive_after_sepal`` is set. ``on_remote_cancel`` then gets
    a :class:`RemoteCancelOutcome`, before the ``CancelledError`` propagates.
    """

    async def _cancel_remote(
        task_id: Optional[str],
        *,
        remote_done: bool = False,
        drive_items: Optional[Sequence[dict]] = None,
    ) -> None:
        if remote_done:
            outcome = RemoteCancelOutcome(task_id=task_id, status="finished", state="COMPLETED")
        else:
            outcome = await cancel_export_task(gee_interface, task_id)

        if (
            request.target == "sepal"
            and request.cleanup_drive_after_sepal
            and outcome.status == "finished"
            and outcome.state in SUCCESS_TASK_STATES
        ):
            try:
                if drive_items is None:
                    drive_items = await asyncio.to_thread(
                        _find_drive_items_by_prefix, drive_interface, request.name, started_at
                    )
                if drive_items:
                    await asyncio.to_thread(_delete_drive_items, drive_interface, drive_items)
                outcome = replace(
                    outcome, deleted_drive_items=tuple(item["name"] for item in drive_items)
                )
            except Exception as exc:
                outcome = replace(outcome, drive_cleanup_error=str(exc) or type(exc).__name__)

        _notify(on_remote_cancel, outcome)

    _notify(on_step, "Validating export settings")

    if request.target == "gee":
        _notify(on_step, "Preparing Earth Engine destination")
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

        _notify(on_step, "Submitting Earth Engine export")
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

    _notify(on_step, "Submitting Google Drive export")
    started_at = datetime.now().astimezone()
    task_id = await _submit_remote(
        gee_interface,
        request,
        asset_id=None,
        on_remote_submitted=on_remote_submitted,
        on_cancel=_cancel_remote,
    )

    if request.target == "drive":
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

    remote_done = False
    drive_items = None
    try:
        _notify(on_step, "Waiting for Earth Engine export to finish")
        await _wait_for_remote_completion(
            gee_interface,
            task_id=task_id,
            description=request.name,
            poll_interval_seconds=request.poll_interval_seconds,
            timeout_seconds=request.timeout_seconds,
            on_update=on_update,
        )
        remote_done = True

        _notify(on_step, "Copying Drive files into SEPAL")
        drive_items = await _wait_for_drive_items(
            drive_interface,
            prefix=request.name,
            modified_after=started_at,
            poll_interval_seconds=request.poll_interval_seconds,
            timeout_seconds=request.timeout_seconds,
            on_update=on_update,
        )

        destination_folder = resolve_sepal_folder(sepal_client, request.sepal_folder)
        # A cancel does not stop this thread. It runs to its end, or fails
        # when the cancel deletes the staging files it downloads.
        sepal_paths = await asyncio.to_thread(
            _copy_drive_items_to_sepal,
            drive_interface,
            sepal_client,
            drive_items,
            destination_folder,
        )
    except asyncio.CancelledError:
        await _cancel_remote(task_id, remote_done=remote_done, drive_items=drive_items)
        raise

    cleanup_warning = None
    if request.cleanup_drive_after_sepal:
        _notify(on_step, "Cleaning up Google Drive staging files")
        try:
            await asyncio.to_thread(_delete_drive_items, drive_interface, drive_items)
        except Exception as exc:  # pragma: no cover - defensive cleanup path
            cleanup_warning = str(exc)

    result = ExportResult(
        target="sepal",
        export_kind=request.export_kind,
        name=request.name,
        task_id=task_id,
        drive_folder=request.drive_folder,
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
