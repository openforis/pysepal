"""TaskManager workspace exports; the server owns all staging and cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import PurePosixPath
from typing import AsyncIterator, Awaitable, Callable, Literal, Optional

from pysepal_api import AsyncSepalClient, SepalClient
from pysepal_api.errors import ApiError, NotFound, ServerError
from pysepal_api.models import Task
from pysepal_api.paths import sanitize_write_path

from pysepal.solara.errors import SessionScopeClosedError

from .export_models import (
    REMOTE_CANCEL_TIMEOUT_SECONDS,
    ExportBackend,
    ExportRequest,
    ExportResult,
    RemoteCancelOutcome,
    _build_result_message,
    get_task_state_name,
    resolve_sepal_folder,
)

TASKMANAGER_ENV_FLAG = "PYSEPAL_TASKMANAGER_EXPORTS"
EXPORT_BACKENDS = ("auto", "direct", "taskmanager")
_FAILED_STATES = frozenset({"FAILED", "CANCELED"})
_FINAL_STATES = _FAILED_STATES | {"COMPLETED"}
# SEPAL's ee.export refuses any other table format for workspace exports.
_TABLE_FORMATS = frozenset({"CSV", "GEO_JSON", "KML", "KMZ", "SHP"})
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
    if request.export_kind == "table" and request.table_file_format not in _TABLE_FORMATS:
        return f"TaskManager does not support the {request.table_file_format} table format."
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
        timeout=sepal_client._http.timeout,
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
    on_remote_cancel=None,
) -> ExportResult:
    """Submit once, then monitor the SEPAL task through workspace completion.

    ``client`` stays owned by the caller. Without it, a client with
    ``sepal_client``'s identity is created for this export and closed after it.
    Each export writes to a new ``<name>_<timestamp>`` folder, because SEPAL
    refuses a folder that holds files or that another export writes to.

    A cancel of this coroutine also cancels the SEPAL task, including one whose
    submission was in flight. ``on_remote_cancel`` then gets a
    :class:`RemoteCancelOutcome`, before the ``CancelledError`` propagates.
    """
    rejection = taskmanager_rejection(request)
    if rejection:
        raise ValueError(rejection)
    callbacks = {
        "on_step": on_step,
        "on_update": on_update,
        "on_remote_submitted": on_remote_submitted,
        "on_remote_cancel": on_remote_cancel,
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
    reason = exc.body.get("message") if isinstance(exc.body, dict) else None
    message = f"SEPAL rejected the export ({reason or exc}); no task was created."
    if isinstance(exc, NotFound):
        message += " This SEPAL deployment may not support TaskManager exports."
    return message


def _workspace_folder(client: AsyncSepalClient, request: ExportRequest) -> str:
    folder = f"{request.name}_{datetime.now():%Y-%m-%d_%H-%M-%S-%f}"
    return str(sanitize_write_path(resolve_sepal_folder(client, request.sepal_folder) / folder))


async def _cancel_task(
    client: AsyncSepalClient, task_id: Optional[str], output_directory: str
) -> RemoteCancelOutcome:
    """Cancel the SEPAL task unless it has already ended. Never raises."""
    outcome = RemoteCancelOutcome(task_id=task_id, status="failed", service="SEPAL")
    if not task_id:
        return replace(outcome, error="SEPAL returned no task id.")

    async def ended_state() -> Optional[str]:
        state = get_task_state_name(await client.tasks.get(task_id))
        return state if state in _FINAL_STATES else None

    def finished(state: str) -> RemoteCancelOutcome:
        return replace(outcome, status="finished", state=state, output_directory=output_directory)

    async def cancel() -> RemoteCancelOutcome:
        state = await ended_state()
        if state is not None:
            return finished(state)
        try:
            await client.tasks.cancel(task_id)
        except Exception:
            # The task may have ended between the read and the cancel.
            state = await ended_state()
            if state is None:
                raise
            return finished(state)
        return replace(outcome, status="cancelled")

    try:
        return await asyncio.wait_for(cancel(), REMOTE_CANCEL_TIMEOUT_SECONDS)
    except Exception as exc:
        return replace(outcome, error=str(exc) or type(exc).__name__)


async def _submit(
    submit: Callable[..., Awaitable[Task]],
    payload: dict,
    on_cancel: Callable[[Optional[str]], Awaitable[None]],
) -> Task:
    """Submit once; on a cancel, let an in-flight request settle and cancel its task."""
    submission = asyncio.ensure_future(submit(**payload))
    try:
        return await asyncio.shield(submission)
    except asyncio.CancelledError:
        done, _pending = await asyncio.wait({submission}, timeout=REMOTE_CANCEL_TIMEOUT_SECONDS)
        if not done:
            submission.cancel()
            await on_cancel(None)
        elif not submission.cancelled() and submission.exception() is None:
            await on_cancel(submission.result().id)
        raise


async def _run(
    request: ExportRequest,
    client: AsyncSepalClient,
    *,
    session_closed: Callable[[], bool],
    on_step,
    on_update,
    on_remote_submitted,
    on_remote_cancel,
) -> ExportResult:
    from pysepal_api.endpoints import ee_exports

    from .export_engine import _apply_band_selection, _apply_viz_to_image, _notify

    if client.results_path is None:
        raise ValueError("Workspace exports require a module results directory.")
    workspace_path = _workspace_folder(client, request)
    output_directory = str(PurePosixPath(client.BASE_REMOTE_PATH) / workspace_path)
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

    async def cancel_remote(task_id: Optional[str]) -> None:
        if task_id:
            _notify(on_remote_submitted, task_id)
        _notify(on_remote_cancel, await _cancel_task(client, task_id, output_directory))

    _notify(on_step, "Submitting SEPAL export")
    try:
        task = await _submit(submit, payload, cancel_remote)
    except ApiError as exc:
        if isinstance(exc, ServerError):
            raise RuntimeError(_UNKNOWN_OUTCOME) from exc
        raise RuntimeError(_rejection_message(exc)) from exc
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RuntimeError(_UNKNOWN_OUTCOME) from exc

    task_id = task.id
    _notify(on_remote_submitted, task_id)
    _notify(on_step, f"Waiting for SEPAL task {task_id}")
    stopped = f"Stopped waiting for SEPAL task `{task_id}`; it may still be running."
    loop = asyncio.get_running_loop()
    deadline = loop.time() + request.timeout_seconds
    try:
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
            # The read after the last sleep still gets one poll interval, so a
            # task that completed in that interval is seen.
            read_timeout = max(deadline - loop.time(), request.poll_interval_seconds)
            try:
                task = await asyncio.wait_for(client.tasks.get(task_id), timeout=read_timeout)
            # Python 3.10's asyncio.TimeoutError is not the builtin TimeoutError.
            except (TimeoutError, asyncio.TimeoutError) as exc:
                raise TimeoutError(stopped) from exc
            except Exception as exc:
                raise RuntimeError(
                    f"Could not monitor SEPAL task `{task_id}`; it may still be running."
                ) from exc
    except asyncio.CancelledError:
        _notify(on_remote_cancel, await _cancel_task(client, task_id, output_directory))
        raise

    result = ExportResult(
        target=request.target,
        export_kind=request.export_kind,
        name=request.name,
        message="",
        backend="taskmanager",
        status="completed",
        sepal_task_id=task_id,
        output_directory=output_directory,
    )
    return replace(result, message=_build_result_message(result))
