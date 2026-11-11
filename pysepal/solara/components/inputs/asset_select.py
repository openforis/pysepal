"""GEE asset selector Solara component.

Provides AssetSelectComponent for selecting Earth Engine assets
with optional column/value filtering (TABLE assets only).
"""

from typing import Callable, Dict, List, Optional, Union

import ee
import reacton.ipyvuetify as rv
import solara
from reacton import ipyvue

from pysepal._vuetify import IPYVUETIFY_V3, density, field_variant, select_items
from pysepal.message import msg
from pysepal.solara.components.inputs.gee_assets import use_gee_assets
from pysepal.solara.hooks import _use_draft
from pysepal.solara.notifications import use_notifications
from pysepal.solara.utils import get_current_gee_interface

# Catalogue key of each asset type, rendered with msg() where it is shown.
ASSET_TYPES = {
    "IMAGE": "widgets.asset_select.types.0",
    "TABLE": "widgets.asset_select.types.1",
    "IMAGE_COLLECTION": "widgets.asset_select.types.2",
    "ALGORITHM": "widgets.asset_select.types.3",
    "FOLDER": "widgets.asset_select.types.4",
}

COLUMN_ALL_ITEMS = [
    {"text": "All features", "value": "ALL"},
    {"divider": True},
]

_EXCLUDED_PROPERTIES = {"system:index", "Shape_Area", "Shape_Leng"}


