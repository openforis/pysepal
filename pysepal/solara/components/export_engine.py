"""Async export engine for Earth Engine, Google Drive, and SEPAL."""

from __future__ import annotations

import asyncio
import contextlib
import io
import threading
from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import Callable, Optional, Sequence

from googleapiclient.http import MediaIoBaseDownload
from pysepal_api import AsyncSepalClient, SepalClient

from pysepal.mapping.visualization import set_viz_params
from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface

from .export_models import (
    FAILED_TASK_STATES,
    SUCCESS_TASK_STATES,
    ExportBackend,
    ExportRequest,
    ExportResult,
    _build_result_message,
    extract_task_id,
    get_task_state_name,
    matches_drive_export_prefix,
    resolve_sepal_folder,
    validate_asset_id_under_root,
)
from .export_taskmanager import select_backend, submit_taskmanager_export

StatusCallback = Optional[Callable[[str], None]]
RemoteSubmittedCallback = Optional[Callable[[Optional[str]], None]]

_DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
_DRIVE_STAGING_ROOT = ("SEPAL", "exports")
# Parallel exports in one process would otherwise race to create duplicate
# SEPAL/exports parents.
_drive_staging_lock = threading.Lock()


def _notify(callback: StatusCallback, message: str) -> None:
    if callback is not None:
        callback(message)


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
            _notify(on_update, f"Waiting for Earth Engine ({state.lower()})")
            previous_state = state

        if state in SUCCESS_TASK_STATES:
            return
        if state in FAILED_TASK_STATES:
            raise _RemoteExportFailed(
                f"Earth Engine export `{description}` finished with state `{state}`."
            )
        await asyncio.sleep(poll_interval_seconds)


def _escape_drive_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_drive_child_folder(service, name: str, parent_id: str) -> Optional[str]:
    query = (
        f"name = '{_escape_drive_query(name)}' and mimeType = '{_DRIVE_FOLDER_MIME}' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    response = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _create_drive_folder(service, name: str, parent_id: str) -> str:
    body = {"name": name, "mimeType": _DRIVE_FOLDER_MIME, "parents": [parent_id]}
    return service.files().create(body=body, fields="id").execute()["id"]


def _create_drive_staging_folder(drive_interface: GDriveInterface, name: str) -> str:
    """Create ``SEPAL/exports/<name>`` in Drive, as SEPAL does, and return its id."""
    service = drive_interface.service
    parent_id = "root"
    with _drive_staging_lock:
        for part in _DRIVE_STAGING_ROOT:
            parent_id = _find_drive_child_folder(service, part, parent_id) or _create_drive_folder(
                service, part, parent_id
            )
    return _create_drive_folder(service, name, parent_id)


def _find_drive_items(
    drive_interface: GDriveInterface,
    prefix: str,
    folder_id: str,
) -> list[dict]:
    """Find the export's files in its staging folder."""
    items: list[dict] = []
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id, name, mimeType)"

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

    matched = [item for item in items if matches_drive_export_prefix(item.get("name", ""), prefix)]
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
    folder_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
    on_update: StatusCallback = None,
) -> list[dict]:
    """Wait until the export's files become visible in its staging folder."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while True:
        items = await asyncio.to_thread(_find_drive_items, drive_interface, prefix, folder_id)
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


def _delete_drive_folder(drive_interface: GDriveInterface, folder_id: str) -> None:
    drive_interface.service.files().delete(fileId=folder_id).execute()


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
    drive_folder: Optional[str] = None,
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
) -> ExportResult:
    """Submit an export request without any Solara-specific behavior.

    ``backend="auto"`` considers TaskManager only when ``async_sepal_client``
    is given (see ``select_backend``); the ``PYSEPAL_TASKMANAGER_EXPORTS`` flag
    applies to the dialog only.
    """
    _notify(on_step, "Validating export settings")

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
        )
    if request.target == "sepal" and sepal_client is None:
        raise ValueError("SEPAL export requires a session-backed SepalClient.")
    if request.target == "sepal" and drive_interface is None:
        raise ValueError("Direct workspace exports require a Google Drive interface.")

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
        submission = await _submit_export(gee_interface, request, asset_id=asset_id)
        task_id = extract_task_id(submission)
        _notify(on_remote_submitted, task_id)
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
    if request.target == "drive":
        submission = await _submit_export(
            gee_interface, request, drive_folder=request.drive_folder or None
        )
        task_id = extract_task_id(submission)
        _notify(on_remote_submitted, task_id)
        result = ExportResult(
            target="drive",
            export_kind=request.export_kind,
            name=request.name,
            task_id=task_id,
            drive_folder=request.drive_folder,
            message="",
        )
        return replace(result, message=_build_result_message(result))

    # Earth Engine writes into an existing Drive folder with the given name, so
    # a unique, pre-created leaf keeps lookup and cleanup inside it.
    staging_name = f"{request.name}_{datetime.now():%Y-%m-%d_%H:%M:%S.%f}"
    staging_id = await asyncio.to_thread(
        _create_drive_staging_folder, drive_interface, staging_name
    )
    submission = await _submit_export(gee_interface, request, drive_folder=staging_name)
    task_id = extract_task_id(submission)
    _notify(on_remote_submitted, task_id)

    _notify(on_step, "Waiting for Earth Engine export to finish")
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
            with contextlib.suppress(Exception):
                await asyncio.to_thread(_delete_drive_folder, drive_interface, staging_id)
        raise

    _notify(on_step, "Copying Drive files into SEPAL")
    drive_items = await _wait_for_drive_items(
        drive_interface,
        prefix=request.name,
        folder_id=staging_id,
        poll_interval_seconds=request.poll_interval_seconds,
        timeout_seconds=request.timeout_seconds,
        on_update=on_update,
    )

    destination_folder = resolve_sepal_folder(sepal_client, request.sepal_folder)
    sepal_paths = await asyncio.to_thread(
        _copy_drive_items_to_sepal,
        drive_interface,
        sepal_client,
        drive_items,
        destination_folder,
    )

    cleanup_warning = None
    if request.cleanup_drive_after_sepal:
        _notify(on_step, "Cleaning up Google Drive staging files")
        try:
            await asyncio.to_thread(_delete_drive_folder, drive_interface, staging_id)
        except Exception as exc:  # pragma: no cover - defensive cleanup path
            cleanup_warning = str(exc)

    result = ExportResult(
        target="sepal",
        status="completed",
        export_kind=request.export_kind,
        name=request.name,
        task_id=task_id,
        drive_folder=str(PurePosixPath(*_DRIVE_STAGING_ROOT, staging_name)),
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


__all__ = ["submit_export_request"]
