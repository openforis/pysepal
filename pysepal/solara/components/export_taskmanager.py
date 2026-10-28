"""TaskManager workspace exports; the server owns all staging and cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import PurePosixPath
from typing import AsyncIterator, Callable, Literal, Optional

from pysepal_api import AsyncSepalClient, SepalClient
from pysepal_api.errors import ApiError, BadRequest, NotFound, ServerError
from pysepal_api.paths import sanitize_write_path

from pysepal.solara.errors import SessionScopeClosedError

from .export_models import (
    ExportBackend,
    ExportRequest,
    ExportResult,
    _build_result_message,
    get_task_state_name,
    resolve_sepal_folder,
)

TASKMANAGER_ENV_FLAG = "PYSEPAL_TASKMANAGER_EXPORTS"
EXPORT_BACKENDS = ("auto", "direct", "taskmanager")
_FAILED_STATES = frozenset({"FAILED", "CANCELED"})
_UNKNOWN_OUTCOME = (
    "SEPAL export submission outcome is unknown. Check SEPAL tasks before retrying; "
    "no alternate backend was used."
)


def taskmanager_opted_in() -> bool:
    """Whether the deployment routes dialog workspace exports through TaskManager."""
    return os.getenv(TASKMANAGER_ENV_FLAG) == "1"


def validate_backend(backend: str) -> None:
    """Raise ``ValueError`` for an unknown backend name."""
    if backend not in EXPORT_BACKENDS:
        raise ValueError(f"Unknown export backend: {backend}")


def taskmanager_rejection(request: ExportRequest) -> Optional[str]:
    """Return why TaskManager cannot run ``request``, or ``None`` when it can."""
    if request.target != "sepal":
        return "TaskManager exports currently support the SEPAL workspace only."
    if request.priority is not None:
        return "TaskManager does not support export priority."
    if request.export_kind == "table" and request.max_vertices is not None:
        return "TaskManager table max_vertices is supported only for Drive."
    return None


def select_backend(
    backend: ExportBackend,
    request: ExportRequest,
    *,
    sepal_client: object | None,
    async_sepal_client: object | None,
    opted_in: bool,
) -> Literal["direct", "taskmanager"]:
    """Resolve ``backend`` to the one that will run ``request``.

    ``auto`` uses TaskManager for workspace exports when the caller supplied an
    async client, or when ``opted_in`` and a sync client exists. It stays direct
    when the request needs an option TaskManager rejects and a sync client can
    run it directly. Explicit backends are returned unchanged.
    """
    validate_backend(backend)
    if backend != "auto":
        return backend
    if request.target != "sepal":
        return "direct"
    if async_sepal_client is None and not (opted_in and sepal_client is not None):
        return "direct"
    if sepal_client is not None and taskmanager_rejection(request):
        return "direct"
    return "taskmanager"


# pysepal-api has no public accessor for a client's auth or closed state. Reusing
# the sync client's auth pins the export to that client's user, and its closed
# state tells us when the session that owns it has been torn down.
def _session_closed(sepal_client: SepalClient) -> bool:
    return sepal_client._http.is_closed


@asynccontextmanager
async def _derived_client(sepal_client: SepalClient) -> AsyncIterator[AsyncSepalClient]:
    client = AsyncSepalClient(
        auth=sepal_client._http.auth,
        module_name=sepal_client.module_name,
        base_url=sepal_client.base_url,
        verify=sepal_client.verify,
    )
    try:
        yield client
    finally:
        await client.aclose()


async def cancel_taskmanager_export(
    client: SepalClient | AsyncSepalClient, sepal_task_id: str
) -> None:
    """Request remote cancellation; acceptance does not mean cancellation finished."""
    if isinstance(client, SepalClient):
        await asyncio.to_thread(client.tasks.cancel, sepal_task_id)
    else:
        await client.tasks.cancel(sepal_task_id)


async def submit_taskmanager_export(
    request: ExportRequest,
    client: AsyncSepalClient | None = None,
    *,
    sepal_client: SepalClient | None = None,
    on_step=None,
    on_update=None,
    on_remote_submitted=None,
) -> ExportResult:
    """Submit once, then monitor the SEPAL task through workspace completion.

    ``client`` stays owned by the caller. Without it, a client with
    ``sepal_client``'s identity is created for this export and closed after it.
    """
    rejection = taskmanager_rejection(request)
    if rejection:
        raise ValueError(rejection)
    callbacks = {
        "on_step": on_step,
        "on_update": on_update,
        "on_remote_submitted": on_remote_submitted,
    }
    if client is not None:
        return await _run(request, client, session_closed=lambda: False, **callbacks)
    if sepal_client is None:
        raise ValueError("TaskManager exports require a SEPAL client.")
    if _session_closed(sepal_client):
        raise SessionScopeClosedError("The export session has closed.")
    async with _derived_client(sepal_client) as derived:
        return await _run(
            request,
            derived,
            session_closed=lambda: _session_closed(sepal_client),
            **callbacks,
        )


def _rejection_message(exc: ApiError) -> str:
    message = f"SEPAL rejected the export ({exc}); no task was created."
    if isinstance(exc, (BadRequest, NotFound)):
        message += " This SEPAL deployment may not support TaskManager exports."
    return message


async def _run(
    request: ExportRequest,
    client: AsyncSepalClient,
    *,
    session_closed: Callable[[], bool],
    on_step,
    on_update,
    on_remote_submitted,
) -> ExportResult:
    from pysepal_api.endpoints import ee_exports

    from .export_engine import _apply_band_selection, _apply_viz_to_image, _notify

    if client.results_path is None:
        raise ValueError("Workspace exports require a module results directory.")
    workspace_path = str(sanitize_write_path(resolve_sepal_folder(client, request.sepal_folder)))
    encode = ee_exports.serialize_ee_object
    common = {
        "destination": ee_exports.EEExportDestination(request.target.upper()),
        "name": request.name,
        "workspace_path": workspace_path,
        "filename_prefix": request.name,
    }
    # Encoding happens here, before submission, so a local failure surfaces as
    # itself instead of as an unknown remote outcome.
    if request.export_kind == "image":
        payload = dict(
            common,
            image=encode(_apply_band_selection(_apply_viz_to_image(request), request)),
            region=encode(request.region) if request.region is not None else None,
            scale=request.scale,
            max_pixels=request.max_pixels,
            file_format=request.image_file_format,
        )
        submit = client.ee_exports.submit_image
    else:
        payload = dict(
            common,
            collection=encode(request.ee_object),
            selectors=list(request.selectors) if request.selectors else None,
            file_format="GeoJSON"
            if request.table_file_format == "GEO_JSON"
            else request.table_file_format,
        )
        submit = client.ee_exports.submit_table

    _notify(on_step, "Submitting SEPAL export")
    try:
        task = await submit(**payload)
    except ApiError as exc:
        if isinstance(exc, ServerError):
            raise RuntimeError(_UNKNOWN_OUTCOME) from exc
        raise RuntimeError(_rejection_message(exc)) from exc
    except Exception as exc:
        raise RuntimeError(_UNKNOWN_OUTCOME) from exc

    task_id = task.id
    _notify(on_remote_submitted, task_id)
    _notify(on_step, f"Waiting for SEPAL task {task_id}")
    stopped = f"Stopped waiting for SEPAL task `{task_id}`; it may still be running."
    loop = asyncio.get_running_loop()
    deadline = loop.time() + request.timeout_seconds
    while (state := get_task_state_name(task)) != "COMPLETED":
        if state in _FAILED_STATES:
            detail = getattr(task, "status_description", None) or state
            raise RuntimeError(f"SEPAL task `{task_id}`: {detail}")
        if session_closed():
            raise SessionScopeClosedError(f"The export session has closed. {stopped}")
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(stopped)
        _notify(on_update, f"SEPAL task {task_id}: {state or 'pending'}")
        await asyncio.sleep(min(request.poll_interval_seconds, remaining))
        try:
            task = await asyncio.wait_for(
                client.tasks.get(task_id), timeout=max(0, deadline - loop.time())
            )
        # Python 3.10's asyncio.TimeoutError is not the builtin TimeoutError.
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise TimeoutError(stopped) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Could not monitor SEPAL task `{task_id}`; it may still be running."
            ) from exc

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
