"""Modal UI for the Solara export launcher."""

from __future__ import annotations

from pathlib import Path

import reacton.ipyvuetify as rv
import reacton.ipyvuetify as v
import solara

from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

from .export_hook import (
    ExportDialogController,
    available_bands_for,
    get_controller_source_state,
    get_source_items,
    get_target_items,
    normalize_band_selection,
)
from .export_models import TABLE_FILE_FORMATS, ExportKind, validate_asset_id_under_root

IMAGE_SCALE_PRESETS = [10, 15, 20, 30, 60, 100]

# Field styling (bands / scale / destination) lives in the sibling CSS file so
# it stays out of the component bodies; loaded once via ``solara.Style`` in
# ``ExportDialog``.
_EXPORT_DIALOG_CSS = Path(__file__).with_name("export_dialog.css").read_text(encoding="utf-8")


def _validation_message(
    *,
    has_usable_sources: bool,
    has_active_source: bool,
    resolvable: bool,
    gee_target: bool,
    gee_asset_id: str,
    asset_root_error: str | None,
    gee_asset_conflict: bool,
    export_name: str,
    bands_empty: bool,
    band_noun: str,
) -> str:
    """Return the single highest-priority blocking message, or ``""`` when valid.

    One message at a time, in the order a user resolves them: pick a source,
    then a valid destination target/id, then a non-empty band selection. The
    dialog renders this once at the bottom and gates the Export button on it.
    """
    if not has_usable_sources:
        return "No exportable layers available."
    if not has_active_source:
        # The Asset selector already makes this obvious — no message. The dialog
        # still disables Export for this case via ``active_source is None``.
        return ""
    if not resolvable:
        return "The selected layer cannot currently be exported."
    if gee_target:
        if not gee_asset_id.strip():
            return "Asset ID is required."
        if asset_root_error:
            return asset_root_error
        if gee_asset_conflict:
            return "An asset with this id already exists. Edit the id or pick a different path."
    elif not export_name.strip():
        return "Name is required."
    if bands_empty:
        return f"Select at least one {band_noun}."
    return ""


@solara.component
def InlineExportFeedback(message: str, level: str) -> None:
    """Render fallback inline feedback when notifications are unavailable."""
    if not message:
        return

    if level == "success":
        solara.Success(message)
    elif level == "error":
        solara.Error(message)
    elif level == "warning":
        solara.Warning(message)
    else:
        solara.Info(message)


def _band_field_label(export_kind: ExportKind | None) -> str:
    """User-facing field label. Images carry bands; tables carry properties."""
    return "Properties" if export_kind == "table" else "Bands"


def _toggle_button(label: str, *, selected: bool, disabled: bool = False):
    """A styled toggle button shared by the band and scale pickers.

    Selected buttons get a solid ``secondary`` fill with a white label so they
    read on both light and dark themes; unselected inherit the neutral toggle
    style. The enclosing ``v.BtnToggle`` should also carry ``color="secondary"``
    so the selected accent (border/overlay) is secondary rather than the
    default primary.
    """
    props: dict[str, object] = {
        "children": [label],
        "small": True,
        "depressed": True,
        "disabled": disabled,
    }
    if selected:
        props["color"] = "secondary"
        props["class_"] = "white--text"
    return rv.Btn(**props)


@solara.component
def BandSelectorField(
    available: tuple[str, ...],
    selected: solara.Reactive[tuple[str, ...]],
    dirty: solara.Reactive[bool],
    export_kind: ExportKind | None,
    disabled: bool = False,
    loading: bool = False,
) -> None:
    """Multi-select toggle-button picker for the subset of bands/properties.

    Renders one selectable button per band inside a ``v.BtnToggle``. Each
    selected button gets a solid ``secondary`` fill with a white label (so it
    reads on both light and dark themes); unselected buttons stay neutral.

    While ``loading`` is set and no catalog is available yet, a spinner stands
    in for the toggles — the window where image bands are auto-discovered from
    the ee.Image. The empty-selection error is surfaced by the dialog's single
    bottom validation message, not here. Returns ``None`` only when there is
    nothing to show and nothing loading.
    """
    if not available and not loading:
        return

    label = _band_field_label(export_kind)
    current = normalize_band_selection(available, selected.value)
    show_loading = loading and not available
    current_set = set(current)
    # ``v.BtnToggle`` tracks selection by child index, so map bands <-> indices.
    selected_indices = [index for index, band in enumerate(available) if band in current_set]
    selected_index_set = set(selected_indices)

    def _on_indices(new_indices) -> None:
        picked = tuple(
            available[index] for index in (new_indices or []) if 0 <= index < len(available)
        )
        new_selection = normalize_band_selection(available, picked)
        if new_selection != selected.value:
            selected.set(new_selection)
        if not dirty.value:
            dirty.set(True)

    # Title on top, picker below — consistent with the Scale and Destination
    # fields. Styling is in export_dialog.css.
    with rv.Html(tag="div", class_="sepal-export-field"):
        solara.Text(label, classes=["sepal-export-field-title"])

        # Frameless but fixed-min-height slot: the spinner and the toggles occupy
        # the same space, so switching layers never resizes the field while the
        # catalog loads.
        with rv.Html(tag="div", class_="sepal-band-slot"):
            if show_loading:
                rv.ProgressCircular(indeterminate=True, size=20, width=2, color="secondary")
            else:
                rv.BtnToggle(
                    v_model=selected_indices,
                    on_v_model=_on_indices,
                    multiple=True,
                    mandatory=False,
                    dense=True,
                    color="secondary",
                    class_="sepal-band-toggle",
                    children=[
                        _toggle_button(
                            band,
                            selected=index in selected_index_set,
                            disabled=disabled,
                        )
                        for index, band in enumerate(available)
                    ],
                )


