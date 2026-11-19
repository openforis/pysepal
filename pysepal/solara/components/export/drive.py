"""Google Drive staging for direct workspace exports, laid out as SEPAL does."""

from __future__ import annotations

import asyncio
import contextlib
import io
import threading
from pathlib import PurePosixPath
from typing import Optional, Sequence

from googleapiclient.http import MediaIoBaseDownload
from pysepal_api import SepalClient

from pysepal.scripts.drive_interface import GDriveInterface

from .models import StatusCallback, notify

_FOLDER_MIME = "application/vnd.google-apps.folder"
STAGING_ROOT = ("SEPAL", "exports")
# One user's parallel exports would otherwise race to create duplicate
# SEPAL/exports parents. Per user, so a hung Drive call blocks only its owner.
_staging_locks: dict[object, threading.Lock] = {}
_staging_locks_guard = threading.Lock()


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_child_folder(service, name: str, parent_id: str) -> Optional[str]:
    query = (
        f"name = '{_escape_query(name)}' and mimeType = '{_FOLDER_MIME}' "
        f"and '{parent_id}' in parents and trashed = false"
    )
    response = service.files().list(q=query, pageSize=1, fields="files(id)").execute()
    files = response.get("files", [])
    return files[0]["id"] if files else None


def _create_folder(service, name: str, parent_id: str) -> str:
    body = {"name": name, "mimeType": _FOLDER_MIME, "parents": [parent_id]}
    return service.files().create(body=body, fields="id").execute()["id"]


def _staging_lock(drive_interface: GDriveInterface) -> threading.Lock:
    user = getattr(drive_interface, "user", None) or id(drive_interface)
    with _staging_locks_guard:
        return _staging_locks.setdefault(user, threading.Lock())


def create_staging_folder(drive_interface: GDriveInterface, name: str) -> str:
    """Create ``SEPAL/exports/<name>`` in Drive, as SEPAL does, and return its id."""
    service = drive_interface.service
    parent_id = "root"
    with _staging_lock(drive_interface):
        for part in STAGING_ROOT:
            parent_id = _find_child_folder(service, part, parent_id) or _create_folder(
                service, part, parent_id
            )
    return _create_folder(service, name, parent_id)


def find_items(drive_interface: GDriveInterface, folder_id: str) -> list[dict]:
    """List the export's files: everything in its staging folder."""
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

    return sorted(items, key=lambda item: item["name"])


def _download_item_bytes(drive_interface: GDriveInterface, item_id: str) -> bytes:
    request = drive_interface.service.files().get_media(fileId=item_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        _status, done = downloader.next_chunk()
    return fh.getvalue()


async def wait_for_items(
    drive_interface: GDriveInterface,
    *,
    name: str,
    folder_id: str,
    poll_interval_seconds: float,
    timeout_seconds: float,
    on_update: StatusCallback = None,
) -> list[dict]:
    """Wait until the export's files become visible in its staging folder."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while True:
        items = await asyncio.to_thread(find_items, drive_interface, folder_id)
        if items:
            return items

        if loop.time() > deadline:
            raise FileNotFoundError(f"No Google Drive files were found for export `{name}`.")

        notify(on_update, "Waiting for Google Drive files")
        await asyncio.sleep(poll_interval_seconds)


def copy_items_to_sepal(
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
        payload = _download_item_bytes(drive_interface, item["id"])
        sepal_client.files.write(str(remote_path), payload, overwrite=True)
        uploaded_paths.append(str(remote_path))

    return tuple(uploaded_paths)


def delete_folder(drive_interface: GDriveInterface, folder_id: str) -> None:
    """Delete a staging folder and everything in it."""
    drive_interface.service.files().delete(fileId=folder_id).execute()


async def discard_folder(drive_interface: GDriveInterface, folder_id: str) -> None:
    """Delete a staging folder on a failure path without masking the failure."""
    with contextlib.suppress(Exception):
        await asyncio.to_thread(delete_folder, drive_interface, folder_id)


__all__ = [
    "STAGING_ROOT",
    "copy_items_to_sepal",
    "create_staging_folder",
    "delete_folder",
    "discard_folder",
    "find_items",
    "wait_for_items",
]
