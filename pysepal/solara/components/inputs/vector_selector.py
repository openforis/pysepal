"""Vector file selector Solara component — canonical location.

Provides VectorSelectorComponent for selecting local vector files
with optional column/value filtering.
"""

import asyncio
from typing import Callable, Dict, List, Optional, Union

import geopandas as gpd
import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg
from pysepal.solara.components.inputs.file_input import FileInputComponent
from pysepal.solara.hooks import _use_draft
from pysepal.solara.notifications import use_notifications

VECTOR_EXTENSIONS = [".shp", ".geojson", ".gpkg", ".kml"]

COLUMN_ALL_ITEMS = [
    {"text": "All features", "value": "ALL"},
    {"divider": True},
]


def _read_columns_from_file(pathname: str) -> List[str]:
    """Read column names from a local vector file.

    Args:
        pathname: Path to a vector file.

    Returns:
        Sorted list of column names (excluding geometry).
    """
    df = gpd.read_file(pathname, ignore_geometry=True, rows=0)
    return sorted(df.columns.tolist())


def _read_column_values(pathname: str, column: str) -> List:
    """Read unique values from a specific column in a vector file.

    Args:
        pathname: Path to a vector file.
        column: Column name.

    Returns:
        Sorted list of unique values.
    """
    df = gpd.read_file(pathname, ignore_geometry=True)
    return sorted(set(df[column].dropna().tolist()))


@solara.component
def VectorSelectorComponent(
    gee: bool = False,
    initial_folder: str = "",
    value: Union[Optional[Dict], solara.Reactive[Optional[Dict]]] = None,
    on_value: Optional[Callable[[Optional[Dict]], None]] = None,
):
    """Selector component for local vector files.

    Provides a file browser for local vector files with optional column/value
    filtering. When a file is selected, reads its columns and lets the user
    filter to specific features. FileInput is responsive on its own (auto-
    hides its button label in narrow containers).

    Args:
        gee: Whether to use GEE assets (currently only local files supported).
        initial_folder: Initial folder shown by the local file picker.
        value: Dict with {pathname, column, value} or None.
        on_value: Callback when selection changes.
    """
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value

    notifications = use_notifications()
    draft, publish = _use_draft(reactive_value)
    selection = draft.value or {}
    file_path = selection.get("pathname") or ""
    selected_column = selection.get("column") or "ALL"
    selected_value = selection.get("value")

    def select_file(path):
        publish(None)
        draft.set({"pathname": path, "column": "ALL", "value": None} if path else None)

    def select_column(column):
        draft.set({**draft.value, "column": column or "ALL", "value": None})

    def select_value(value):
        draft.set({**draft.value, "value": value})

    async def load_columns():
        if not file_path:
            return []
        return await asyncio.to_thread(_read_columns_from_file, file_path)

    column_task = solara.lab.use_task(
        load_columns, dependencies=[file_path], raise_error=False, prefer_threaded=False
    )

    async def load_values():
        if not file_path or selected_column == "ALL":
            return []
        return await asyncio.to_thread(_read_column_values, file_path, selected_column)

    value_task = solara.lab.use_task(
        load_values,
        dependencies=[file_path, selected_column],
        raise_error=False,
        prefer_threaded=False,
    )

    def publish_selection():
        if not file_path or column_task.error:
            publish(None)
        elif column_task.finished:
            publish({"pathname": file_path, "column": selected_column, "value": selected_value})

    solara.use_effect(publish_selection, [draft.value, column_task.finished, column_task.error])

    def report_errors():
        if column_task.error:
            notifications.error(f"Error reading columns: {column_task.exception}")
        if value_task.error:
            notifications.error(f"Error reading values: {value_task.exception}")

    solara.use_effect(report_errors, [column_task.exception, value_task.exception])
    column_items = COLUMN_ALL_ITEMS + (column_task.value or []) if column_task.finished else []
    value_items = value_task.value or [] if value_task.finished else []

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        FileInputComponent(
            initial_folder=initial_folder,
            extensions=VECTOR_EXTENSIONS,
            label=msg("widgets.vector.label"),
            value=file_path,
            on_value=select_file,
        )

        if file_path:
            with rv.Select(
                label=msg("widgets.vector.column"),
                items=column_items,
                v_model=selected_column,
                on_v_model=select_column,
                dense=True,
                loading=column_task.pending,
            ):
                pass

            if selected_column != "ALL":
                with rv.Select(
                    label=msg("widgets.vector.value"),
                    items=value_items,
                    v_model=selected_value,
                    on_v_model=select_value,
                    dense=True,
                    clearable=True,
                    loading=value_task.pending,
                ):
                    pass
