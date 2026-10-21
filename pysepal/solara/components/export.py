"""Stable import surface for the Solara export system.

This module keeps the legacy import path alive while the implementation is
split across dedicated model, engine, hook, dialog, and launcher modules.
"""

from __future__ import annotations

from typing import Optional, Sequence

import solara
from pysepal_api import SepalClient

from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface

from .export_dialog import ExportDialog
from .export_engine import submit_export_request
from .export_hook import ExportDialogController, use_export_dialog
from .export_launcher import ExportLauncher
from .export_models import (
    DEFAULT_IMAGE_FILE_FORMAT,
    DEFAULT_TABLE_FILE_FORMAT,
    TABLE_FILE_FORMATS,
    TARGET_LABELS,
    ExportBackend,
    ExportKind,
    ExportRequest,
    ExportResult,
    ExportSource,
    ExportTarget,
    ResolvedExport,
    _build_result_message,
    extract_task_id,
    get_task_state_name,
    infer_export_kind,
    matches_drive_export_prefix,
    resolve_asset_folder,
    resolve_sepal_folder,
    sanitize_export_name,
    validate_asset_id_under_root,
)
from .export_taskmanager import cancel_taskmanager_export


@solara.component
def ExportDataComponent(
    ee_object: object = None,
    value: Optional[ExportResult] | solara.Reactive[Optional[ExportResult]] = None,
    on_value=None,
    loading: bool | solara.Reactive[bool] = False,
    on_loading=None,
    title: str = "Export data",
    default_name: str = "export",
    default_target: ExportTarget = "gee",
    default_scale: int = 30,
    default_gee_folder: str = "",
    default_drive_folder: str = "",
    default_sepal_folder: str = "",
    region: object = None,
    selectors: Optional[Sequence[str]] = None,
    table_file_format: str = DEFAULT_TABLE_FILE_FORMAT,
    image_file_format: str = DEFAULT_IMAGE_FILE_FORMAT,
    max_pixels: Optional[int] = 1_000_000_000,
    max_vertices: Optional[int] = None,
    priority: Optional[int] = None,
    poll_interval_seconds: float = 3.0,
    timeout_seconds: float = 1800.0,
    cleanup_drive_after_sepal: bool = True,
    small: bool = True,
    block: bool = False,
    gee_interface: Optional[GEEInterface] = None,
    drive_interface: Optional[GDriveInterface] = None,
    sepal_client: Optional[SepalClient] = None,
):
    """Deprecated compatibility wrapper around ``ExportLauncher``.

    New code should pass one or more ``ExportSource`` objects to
    ``ExportLauncher`` or use ``use_export_dialog`` directly.
    """
    export_error = None
    sources: list[ExportSource] = []

    if ee_object is not None:
        try:
            export_kind = infer_export_kind(ee_object)
        except TypeError as exc:
            export_kind = None
            export_error = str(exc)
        else:
            sources = [
                ExportSource(
                    id="legacy_export",
                    label=default_name or "Export",
                    kind=export_kind,
                    resolve=lambda: ResolvedExport(
                        ee_object=ee_object,
                        default_name=default_name,
                        region=region,
                        default_scale=default_scale,
                        selectors=tuple(selectors) if selectors else None,
                        gee_folder=default_gee_folder,
                        drive_folder=default_drive_folder,
                        sepal_folder=default_sepal_folder,
                        table_file_format=table_file_format,
                        image_file_format=image_file_format,
                        max_pixels=max_pixels,
                        max_vertices=max_vertices,
                        priority=priority,
                    ),
                )
            ]

    with solara.Column(style="gap: 8px;"):
        if export_error:
            solara.Error(export_error)
        elif ee_object is None:
            solara.Info("Provide an ee.Image or ee.FeatureCollection to enable export.")

        ExportLauncher(
            sources=sources,
            value=value,
            on_value=on_value,
            loading=loading,
            on_loading=on_loading,
            default_target=default_target,
            poll_interval_seconds=poll_interval_seconds,
            timeout_seconds=timeout_seconds,
            cleanup_drive_after_sepal=cleanup_drive_after_sepal,
            button_text=True,
            small=small,
            block=block,
            dialog_title=title,
            gee_interface=gee_interface,
            drive_interface=drive_interface,
            sepal_client=sepal_client,
        )


__all__ = [
    "DEFAULT_IMAGE_FILE_FORMAT",
    "DEFAULT_TABLE_FILE_FORMAT",
    "TABLE_FILE_FORMATS",
    "TARGET_LABELS",
    "ExportBackend",
    "ExportDataComponent",
    "ExportDialog",
    "ExportDialogController",
    "ExportKind",
    "ExportLauncher",
    "ExportRequest",
    "ExportResult",
    "ExportSource",
    "ExportTarget",
    "ResolvedExport",
    "_build_result_message",
    "cancel_taskmanager_export",
    "extract_task_id",
    "get_task_state_name",
    "infer_export_kind",
    "matches_drive_export_prefix",
    "resolve_asset_folder",
    "resolve_sepal_folder",
    "sanitize_export_name",
    "submit_export_request",
    "use_export_dialog",
    "validate_asset_id_under_root",
]
