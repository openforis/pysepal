"""High-level one-button launcher for the Solara export dialog."""

from __future__ import annotations

from typing import Callable, Optional, Sequence, Union

import solara
from pysepal_api import AsyncSepalClient, SepalClient

from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface

from .export_dialog import ExportDialog, InlineExportFeedback
from .export_hook import ExportDialogController, use_export_dialog
from .export_models import ExportBackend, ExportResult, ExportSource, ExportTarget


@solara.component
def ExportLauncher(
    sources: Sequence[ExportSource],
    label: str = "Export",
    icon: str = "mdi-export-variant",
    value: Union[Optional[ExportResult], solara.Reactive[Optional[ExportResult]]] = None,
    on_value: Optional[Callable[[Optional[ExportResult]], None]] = None,
    loading: Union[bool, solara.Reactive[bool]] = False,
    on_loading: Optional[Callable[[bool], None]] = None,
    default_target: ExportTarget = "gee",
    poll_interval_seconds: float = 3.0,
    timeout_seconds: float = 1800.0,
    cleanup_drive_after_sepal: bool = True,
    button_text: bool = False,
    small: bool = True,
    block: bool = False,
    dialog_title: str = "Export",
    gee_interface: GEEInterface | None = None,
    drive_interface: GDriveInterface | None = None,
    sepal_client: SepalClient | None = None,
    async_sepal_client: AsyncSepalClient | None = None,
    backend: ExportBackend = "auto",
):
    """Render the default export launcher UX."""
    reactive_value = solara.use_reactive(value, on_value)
    reactive_loading = solara.use_reactive(loading, on_loading)
    controller: ExportDialogController = use_export_dialog(
        sources,
        default_target=default_target,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds,
        cleanup_drive_after_sepal=cleanup_drive_after_sepal,
        gee_interface=gee_interface,
        drive_interface=drive_interface,
        sepal_client=sepal_client,
        async_sepal_client=async_sepal_client,
        backend=backend,
    )
    has_usable_sources = any(not source.disabled for source in controller.sources)
    disabled_tooltip = "No exportable layers available" if not has_usable_sources else ""

    def _sync_parent_state() -> None:
        reactive_value.set(controller.result.value)
        reactive_loading.set(controller.loading.value)

    solara.use_effect(
        _sync_parent_state,
        [controller.result.value, controller.loading.value],
    )

    with solara.Column(style="gap: 8px;"):
        if disabled_tooltip:
            with solara.Tooltip(disabled_tooltip):
                with solara.Column(style=("width: 100%;" if block else "width: fit-content;")):
                    solara.Button(
                        label=label if button_text else "",
                        on_click=controller.open_dialog,
                        icon_name=icon,
                        color="primary",
                        disabled=True,
                        small=small,
                        block=block,
                    )
        else:
            solara.Button(
                label=label if button_text else "",
                on_click=controller.open_dialog,
                icon_name=icon,
                color="primary",
                disabled=False,
                small=small,
                block=block,
            )

        ExportDialog(controller=controller, title=dialog_title)

        if (
            not controller._state.notifications_enabled
            and not controller.open.value
            and controller._state.inline_message.value
        ):
            InlineExportFeedback(
                message=controller._state.inline_message.value,
                level=controller._state.inline_level.value,
            )


__all__ = ["ExportLauncher"]