@solara.component
def ImageScaleField(scale: solara.Reactive[int]) -> None:
    """Render SEPAL-style scale presets plus a custom numeric field."""
    selected_preset_index = (
        IMAGE_SCALE_PRESETS.index(scale.value) if scale.value in IMAGE_SCALE_PRESETS else None
    )

    def _handle_preset_index(index: int | None) -> None:
        if index is not None and 0 <= index < len(IMAGE_SCALE_PRESETS):
            scale.set(int(IMAGE_SCALE_PRESETS[index]))

    def _handle_custom_scale(value: str) -> None:
        try:
            numeric_value = int(float(value))
        except (TypeError, ValueError):
            return

        if numeric_value > 0:
            scale.set(numeric_value)

    with rv.Html(tag="div", class_="sepal-export-field"):
        solara.Text("Scale", classes=["sepal-export-field-title"])
        with rv.Html(tag="div", class_="sepal-scale-row"):
            # Same styling as the band picker: solid secondary fill on the
            # selected preset, secondary accent (no default primary/blue).
            rv.BtnToggle(
                v_model=selected_preset_index,
                on_v_model=_handle_preset_index,
                multiple=False,
                mandatory=False,
                dense=True,
                color="secondary",
                class_="sepal-scale-toggle",
                children=[
                    _toggle_button(str(preset), selected=index == selected_preset_index)
                    for index, preset in enumerate(IMAGE_SCALE_PRESETS)
                ],
            )

            with rv.TextField(
                v_model=str(scale.value),
                on_v_model=_handle_custom_scale,
                type="number",
                suffix="m",
                dense=True,
                hide_details=True,
                placeholder="Custom",
                class_="sepal-scale-custom",
            ):
                pass


