"""Controller hook for the Solara export launcher and dialog."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Callable, Literal, Optional, Sequence

import solara
from pysepal_api import AsyncSepalClient, SepalClient

from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.notifications import use_notifications
from pysepal.solara.notifications.notifier import NoopNotifier
from pysepal.solara.utils import (
    get_current_drive_interface,
    get_current_gee_interface,
    get_current_sepal_client,
)

from .engine import submit_export_request
from .models import (
    DEFAULT_IMAGE_FILE_FORMAT,
    DEFAULT_TABLE_FILE_FORMAT,
    TARGET_LABELS,
    ExportBackend,
    ExportKind,
    ExportRequest,
    ExportResult,
    ExportSource,
    ExportTarget,
    RemoteCancelOutcome,
    ResolvedExport,
    _build_cancel_message,
    sanitize_export_name,
    validate_asset_id_under_root,
)
from .sources import (
    available_bands_for,
    build_default_gee_asset_id,
    coerce_default_target,
    default_bands_for,
    defaults_signature,
    discover_image_bands,
    enabled_sources,
    get_active_source,
    get_source_items,
    get_target_items,
    normalize_band_selection,
    resolve_gee_asset_conflict,
    resolve_source_state,
    resolved_default_bands,
    source_by_id,
    targets_for,
)
from .taskmanager import select_backend, taskmanager_opted_in, validate_backend

# Longer than the 3s toast default so the asset path / task id stays copyable.
EXPORT_SUCCESS_TOAST_TIMEOUT = 8.0


@dataclass(frozen=True, slots=True)
class _ExportDialogState:
    scale: solara.Reactive[int]
    asset_root: solara.Reactive[str]
    gee_asset_id: solara.Reactive[str]
    gee_asset_id_dirty: solara.Reactive[bool]
    last_default_gee_asset_id: solara.Reactive[str]
    drive_folder: solara.Reactive[str]
    sepal_folder: solara.Reactive[str]
    table_file_format: solara.Reactive[str]
    inline_message: solara.Reactive[str]
    inline_level: solara.Reactive[str]
    last_default_name: solara.Reactive[str]
    gee_asset_conflict: solara.Reactive[bool]
    gee_asset_conflict_path: solara.Reactive[str]
    selected_bands: solara.Reactive[tuple[str, ...]]
    bands_dirty: solara.Reactive[bool]
    last_default_bands: solara.Reactive[tuple[str, ...]]
    discovered_bands: solara.Reactive[tuple[str, ...]]
    discovered_source_id: solara.Reactive[str]
    bands_loading: solara.Reactive[bool]
    gee_interface: GEEInterface
    drive_interface: GDriveInterface | None
    sepal_client: SepalClient | AsyncSepalClient | None
    notifications_enabled: bool
    poll_interval_seconds: float
    timeout_seconds: float
    cleanup_drive_after_sepal: bool
    cancel_reason_ref: Any = field(repr=False, compare=False)
    run_started_ref: Any = field(repr=False, compare=False)
    available_targets: frozenset[ExportTarget] = frozenset()


@dataclass(frozen=True, slots=True)
class ExportDialogController:
    """Public controller returned by ``use_export_dialog``."""

    open: solara.Reactive[bool]
    selected_target: solara.Reactive[ExportTarget]
    selected_source_id: solara.Reactive[str]
    export_name: solara.Reactive[str]
    name_dirty: solara.Reactive[bool]
    loading: solara.Reactive[bool]
    result: solara.Reactive[Optional[ExportResult]]
    sources: tuple[ExportSource, ...]
    task: Any
    open_dialog: Callable[[], None]
    close_dialog: Callable[[], None]
    submit_export: Callable[[], None]
    cancel_export: Callable[[], None]
    _state: _ExportDialogState = field(repr=False, compare=False)
    _source_state: tuple[
        ExportSource | None, ResolvedExport | None, ExportKind | None, str | None
    ] = field(default=(None, None, None, None), repr=False, compare=False)


def get_controller_source_state(
    controller: ExportDialogController,
) -> tuple[ExportSource | None, ResolvedExport | None, ExportKind | None, str | None]:
    """Return ``(active_source, resolved, kind, error)`` for the controller's selection."""
    return controller._source_state


