"""GEE asset selector Solara component.

Provides AssetSelectComponent for selecting Earth Engine assets
with optional column/value filtering (TABLE assets only).
"""

from typing import Callable, Dict, List, Optional, Union

import ee
import reacton.ipyvuetify as rv
import solara

from pysepal.message import ms
from pysepal.solara.notifications import use_notifications
from pysepal.solara.utils import get_current_gee_interface

ASSET_TYPES = {
    "IMAGE": ms.widgets.asset_select.types[0],
    "TABLE": ms.widgets.asset_select.types[1],
    "IMAGE_COLLECTION": ms.widgets.asset_select.types[2],
    "ALGORITHM": ms.widgets.asset_select.types[3],
    "FOLDER": ms.widgets.asset_select.types[4],
}

COLUMN_ALL_ITEMS = [
    {"text": "All features", "value": "ALL"},
    {"divider": True},
]

_EXCLUDED_PROPERTIES = {"system:index", "Shape_Area", "Shape_Leng"}


@solara.component
def AssetSelectComponent(
    types: List[str] = ["IMAGE", "TABLE"],
    folder: str = "",
    value: Union[Optional[Dict], solara.Reactive[Optional[Dict]]] = None,
    on_value: Optional[Callable[[Optional[Dict]], None]] = None,
    loading: Union[bool, solara.Reactive[bool]] = False,
    on_loading: Optional[Callable[[bool], None]] = None,
    gee_interface=None,
):
    """Selector component for GEE assets.

    Loads the user's GEE assets, validates the selection, and (for TABLE assets)
    supports optional column/value filtering.

    Args:
        types: Asset types to list. Defaults to ["IMAGE", "TABLE"].
        folder: GEE folder to list assets from. Defaults to user's root folder.
        value: Dict with {asset_id, type, column, value} or None.
        on_value: Callback when selection changes.
        loading: Whether the component is busy (loading assets, validating, etc.).
        on_loading: Callback when loading state changes.
        gee_interface: Optional GEEInterface instance. Falls back to session default.
    """
    reactive_value = solara.use_reactive(value, on_value)
    reactive_loading = solara.use_reactive(loading, on_loading)
    del value, on_value, loading, on_loading

    gee_interface = gee_interface or get_current_gee_interface()
    notifications = use_notifications()

    asset_id = solara.use_reactive(None)
    asset_type = solara.use_reactive(None)
    asset_items = solara.use_reactive([])
    selected_column = solara.use_reactive("ALL")
    selected_value = solara.use_reactive(None)
    column_items = solara.use_reactive([])
    value_items = solara.use_reactive([])
    loading_assets = solara.use_reactive(True)
    loading_columns = solara.use_reactive(False)
    loading_values = solara.use_reactive(False)
    validation_msg = solara.use_reactive("")

    # What this component last published. An incoming value that differs came from
    # outside, so the widgets are seeded from it. Comparing rather than flagging keeps
    # the effect idempotent under reacton's double effect-run.
    published = solara.use_ref(None)

    # The caller's selection, held until the asset-change cascade consumes it. Kept
    # apart from `published` on purpose: that ref is overwritten by our own
    # intermediate publishes (the cascade emits column="ALL" on its way through),
    # which would erase the filter we are trying to restore before we read it.
    pending_seed = solara.use_ref(None)

    def _seed_from_value():
        incoming = reactive_value.value
        if not incoming or incoming == published.current:
            return
        published.current = incoming
        pending_seed.current = incoming
        if incoming.get("asset_id") == asset_id.value:
            # Same asset, different filter. Writing the same id back is a store
            # no-op, so on_asset_change never re-runs and the widgets would keep
            # showing the old filter — apply it here instead.
            selected_column.set(incoming.get("column") or "ALL")
            selected_value.set(incoming.get("value"))
            return
        asset_id.set(incoming.get("asset_id"))
        asset_type.set(incoming.get("type"))

    solara.use_effect(_seed_from_value, [reactive_value.value])

    def _sync_loading():
        reactive_loading.set(loading_assets.value or loading_columns.value or loading_values.value)

    solara.use_effect(
        _sync_loading,
        [loading_assets.value, loading_columns.value, loading_values.value],
    )

    async def load_assets():
        loading_assets.set(True)
        try:
            folder_path = folder or await gee_interface.get_folder_async()
            raw_assets = await gee_interface.get_assets_async(folder_path)

            assets = {k: sorted([e["id"] for e in raw_assets if e["type"] == k]) for k in types}

            items = []
            for k in types:
                if assets[k]:
                    items += [
                        {"divider": True},
                        {"header": ASSET_TYPES.get(k, k)},
                        *assets[k],
                    ]

            if not items:
                asset_items.set(
                    [
                        {
                            "text": ms.widgets.asset_select.no_assets.format(folder_path or "root"),
                            "disabled": True,
                        }
                    ]
                )
            else:
                asset_items.set(items)
        except Exception as e:
            notifications.error(f"Error loading assets: {e}")
            asset_items.set([])
        finally:
            loading_assets.set(False)

    # Keep session-backed GEE coroutines on Solara's current event loop.
    solara.lab.use_task(
        load_assets,
        dependencies=[],
        raise_error=False,
        prefer_threaded=False,
    )

    async def on_asset_change():
        aid = asset_id.value
        asset_type.set(None)
        selected_column.set("ALL")
        selected_value.set(None)
        column_items.set([])
        value_items.set([])
        validation_msg.set("")

        if not aid:
            reactive_value.set(None)
            return

        loading_columns.set(True)
        try:
            asset_info = await gee_interface.get_asset_async(aid.strip())

            if asset_info["type"] not in types:
                validation_msg.set(
                    ms.widgets.asset_select.wrong_type.format(asset_info["type"], ",".join(types))
                )
                reactive_value.set(None)
                return

            asset_type.set(asset_info["type"])

            if asset_info["type"] == "TABLE":
                info = await gee_interface.get_info_async(ee.FeatureCollection(aid).first())
                cols = sorted(
                    [str(col) for col in info["properties"] if col not in _EXCLUDED_PROPERTIES]
                )
                column_items.set(COLUMN_ALL_ITEMS + cols)

            seeded = pending_seed.current or {}
            column = seeded.get("column", "ALL") if seeded.get("asset_id") == aid else "ALL"
            filter_value = seeded.get("value") if column != "ALL" else None
            if column != "ALL":
                selected_column.set(column)
            if filter_value is not None:
                selected_value.set(filter_value)

            published.current = {
                "asset_id": aid,
                "type": asset_info["type"],
                "column": column,
                "value": filter_value,
            }
            reactive_value.set(published.current)
        except ValueError as e:
            validation_msg.set(str(e))
            reactive_value.set(None)
        except Exception:
            notifications.error(ms.widgets.asset_select.no_access)
            reactive_value.set(None)
        finally:
            loading_columns.set(False)

    solara.lab.use_task(
        on_asset_change,
        dependencies=[asset_id.value],
        raise_error=False,
        prefer_threaded=False,
    )

    async def on_column_change():
        col = selected_column.value
        seeded = pending_seed.current or {}
        # Restoring a filter writes the column and then the value, but this reaction
        # runs in between and would null the value straight back out — reactive
        # writes made inside an effect do not flush nested effects until the pass
        # ends. Skip the reset for the column we are restoring.
        restoring_this_column = (
            seeded.get("asset_id") == asset_id.value
            and seeded.get("column") == col
            and seeded.get("value") is not None
        )
        if not restoring_this_column:
            selected_value.set(None)
        value_items.set([])

        aid = asset_id.value
        if not aid or not col or col == "ALL" or asset_type.value != "TABLE":
            if aid:
                published.current = {
                    "asset_id": aid,
                    "type": asset_type.value,
                    "column": col,
                    "value": None,
                }
                reactive_value.set(published.current)
            return

        loading_values.set(True)
        try:
            fc = ee.FeatureCollection(aid)
            vals = await gee_interface.get_info_async(fc.distinct(col).aggregate_array(col))
            value_items.set(sorted(set(vals)))
            if restoring_this_column:
                selected_value.set(seeded["value"])
        except Exception as e:
            notifications.error(f"Error loading column values: {e}")
            value_items.set([])
        finally:
            loading_values.set(False)

    solara.lab.use_task(
        on_column_change,
        dependencies=[selected_column.value],
        raise_error=False,
        prefer_threaded=False,
    )

    def on_value_change():
        aid = asset_id.value
        if aid and selected_column.value:
            published.current = {
                "asset_id": aid,
                "type": asset_type.value,
                "column": selected_column.value,
                "value": selected_value.value,
            }
            reactive_value.set(published.current)

    solara.use_effect(on_value_change, [selected_value.value])

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        with rv.Combobox(
            label=ms.widgets.asset_select.label,
            items=asset_items.value,
            v_model=asset_id.value,
            on_v_model=asset_id.set,
            clearable=True,
            dense=True,
            loading=loading_assets.value or loading_columns.value,
            placeholder=ms.widgets.asset_select.placeholder,
            prepend_icon="mdi-sync",
            error=bool(validation_msg.value),
            error_messages=validation_msg.value or None,
        ):
            pass

        if column_items.value and not validation_msg.value:
            with rv.Select(
                label="Column",
                items=column_items.value,
                v_model=selected_column.value,
                on_v_model=selected_column.set,
                dense=True,
                loading=loading_columns.value,
            ):
                pass

            if selected_column.value and selected_column.value != "ALL":
                with rv.Select(
                    label="Value",
                    items=value_items.value,
                    v_model=selected_value.value,
                    on_v_model=selected_value.set,
                    dense=True,
                    clearable=True,
                    loading=loading_values.value,
                ):
                    pass
