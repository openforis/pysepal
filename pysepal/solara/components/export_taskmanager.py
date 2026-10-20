"""TaskManager workspace exports; the server owns all staging and cleanup."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import PurePosixPath

from pysepal_api import AsyncSepalClient
from pysepal_api.paths import sanitize_write_path

from .export_models import (
    ExportRequest,
    ExportResult,
    _build_result_message,
    get_task_state_name,
    resolve_sepal_folder,
)


async def cancel_taskmanager_export(client: AsyncSepalClient, sepal_task_id: str) -> None:
    """Request remote cancellation; acceptance does not mean cancellation finished."""
    await client.tasks.cancel(sepal_task_id)


async def submit_taskmanager_export(
    request: ExportRequest,
    client: AsyncSepalClient,
    *,
    on_step=None,
    on_update=None,
    on_remote_submitted=None,
) -> ExportResult:
    """Submit once, then monitor the SEPAL task through workspace completion."""
    from pysepal_api.endpoints.ee_exports import EEExportDestination

    from .export_engine import _apply_band_selection, _apply_viz_to_image, _notify

    if request.target != "sepal":
        raise ValueError("TaskManager exports currently support the SEPAL workspace only.")
    if request.priority is not None:
        raise ValueError("TaskManager does not support export priority.")
    if request.export_kind == "table" and request.max_vertices is not None:
        raise ValueError("TaskManager table max_vertices is supported only for Drive.")
    if client.results_path is None:
        raise ValueError("Workspace exports require a module results directory.")
    workspace_path = str(sanitize_write_path(resolve_sepal_folder(client, request.sepal_folder)))
    common = {
        "destination": EEExportDestination(request.target.upper()),
        "name": request.name,
        "workspace_path": workspace_path,
        "filename_prefix": request.name,
    }
    if request.export_kind == "image":
        payload = dict(
            common,
            image=_apply_band_selection(_apply_viz_to_image(request), request),
            region=request.region,
            scale=request.scale,
            max_pixels=request.max_pixels,
            file_format=request.image_file_format,
        )
        submit = client.ee_exports.submit_image
    else:
        payload = dict(
            common,
            collection=request.ee_object,
            selectors=list(request.selectors) if request.selectors else None,
            file_format="GeoJSON"
            if request.table_file_format == "GEO_JSON"
            else request.table_file_format,
        )
        submit = client.ee_exports.submit_table

    _notify(on_step, "Submitting SEPAL export")
    try:
        task = await submit(**payload)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "SEPAL export submission outcome is unknown. Check SEPAL tasks before retrying; "
            "no alternate backend was used."
        ) from exc
    task_id = task.id
    _notify(on_remote_submitted, task_id)
    _notify(on_step, f"Waiting for SEPAL task {task_id}")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + request.timeout_seconds
    while get_task_state_name(task) != "COMPLETED":
        state = get_task_state_name(task)
        if state in {"FAILED", "CANCELED", "CANCELLED"}:
            detail = getattr(task, "status_description", None) or state
            raise RuntimeError(f"SEPAL task `{task_id}`: {detail}")
        if loop.time() >= deadline:
            raise TimeoutError(
                f"Stopped waiting for SEPAL task `{task_id}`; it may still be running."
            )
        _notify(on_update, f"SEPAL task {task_id}: {state or 'pending'}")
        try:
            task = await asyncio.wait_for(
                client.tasks.get(task_id), timeout=max(0, deadline - loop.time())
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"Stopped waiting for SEPAL task `{task_id}`; it may still be running."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Could not monitor SEPAL task `{task_id}`; it may still be running."
            ) from exc
        if get_task_state_name(task) not in {
            "COMPLETED",
            "FAILED",
            "CANCELED",
            "CANCELLED",
        }:
            await asyncio.sleep(min(request.poll_interval_seconds, max(0, deadline - loop.time())))

    result = ExportResult(
        target=request.target,
        export_kind=request.export_kind,
        name=request.name,
        message="",
        backend="taskmanager",
        status="completed",
        sepal_task_id=task_id,
        output_directory=str(PurePosixPath(client.BASE_REMOTE_PATH) / workspace_path),
    )
    return replace(result, message=_build_result_message(result))