def _tracker_step_count(request: ExportRequest, backend: Literal["direct", "taskmanager"]) -> int:
    if request.target == "gee":
        return 3
    if request.target == "drive":
        return 2
    if backend == "taskmanager":
        return 3
    return 5 if request.cleanup_drive_after_sepal else 4


def use_export_dialog(
    sources: Sequence[ExportSource],
    *,
    default_target: ExportTarget = "gee",
    poll_interval_seconds: float = 3.0,
    timeout_seconds: float = 1800.0,
    cleanup_drive_after_sepal: bool = True,
    gee_interface: GEEInterface | None = None,
    drive_interface: GDriveInterface | None = None,
    sepal_client: SepalClient | None = None,
    async_sepal_client: AsyncSepalClient | None = None,
    backend: ExportBackend = "auto",
) -> ExportDialogController:
    """Return controller state for a reusable export dialog."""
    sources_tuple = tuple(sources)
    source_signature = tuple((source.id, source.disabled) for source in sources_tuple)
    usable_sources = enabled_sources(sources_tuple)

    validate_backend(backend)
    gee_interface = gee_interface or get_current_gee_interface()
    sepal_client = sepal_client or get_current_sepal_client()
    workspace_client = sepal_client or async_sepal_client
    available_targets = targets_for(backend, sepal_client, async_sepal_client)

    notifications = use_notifications(required=False)
    notifications_enabled = not isinstance(notifications, NoopNotifier)

    open_state = solara.use_reactive(False)
    selected_target = solara.use_reactive(coerce_default_target(default_target, available_targets))
    selected_source_id = solara.use_reactive("")
    export_name = solara.use_reactive("")
    name_dirty = solara.use_reactive(False)
    loading = solara.use_reactive(False)
    result = solara.use_reactive(None)
    open_count = solara.use_reactive(0)

    state = _ExportDialogState(
        scale=solara.use_reactive(30),
        asset_root=solara.use_reactive("projects/{project}/assets"),
        gee_asset_id=solara.use_reactive(""),
        gee_asset_id_dirty=solara.use_reactive(False),
        last_default_gee_asset_id=solara.use_reactive(""),
        drive_folder=solara.use_reactive(""),
        sepal_folder=solara.use_reactive(""),
        table_file_format=solara.use_reactive(DEFAULT_TABLE_FILE_FORMAT),
        inline_message=solara.use_reactive(""),
        inline_level=solara.use_reactive("info"),
        last_default_name=solara.use_reactive(""),
        gee_asset_conflict=solara.use_reactive(False),
        gee_asset_conflict_path=solara.use_reactive(""),
        selected_bands=solara.use_reactive(()),
        bands_dirty=solara.use_reactive(False),
        last_default_bands=solara.use_reactive(()),
        discovered_bands=solara.use_reactive(()),
        discovered_source_id=solara.use_reactive(""),
        bands_loading=solara.use_reactive(False),
        gee_interface=gee_interface,
        drive_interface=drive_interface,
        sepal_client=workspace_client,
        notifications_enabled=notifications_enabled,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        cleanup_drive_after_sepal=cleanup_drive_after_sepal,
        cancel_reason_ref=solara.use_ref(None),
        run_started_ref=solara.use_ref(False),
        available_targets=available_targets,
    )

    active_source = get_active_source(sources_tuple, selected_source_id.value)
    # Resolve once per selection. Reacton compares functions by code and captured
    # values, so a resolve rebuilt each render with the same inputs is not re-run.
    # Each open of the dialog resolves again, for state the closure does not capture.
    resolve_key = (
        None
        if active_source is None
        else (active_source.id, active_source.label, active_source.kind, active_source.resolve)
    )
    resolved_export, export_kind, resolve_error = solara.use_memo(
        lambda: resolve_source_state(active_source),
        dependencies=[resolve_key, open_count.value],
    )
    active_source_id = active_source.id if active_source is not None else ""
    default_name = (
        sanitize_export_name(resolved_export.default_name) if resolved_export is not None else ""
    )
    source_defaults_signature = defaults_signature(
        resolved_export,
        export_kind,
        state.sepal_client,
    )
    # Effective catalog: declared bands, else bands auto-discovered from the
    # image. The source-id gate drops a stale catalog from a prior selection.
    declared_bands = available_bands_for(resolved_export)
    discovered_bands = (
        state.discovered_bands.value
        if active_source_id and state.discovered_source_id.value == active_source_id
        else ()
    )
    available_bands = declared_bands or discovered_bands
    default_bands = default_bands_for(resolved_export, available_bands)
    last_resolve_error_ref = solara.use_ref(None)

    def _push_inline(level: str, message: str) -> None:
        state.inline_level.set(level)
        state.inline_message.set(message)

    def _clear_inline() -> None:
        state.inline_level.set("info")
        state.inline_message.set("")

    def _publish(level: str, message: str, *, timeout: Optional[float] = None) -> None:
        if notifications_enabled:
            if level == "success":
                notifications.success(message, timeout=timeout)
            elif level == "error":
                notifications.error(message, timeout=timeout)
            elif level == "warning":
                notifications.warning(message, timeout=timeout)
            elif level == "cancel":
                notifications.cancel(message, timeout=timeout)
            else:
                notifications.info(message, timeout=timeout)
        else:
            _push_inline(level, message)

    def _reconcile_selected_source() -> None:
        if not selected_source_id.value:
            return

        selected = source_by_id(sources_tuple, selected_source_id.value)
        if selected is None or selected.disabled:
            selected_source_id.set("")

    solara.use_effect(_reconcile_selected_source, [source_signature, selected_source_id.value])

    def _reconcile_target() -> None:
        if available_targets and selected_target.value not in available_targets:
            selected_target.set(coerce_default_target(default_target, available_targets))

    solara.use_effect(_reconcile_target, [selected_target.value, available_targets])

    async def _load_asset_root() -> None:
        try:
            root_folder = await state.gee_interface.get_folder_async()
        except Exception:
            return

        if root_folder:
            state.asset_root.set(str(root_folder).rstrip("/"))

    solara.lab.use_task(
        _load_asset_root,
        dependencies=[],
        raise_error=False,
        prefer_threaded=False,
    )

    async def _check_gee_asset_conflict() -> None:
        # Structurally invalid paths are gated by the visible "must live under
        # <root>/" error; no point probing a path the user can't write to.
        if validate_asset_id_under_root(state.gee_asset_id.value, state.asset_root.value):
            state.gee_asset_conflict.set(False)
            state.gee_asset_conflict_path.set("")
            return

        conflict, candidate = await resolve_gee_asset_conflict(
            target=selected_target.value,
            has_active_source=active_source is not None,
            asset_id=state.gee_asset_id.value,
            gee_interface=state.gee_interface,
        )
        state.gee_asset_conflict.set(conflict)
        state.gee_asset_conflict_path.set(candidate)

    solara.lab.use_task(
        _check_gee_asset_conflict,
        dependencies=[
            selected_target.value,
            state.gee_asset_id.value,
            state.asset_root.value,
            active_source_id,
        ],
        raise_error=False,
        prefer_threaded=False,
    )

    def _sync_source_defaults() -> None:
        if resolved_export is None:
            return

        state.scale.set(int(resolved_export.default_scale or 30))
        state.drive_folder.set(resolved_export.drive_folder or "")
        state.sepal_folder.set(resolved_export.sepal_folder or "")
        state.table_file_format.set(resolved_export.table_file_format or DEFAULT_TABLE_FILE_FORMAT)

    solara.use_effect(_sync_source_defaults, [active_source_id, source_defaults_signature])

    def _sync_default_name() -> None:
        if name_dirty.value:
            return

        if default_name != state.last_default_name.value:
            state.last_default_name.set(default_name)
            export_name.set(default_name)

    solara.use_effect(_sync_default_name, [active_source_id, default_name, name_dirty.value])

    def _sync_default_gee_asset_id() -> None:
        if state.gee_asset_id_dirty.value:
            return
        if resolved_export is None:
            return

        default = build_default_gee_asset_id(
            state.asset_root.value,
            resolved_export,
            state.sepal_client,
        )
        if not default:
            return  # Asset root still loading.

        if default != state.last_default_gee_asset_id.value:
            state.last_default_gee_asset_id.set(default)
            state.gee_asset_id.set(default)

    solara.use_effect(
        _sync_default_gee_asset_id,
        [
            active_source_id,
            state.asset_root.value,
            state.gee_asset_id_dirty.value,
            source_defaults_signature,
        ],
    )

    async def _sync_discovered_bands() -> None:
        # Auto-discover bands only for image sources without a declared catalog.
        if export_kind != "image" or declared_bands or resolved_export is None:
            if state.bands_loading.value:
                state.bands_loading.set(False)
            return

        state.bands_loading.set(True)
        try:
            names = await discover_image_bands(state.gee_interface, resolved_export.ee_object)
        finally:
            state.bands_loading.set(False)
        # Tag with the source id so it applies only to the source it was fetched for.
        state.discovered_source_id.set(active_source_id)
        state.discovered_bands.set(names)

    solara.lab.use_task(
        _sync_discovered_bands,
        dependencies=[
            active_source_id,
            export_kind,
            declared_bands,
            resolved_export,
            open_count.value,
        ],
        raise_error=False,
        prefer_threaded=False,
    )

    def _reset_bands_dirty_on_source_change() -> None:
        # A freshly selected source starts clean, so its defaults re-apply.
        if state.bands_dirty.value:
            state.bands_dirty.set(False)

    solara.use_effect(_reset_bands_dirty_on_source_change, [active_source_id])

    def _sync_default_bands() -> None:
        # No catalog: clear stale picker state so a prior subset doesn't leak.
        if not available_bands:
            if state.last_default_bands.value:
                state.last_default_bands.set(())
            if state.selected_bands.value:
                state.selected_bands.set(())
            return

        if state.bands_dirty.value:
            return

        if default_bands != state.last_default_bands.value:
            state.last_default_bands.set(default_bands)
            state.selected_bands.set(default_bands)

    solara.use_effect(
        _sync_default_bands,
        [
            active_source_id,
            state.bands_dirty.value,
            available_bands,
            default_bands,
        ],
    )

    def _handle_resolve_error() -> None:
        if not resolve_error:
            last_resolve_error_ref.current = None
            return

        error_key = (active_source_id, resolve_error)
        if last_resolve_error_ref.current == error_key:
            return

        last_resolve_error_ref.current = error_key
        _publish("error", resolve_error)

    solara.use_effect(_handle_resolve_error, [active_source_id, resolve_error])

    def build_request() -> ExportRequest:
        if active_source is None:
            if usable_sources:
                raise ValueError("Select an asset to export.")
            raise ValueError("No exportable layers available.")
        if resolved_export is None or export_kind is None:
            raise ValueError(resolve_error or "Unable to resolve the selected export source.")
        if selected_target.value not in available_targets:
            if selected_target.value == "sepal" or not available_targets:
                raise ValueError(
                    "SEPAL export requires a session-backed SepalClient. "
                    "Use @with_sepal_sessions in the host page."
                )
            raise ValueError("The TaskManager backend currently supports SEPAL workspace only.")

        if selected_target.value == "gee":
            asset_id = state.gee_asset_id.value.strip()
            if not asset_id:
                raise ValueError("Asset ID required")
            description = PurePosixPath(asset_id).name or "export"
        else:
            if not export_name.value.strip():
                raise ValueError("Name required")
            description = sanitize_export_name(export_name.value)
            export_name.set(description)
            asset_id = None

        if available_bands:
            picked = normalize_band_selection(available_bands, state.selected_bands.value)
            if not picked:
                raise ValueError("Select at least one band.")
            selectors = picked
        else:
            selectors = tuple(resolved_export.selectors) if resolved_export.selectors else None

        return ExportRequest(
            ee_object=resolved_export.ee_object,
            export_kind=export_kind,
            target=selected_target.value,
            name=description,
            region=resolved_export.region,
            scale=state.scale.value if export_kind == "image" else None,
            gee_asset_id=asset_id,
            drive_folder=(
                state.drive_folder.value.strip() or None
                if selected_target.value == "drive"
                else None
            ),
            sepal_folder=state.sepal_folder.value.strip() or None,
            table_file_format=state.table_file_format.value,
            image_file_format=resolved_export.image_file_format or DEFAULT_IMAGE_FILE_FORMAT,
            selectors=selectors,
            max_pixels=resolved_export.max_pixels,
            max_vertices=resolved_export.max_vertices,
            priority=resolved_export.priority,
            cleanup_drive_after_sepal=state.cleanup_drive_after_sepal,
            poll_interval_seconds=state.poll_interval_seconds,
            timeout_seconds=state.timeout_seconds,
            vis_params=resolved_export.vis_params if export_kind == "image" else None,
        )

    async def run_export(request: ExportRequest) -> ExportResult:
        selected = select_backend(
            backend,
            request,
            sepal_client=sepal_client,
            async_sepal_client=async_sepal_client,
            opted_in=taskmanager_opted_in(),
        )
        tracker_title = f"Exporting {request.name} to {TARGET_LABELS[request.target]}"
        total_steps = _tracker_step_count(request, selected)

        # From here on this coroutine reports its own cancel, with what it did
        # to the Earth Engine task; _sync_task_state only reports a cancel
        # that came before it started.
        state.run_started_ref.current = True
        cancel_outcomes: list[RemoteCancelOutcome] = []

        with notifications.track(tracker_title, total_steps=total_steps) as tracker:
            drive = state.drive_interface
            if (
                request.target == "sepal"
                and selected == "direct"
                and sepal_client is not None
                and drive is None
            ):
                drive = get_current_drive_interface()
            try:
                return await submit_export_request(
                    request,
                    gee_interface=state.gee_interface,
                    drive_interface=drive,
                    sepal_client=sepal_client,
                    async_sepal_client=async_sepal_client,
                    backend=selected,
                    on_step=tracker.step,
                    on_update=tracker.update,
                    on_remote_cancel=cancel_outcomes.append,
                )
            except asyncio.CancelledError:
                level, message = _build_cancel_message(
                    request, cancel_outcomes[-1] if cancel_outcomes else None
                )
                _publish(level, message)
                raise

    task = solara.lab.use_task(
        run_export,
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )

    def _sync_task_state() -> None:
        loading.set(task.pending)

        if task.pending:
            result.set(None)
            _clear_inline()
            return

        if task.finished:
            result.set(task.value)
            state.run_started_ref.current = False
            if task.value:
                _publish(
                    "success",
                    task.value.message,
                    timeout=EXPORT_SUCCESS_TOAST_TIMEOUT,
                )
            return

        if task.error:
            result.set(None)
            state.run_started_ref.current = False
            if task.exception is not None:
                _publish("error", str(task.exception))
            return

        if task.cancelled:
            result.set(None)
            if not state.run_started_ref.current:
                _publish("cancel", "Export cancelled.")
            state.run_started_ref.current = False

    solara.use_effect(
        _sync_task_state,
        [
            task.pending,
            task.finished,
            task.error,
            task.cancelled,
            task.value,
            task.exception,
        ],
    )

    def open_dialog() -> None:
        _clear_inline()
        selected_source_id.set("")
        export_name.set("")
        name_dirty.set(False)
        state.last_default_name.set("")
        state.gee_asset_id.set("")
        state.gee_asset_id_dirty.set(False)
        state.last_default_gee_asset_id.set("")
        state.selected_bands.set(())
        state.bands_dirty.set(False)
        state.last_default_bands.set(())
        state.discovered_bands.set(())
        state.discovered_source_id.set("")
        state.bands_loading.set(False)
        open_count.set(open_count.value + 1)
        open_state.set(True)

    def close_dialog() -> None:
        _clear_inline()
        name_dirty.set(False)
        state.gee_asset_id_dirty.set(False)
        state.bands_dirty.set(False)
        state.bands_loading.set(False)
        open_state.set(False)

    def submit_export() -> None:
        state.cancel_reason_ref.current = None
        _clear_inline()

        try:
            request = build_request()
        except Exception as exc:
            _publish("error", str(exc))
            return

        task(request)

    def cancel_export() -> None:
        state.cancel_reason_ref.current = "user"
        if task.pending:
            try:
                task.cancel()
            except RuntimeError:
                pass

    return ExportDialogController(
        open=open_state,
        selected_target=selected_target,
        selected_source_id=selected_source_id,
        export_name=export_name,
        name_dirty=name_dirty,
        loading=loading,
        result=result,
        sources=sources_tuple,
        task=task,
        open_dialog=open_dialog,
        close_dialog=close_dialog,
        submit_export=submit_export,
        cancel_export=cancel_export,
        _state=state,
        _source_state=(active_source, resolved_export, export_kind, resolve_error),
    )


__all__ = [
    "ExportDialogController",
    "available_bands_for",
    "default_bands_for",
    "discover_image_bands",
    "get_active_source",
    "get_controller_source_state",
    "get_source_items",
    "get_target_items",
    "normalize_band_selection",
    "resolve_source_state",
    "resolved_default_bands",
    "use_export_dialog",
]