def _use_commit_on_enter_or_blur(field, commit: Callable[[Optional[str]], None]) -> None:
    """Hand ``commit`` the typed text when the user presses Enter or leaves ``field``.

    Only on Vuetify 3: a Vuetify 2 combobox moves v_model there itself. The installed
    major never changes in a process, so the hook order is stable.
    """
    if not IPYVUETIFY_V3:
        return

    def on_enter(widget, *_ignore):
        commit(widget.v_model)

    def on_focus(widget, _event, focused):
        if not focused:
            commit(widget.v_model)

    ipyvue.use_event(field, "keydown.enter", on_enter)
    ipyvue.use_event(field, "update:focused", on_focus)


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
            The list is shared with every field of the session listing the same
            folder (see :func:`use_gee_assets`). The sync icon lists the assets
            again for every field of the session.
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
    notifications = use_notifications(required=False)
    draft, publish = _use_draft(reactive_value)
    selection = draft.value or {}
    asset_id = selection.get("asset_id")
    asset_type = selection.get("type")
    selected_column = selection.get("column") or "ALL"
    selected_value = selection.get("value")
    listing = use_gee_assets(folder, gee_interface)

    def select_asset(aid):
        publish(None)
        draft.set({"asset_id": aid, "type": None, "column": "ALL", "value": None} if aid else None)

    def select_column(column):
        draft.set({**draft.value, "column": column or "ALL", "value": None})

    def select_value(value):
        draft.set({**draft.value, "value": value})

    asset_items = []
    listed_ids = set()
    for k in types:
        ids = sorted(e["id"] for e in listing.assets if e.get("type") == k)
        listed_ids.update(ids)
        if ids:
            asset_items += [
                {"divider": True},
                {"header": msg(ASSET_TYPES[k]) if k in ASSET_TYPES else k},
                *ids,
            ]
    if not asset_items and not listing.loading and listing.error is None:
        asset_items = [
            {
                "text": msg("widgets.asset_select.no_assets", folder=listing.folder or "root"),
                "disabled": True,
            }
        ]

    def report_listing_error():
        if listing.error is not None:
            notifications.error(f"Error loading assets: {listing.error}")

    solara.use_effect(report_listing_error, [listing.error])

    async def load_asset():
        if not asset_id:
            return None
        info = await gee_interface.get_asset_async(asset_id.strip())
        if info["type"] not in types:
            raise ValueError(
                msg(
                    "widgets.asset_select.wrong_type",
                    asset_type=info["type"],
                    allowed=",".join(types),
                )
            )
        columns = []
        if info["type"] == "TABLE":
            feature = await gee_interface.get_info_async(ee.FeatureCollection(asset_id).first())
            columns = sorted(
                str(col) for col in feature["properties"] if col not in _EXCLUDED_PROPERTIES
            )
        return info["type"], columns

    asset_task = solara.lab.use_task(
        load_asset, dependencies=[asset_id], raise_error=False, prefer_threaded=False
    )

    # A wrong asset type is a fault in what the user typed, so it is reported under
    # the field. Anything else is an access failure they cannot see there.
    wrong_type = str(asset_task.exception) if isinstance(asset_task.exception, ValueError) else ""

    def apply_asset():
        if asset_task.error:
            if not wrong_type:
                notifications.error(msg("widgets.asset_select.no_access"))
        elif asset_task.finished and asset_task.value is not None:
            draft.set({**draft.value, "type": asset_task.value[0]})

    solara.use_effect(apply_asset, [asset_task.finished, asset_task.exception])

    async def load_values():
        if not asset_id or selected_column == "ALL" or asset_type != "TABLE":
            return []
        fc = ee.FeatureCollection(asset_id)
        values = await gee_interface.get_info_async(
            fc.distinct(selected_column).aggregate_array(selected_column)
        )
        return sorted(set(values))

    value_task = solara.lab.use_task(
        load_values,
        dependencies=[asset_id, asset_type, selected_column],
        raise_error=False,
        prefer_threaded=False,
    )

    def report_value_error():
        if value_task.error:
            notifications.error(f"Error loading column values: {value_task.exception}")

    solara.use_effect(report_value_error, [value_task.exception])

    def publish_selection():
        if not asset_id or asset_task.error:
            publish(None)
        elif asset_task.finished and asset_type is not None:
            publish(
                {
                    "asset_id": asset_id,
                    "type": asset_type,
                    "column": selected_column,
                    "value": selected_value,
                }
            )

    solara.use_effect(publish_selection, [draft.value, asset_task.finished, asset_task.error])

    def sync_loading():
        reactive_loading.set(listing.loading or asset_task.pending or value_task.pending)

    solara.use_effect(sync_loading, [listing.loading, asset_task.pending, value_task.pending])
    column_items = []
    if asset_task.finished and asset_task.value and asset_task.value[0] == "TABLE":
        column_items = COLUMN_ALL_ITEMS + asset_task.value[1]
    value_items = value_task.value or [] if value_task.finished else []
    validation_msg = wrong_type

    def reload_assets(*_ignore):
        listing.reload()

    # A Vuetify 3 combobox moves v_model on every keystroke, where Vuetify 2 moved it
    # on blur or Enter. Each move is an asset lookup, so on Vuetify 3 a typed id only
    # counts once it is complete: a listed asset or an empty field at once, any other
    # text on blur or Enter, as Vuetify 2 did.
    def type_asset(text):
        if not text or text in listed_ids:
            commit_asset(text)

    def commit_asset(text):
        if text != (draft.value or {}).get("asset_id"):
            select_asset(text)

    with solara.Column(classes="pa-0 ma-0", style="gap: 8px;"):
        asset_field = rv.Combobox(
            label=msg("widgets.asset_select.label"),
            items=select_items(asset_items),
            v_model=asset_id,
            on_v_model=type_asset if IPYVUETIFY_V3 else select_asset,
            clearable=True,
            loading=listing.loading or asset_task.pending,
            placeholder=msg("widgets.asset_select.placeholder"),
            # Vuetify 2 shows a placeholder unfocused; Vuetify 3 needs to be told.
            **({"persistent_placeholder": True} if IPYVUETIFY_V3 else {}),
            prepend_inner_icon="mdi-sync",
            error=bool(validation_msg),
            error_messages=validation_msg or None,
            **density(),
            **field_variant(),
        )
        ipyvue.use_event(asset_field, "click:prepend-inner", reload_assets)
        _use_commit_on_enter_or_blur(asset_field, commit_asset)

        if column_items and not validation_msg:
            with rv.Select(
                label="Column",
                items=select_items(column_items),
                v_model=selected_column,
                on_v_model=select_column,
                loading=asset_task.pending,
                **density(),
                **field_variant(),
            ):
                pass

            if selected_column != "ALL":
                with rv.Select(
                    label="Value",
                    items=value_items,
                    v_model=selected_value,
                    on_v_model=select_value,
                    clearable=True,
                    loading=value_task.pending,
                    **density(),
                    **field_variant(),
                ):
                    pass
