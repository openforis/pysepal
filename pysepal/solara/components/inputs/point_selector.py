"""Points/CSV file selector Solara component — canonical location.

Provides PointsSelectorComponent for selecting CSV/TXT files with point data
(lat/lng columns).
"""

from typing import Callable, Dict, List, Optional, Union

import pandas as pd
import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg
from pysepal.solara.components.inputs.file_input import FileInputComponent
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

    file_path = solara.use_reactive("")
    column_items = solara.use_reactive([])
    id_column = solara.use_reactive(None)
    lat_column = solara.use_reactive(None)
    lng_column = solara.use_reactive(None)

    def on_file_change():
        path = file_path.value
        column_items.set([])
        id_column.set(None)
        lat_column.set(None)
        lng_column.set(None)
        reactive_value.set(None)

        if not path:
            return

        try:
            df = pd.read_csv(path, sep=None, engine="python", nrows=0)
            cols = df.columns.tolist()

            if len(cols) < 3:
                notifications.warning(msg("widgets.load_table.too_small"))
                return

            column_items.set(cols)

            detected = _auto_detect_columns(cols)
            if detected["id_column"]:
                id_column.set(detected["id_column"])
            if detected["lat_column"]:
                lat_column.set(detected["lat_column"])
            if detected["lng_column"]:
                lng_column.set(detected["lng_column"])

        except Exception as e:
            notifications.error(f"Error reading file: {e}")

    solara.use_effect(on_file_change, [file_path.value])

    def update_output():
        if file_path.value and id_column.value and lat_column.value and lng_column.value:
            reactive_value.set(
                {
                    "pathname": file_path.value,
                    "id_column": id_column.value,
                    "lat_column": lat_column.value,
                    "lng_column": lng_column.value,
                }
            )
        elif file_path.value:
            reactive_value.set(None)
        else:
            reactive_value.set(None)

    solara.use_effect(
        update_output,
        [file_path.value, id_column.value, lat_column.value, lng_column.value],
    )

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        FileInputComponent(
            initial_folder=initial_folder,
            extensions=POINT_EXTENSIONS,
            label=msg("widgets.table.label"),
            value=file_path,
        )

        if column_items.value:
            with rv.Select(
                label=msg("widgets.table.column.id"),
                items=column_items.value,
                v_model=id_column.value,
                on_v_model=id_column.set,
                dense=True,
                clearable=True,
            ):
                pass

            with rv.Select(
                label=msg("widgets.table.column.lat"),
                items=column_items.value,
                v_model=lat_column.value,
                on_v_model=lat_column.set,
                dense=True,
                clearable=True,
            ):
                pass

            with rv.Select(
                label=msg("widgets.table.column.lng"),
                items=column_items.value,
                v_model=lng_column.value,
                on_v_model=lng_column.set,
                dense=True,
                clearable=True,
            ):
                pass