@solara.component
def ExportDialog(
    controller: ExportDialogController,
    title: str = "Export",
    max_width: str = "720px",
):
    """Render the export dialog using an existing controller."""
    state = controller._state
    active_source, resolved_export, export_kind, resolve_error = get_controller_source_state(
        controller
    )
    has_usable_sources = any(not source.disabled for source in controller.sources)
    fields_disabled = active_source is None
    gee_target_selected = controller.selected_target.value == "gee"
    gee_asset_conflict = gee_target_selected and state.gee_asset_conflict.value
    # Effective catalog = declared bands, else the bands auto-discovered from
    # the ee.Image (image sources without a declared catalog). Discovered bands
    # are gated by source id so a stale catalog from a previously selected
    # source is never shown.
    active_source_id = active_source.id if active_source is not None else ""
    declared_bands = available_bands_for(resolved_export)
    discovery_ran = bool(active_source_id) and state.discovered_source_id.value == active_source_id
    discovered_bands = state.discovered_bands.value if discovery_ran else ()
    available_bands = declared_bands or discovered_bands
    # Every image gets a band picker; while its catalog is still being discovered
    # (the task has not recorded a result for this source yet) show a same-height
    # spinner. Computing this synchronously — rather than waiting for the async
    # ``bands_loading`` flag — keeps the slot mounted the instant you switch
    # layers, so it never unmounts-and-remounts.
    bands_pending = (
        active_source is not None
        and export_kind == "image"
        and not declared_bands
        and not discovery_ran
    )
    bands_loading = state.bands_loading.value or bands_pending
    bands_required = bool(available_bands)
    bands_empty = bands_required and not normalize_band_selection(
        available_bands, state.selected_bands.value
    )

    asset_root_error = (
        validate_asset_id_under_root(state.gee_asset_id.value, state.asset_root.value)
        if gee_target_selected and not fields_disabled
        else None
    )
    # Single source of truth for validation: one prioritized message, rendered
    # once at the bottom, and the Export button is gated on it (plus the
    # transient band-discovery window).
    validation_message = _validation_message(
        has_usable_sources=has_usable_sources,
        has_active_source=active_source is not None,
        resolvable=(resolved_export is not None and export_kind is not None and not resolve_error),
        gee_target=gee_target_selected,
        gee_asset_id=state.gee_asset_id.value,
        asset_root_error=asset_root_error,
        gee_asset_conflict=gee_asset_conflict,
        export_name=controller.export_name.value,
        bands_empty=bands_empty,
        band_noun="property" if export_kind == "table" else "band",
    )
    submit_disabled = active_source is None or bool(validation_message) or bands_loading

    target_items = get_target_items(state.sepal_client, available=state.available_targets)
    source_items = get_source_items(controller.sources)
    button_props = use_task_button(
        controller.task,
        on_start=controller.submit_export,
        cancel_reason_ref=state.cancel_reason_ref,
    )

    def _handle_name_change(value: str) -> None:
        controller.export_name.set(value)
        if not controller.name_dirty.value and value != state.last_default_name.value:
            controller.name_dirty.set(True)

    def _handle_asset_id_change(value: str) -> None:
        state.gee_asset_id.set(value)
        if not state.gee_asset_id_dirty.value and value != state.last_default_gee_asset_id.value:
            state.gee_asset_id_dirty.set(True)

    with v.Dialog(
        v_model=controller.open.value,
        on_v_model=controller.open.set,
        max_width=max_width,
        scrollable=True,
    ):
        with solara.v.Card():
            solara.Style(_EXPORT_DIALOG_CSS)
            solara.v.CardTitle(children=[title])

            with solara.v.CardText():
                with solara.Column(gap="16px", classes=["sepal-export-body"]):
                    if source_items:
                        with rv.Select(
                            label="Asset",
                            items=source_items,
                            v_model=controller.selected_source_id.value,
                            on_v_model=controller.selected_source_id.set,
                            dense=True,
                            placeholder="Select asset",
                            hide_details=True,
                        ):
                            pass

                    if available_bands or bands_loading:
                        BandSelectorField(
                            available=available_bands,
                            selected=state.selected_bands,
                            dirty=state.bands_dirty,
                            export_kind=export_kind,
                            disabled=fields_disabled,
                            loading=bands_loading,
                        )

                    with rv.Html(tag="div", class_="sepal-export-field"):
                        solara.Text("Destination", classes=["sepal-export-field-title"])
                        with rv.RadioGroup(
                            v_model=controller.selected_target.value,
                            on_v_model=controller.selected_target.set,
                            dense=True,
                            mandatory=True,
                            row=True,
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            for item in target_items:
                                rv.Radio(
                                    label=item["text"],
                                    value=item["value"],
                                    disabled=bool(item.get("disabled", False)) or fields_disabled,
                                )

                    if gee_target_selected:
                        with rv.TextField(
                            label="Asset ID",
                            v_model=state.gee_asset_id.value,
                            on_v_model=_handle_asset_id_change,
                            dense=True,
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            pass
                    else:
                        with rv.TextField(
                            label="Export name",
                            v_model=controller.export_name.value,
                            on_v_model=_handle_name_change,
                            dense=True,
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            pass

                    # Workspace exports only pass through Drive as staging;
                    # like the SEPAL UI, the user never picks that folder.
                    if controller.selected_target.value == "drive":
                        with rv.TextField(
                            label="Google Drive folder",
                            v_model=state.drive_folder.value,
                            on_v_model=state.drive_folder.set,
                            dense=True,
                            placeholder="Drive root",
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            pass

                    if export_kind == "table" and controller.selected_target.value in {
                        "drive",
                        "sepal",
                    }:
                        with rv.Select(
                            label="Table file format",
                            items=TABLE_FILE_FORMATS,
                            v_model=state.table_file_format.value,
                            on_v_model=state.table_file_format.set,
                            dense=True,
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            pass

                    if controller.selected_target.value == "sepal":
                        with rv.TextField(
                            label="SEPAL folder",
                            v_model=state.sepal_folder.value,
                            on_v_model=state.sepal_folder.set,
                            dense=True,
                            placeholder="Relative to the module results directory",
                            hide_details=True,
                            disabled=fields_disabled,
                        ):
                            pass

                    if export_kind == "image":
                        ImageScaleField(scale=state.scale)

                    # Always render the row (fixed height) so showing/clearing
                    # the message never resizes the modal.
                    with rv.Html(tag="div", class_="sepal-export-message"):
                        if validation_message:
                            solara.Text(validation_message, classes=["sepal-export-error"])

                    if not state.notifications_enabled and state.inline_message.value:
                        InlineExportFeedback(
                            message=state.inline_message.value,
                            level=state.inline_level.value,
                        )

            with solara.v.CardActions():
                solara.v.Spacer()
                solara.Button(
                    label="Close",
                    on_click=controller.close_dialog,
                    text=True,
                    disabled=controller.task.pending,
                    small=True,
                )
                TaskButtonComponent(
                    label="Export",
                    cancel_label="Cancel",
                    **button_props,
                    external_busy=submit_disabled,
                    min_width="120px",
                    small=True,
                )


__all__ = ["BandSelectorField", "ExportDialog", "InlineExportFeedback"]
