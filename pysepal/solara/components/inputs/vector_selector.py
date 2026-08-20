"""Vector file selector Solara component — canonical location.

Provides VectorSelectorComponent for selecting local vector files
with optional column/value filtering.
"""

import asyncio
from typing import Callable, Dict, List, Optional, Union

import geopandas as gpd
import reacton.ipyvuetify as rv
import solara

from pysepal.message import ms
from pysepal.solara.components.inputs.file_input import FileInputComponent
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

    file_path = solara.use_reactive("")
    selected_column = solara.use_reactive("ALL")
    selected_value = solara.use_reactive(None)
    column_items = solara.use_reactive([])
    value_items = solara.use_reactive([])
    loading_columns = solara.use_reactive(False)
    loading_values = solara.use_reactive(False)

    # `published` suppresses the echo of our own output; `pending_seed` holds the
    # caller's selection until the column cascade consumes it. They must stay
    # separate — the cascade publishes column="ALL" on its way through, which would
    # otherwise erase the filter we are restoring before we read it.
    published = solara.use_ref(None)
    pending_seed = solara.use_ref(None)

    def _seed_from_value():
        incoming = reactive_value.value
        if not incoming or incoming == published.current:
            return
        published.current = incoming
        pending_seed.current = incoming
        if (incoming.get("pathname") or "") == file_path.value:
            # Same file, different filter: writing the same path back is a no-op,
            # so on_file_change never re-runs. Apply the filter directly.
            selected_column.set(incoming.get("column") or "ALL")
            selected_value.set(incoming.get("value"))
            return
        file_path.set(incoming.get("pathname") or "")

    solara.use_effect(_seed_from_value, [reactive_value.value])

    # --- File change: read columns in a background task ---

    async def _load_columns(path: str):
        cols = await asyncio.to_thread(_read_columns_from_file, path)
        return cols

    column_task = solara.lab.use_task(
        _load_columns,
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )

    def on_file_change():
        path = file_path.value
        selected_column.set("ALL")
        selected_value.set(None)
        column_items.set([])
        value_items.set([])

        if not path:
            reactive_value.set(None)
            return

        column_task(path)

    solara.use_effect(on_file_change, [file_path.value])

    def _handle_column_task():
        loading_columns.set(column_task.pending)
        if column_task.finished and column_task.value is not None:
            column_items.set(COLUMN_ALL_ITEMS + column_task.value)
            seeded = pending_seed.current or {}
            if seeded.get("pathname") == file_path.value and seeded.get("column", "ALL") != "ALL":
                selected_column.set(seeded["column"])
                if seeded.get("value") is not None:
                    selected_value.set(seeded["value"])
                return
            published.current = {"pathname": file_path.value, "column": "ALL", "value": None}
            reactive_value.set(published.current)
        elif column_task.error:
            column_items.set([])
            reactive_value.set(None)
            notifications.error(f"Error reading columns: {column_task.exception}")

    solara.use_effect(
        _handle_column_task,
        [column_task.pending, column_task.finished, column_task.error],
    )

    # --- Column change: read unique values in a background task ---

    async def _load_values(path: str, col: str):
        vals = await asyncio.to_thread(_read_column_values, path, col)
        return vals

    value_task = solara.lab.use_task(
        _load_values,
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )

    def on_column_change():
        col = selected_column.value
        seeded = pending_seed.current or {}
        # Restoring a filter writes the column and then the value, but this reaction
        # runs in between and would null the value straight back out.
        restoring_this_column = (
            seeded.get("pathname") == file_path.value
            and seeded.get("column") == col
            and seeded.get("value") is not None
        )
        if not restoring_this_column:
            selected_value.set(None)
        value_items.set([])

        if not file_path.value or not col or col == "ALL":
            if file_path.value:
                published.current = {"pathname": file_path.value, "column": col, "value": None}
                reactive_value.set(published.current)
            return

        value_task(file_path.value, col)

    solara.use_effect(on_column_change, [selected_column.value])

    def _handle_value_task():
        loading_values.set(value_task.pending)
        if value_task.finished and value_task.value is not None:
            value_items.set(value_task.value)
        elif value_task.error:
            value_items.set([])
            notifications.error(f"Error reading values: {value_task.exception}")

    solara.use_effect(
        _handle_value_task,
        [value_task.pending, value_task.finished, value_task.error],
    )

    def on_value_change():
        if file_path.value and selected_column.value:
            published.current = {
                "pathname": file_path.value,
                "column": selected_column.value,
                "value": selected_value.value,
            }
            reactive_value.set(published.current)

    solara.use_effect(on_value_change, [selected_value.value])

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        FileInputComponent(
            initial_folder=initial_folder,
            extensions=VECTOR_EXTENSIONS,
            label=ms.widgets.vector.label,
            value=file_path,
        )

        if file_path.value:
            with rv.Select(
                label=ms.widgets.vector.column,
                items=column_items.value,
                v_model=selected_column.value,
                on_v_model=selected_column.set,
                dense=True,
                loading=loading_columns.value,
            ):
                pass

            if selected_column.value and selected_column.value != "ALL":
                with rv.Select(
                    label=ms.widgets.vector.value,
                    items=value_items.value,
                    v_model=selected_value.value,
                    on_v_model=selected_value.set,
                    dense=True,
                    clearable=True,
                    loading=loading_values.value,
                ):
                    pass
