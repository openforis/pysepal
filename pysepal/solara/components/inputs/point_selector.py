"""Points/CSV file selector Solara component — canonical location.

Provides PointsSelectorComponent for selecting CSV/TXT files with point data
(lat/lng columns).
"""

import asyncio
from typing import Callable, Dict, List, Optional, Union

import pandas as pd
import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg
from pysepal.solara.components.inputs.file_input import FileInputComponent
from pysepal.solara.hooks import _use_draft
from pysepal.solara.notifications import use_notifications

POINT_EXTENSIONS = [".csv", ".txt"]

_LNG_PATTERNS = ["lng", "long", "longitude", "x_coord", "xcoord", "lon"]
_LAT_PATTERNS = ["lat", "latitude", "y_coord", "ycoord"]


def _auto_detect_columns(columns: List[str]) -> Dict[str, Optional[str]]:
    """Auto-detect id, lat, lng columns from column names.

    Scans column names for common patterns and returns the first match
    for each role. Matches are case-insensitive substring checks.

    Args:
        columns: List of column names.

    Returns:
        Dict with 'id_column', 'lat_column', 'lng_column' keys (values may be None).
    """
    result = {"id_column": None, "lat_column": None, "lng_column": None}

    for name in reversed(columns):
        lname = name.lower()
        if "id" in lname:
            result["id_column"] = name
        elif any(p in lname for p in _LNG_PATTERNS):
            result["lng_column"] = name
        elif any(p in lname for p in _LAT_PATTERNS):
            result["lat_column"] = name

    return result


@solara.component
def PointsSelectorComponent(
    initial_folder: str = "",
    value: Union[Optional[Dict], solara.Reactive[Optional[Dict]]] = None,
    on_value: Optional[Callable[[Optional[Dict]], None]] = None,
):
    """Selector component for CSV/TXT files with point data.

    Provides a file browser for CSV/TXT files and three column selectors
    (ID, Latitude, Longitude) with auto-detection of common column names.
    The file-button label auto-hides when the component is rendered inside
    a container narrower than ~450px (CSS container query).

    Args:
        initial_folder: Initial folder shown by the local file picker.
        value: Dict with {pathname, id_column, lat_column, lng_column} or None.
        on_value: Callback when selection changes.
    """
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value

    notifications = use_notifications()
    draft, publish = _use_draft(reactive_value)
    selection = draft.value or {}
    file_path = selection.get("pathname") or ""
    id_column = selection.get("id_column")
    lat_column = selection.get("lat_column")
    lng_column = selection.get("lng_column")

    def select_file(path):
        publish(None)
        draft.set({"pathname": path} if path else None)

    def select_column(role, column):
        draft.set({**draft.value, role: column})

    async def load_columns():
        if not file_path:
            return []
        table = await asyncio.to_thread(pd.read_csv, file_path, sep=None, engine="python", nrows=0)
        return table.columns.tolist()

    column_task = solara.lab.use_task(
        load_columns, dependencies=[file_path], raise_error=False, prefer_threaded=False
    )

    def apply_columns():
        if column_task.error:
            notifications.error(f"Error reading file: {column_task.exception}")
        elif column_task.finished and file_path:
            columns = column_task.value
            if len(columns) < 3:
                notifications.warning(msg("widgets.load_table.too_small"))
                return
            current = draft.value
            detected = _auto_detect_columns(columns)
            draft.set({**detected, **current})

    solara.use_effect(apply_columns, [column_task.finished, column_task.exception])

    def publish_selection():
        if not file_path or column_task.error:
            publish(None)
        elif column_task.finished:
            complete = len(column_task.value) >= 3 and id_column and lat_column and lng_column
            publish(draft.value if complete else None)

    solara.use_effect(publish_selection, [draft.value, column_task.finished, column_task.error])
    column_items = column_task.value or [] if column_task.finished else []

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        FileInputComponent(
            initial_folder=initial_folder,
            extensions=POINT_EXTENSIONS,
            label=msg("widgets.table.label"),
            value=file_path,
            on_value=select_file,
        )

        if file_path:
            with rv.Select(
                label=msg("widgets.table.column.id"),
                items=column_items,
                v_model=id_column,
                on_v_model=lambda column: select_column("id_column", column),
                loading=column_task.pending,
                dense=True,
                clearable=True,
            ):
                pass

            with rv.Select(
                label=msg("widgets.table.column.lat"),
                items=column_items,
                v_model=lat_column,
                on_v_model=lambda column: select_column("lat_column", column),
                loading=column_task.pending,
                dense=True,
                clearable=True,
            ):
                pass

            with rv.Select(
                label=msg("widgets.table.column.lng"),
                items=column_items,
                v_model=lng_column,
                on_v_model=lambda column: select_column("lng_column", column),
                loading=column_task.pending,
                dense=True,
                clearable=True,
            ):
                pass
