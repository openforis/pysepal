"""The layer panel for the MapApp right panel."""

from typing import Callable, Optional

import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.message import msg
from pysepal.solara.theme import use_theme_dark

from .basemap import BasemapPicker
from .hooks import use_layer_store
from .row import LayerRow
from .sortable import SortableList


def _data_ids(store: LayerStore) -> list[str]:
    """The ids of the data zone, top first."""
    return [layer_id for layer_id in store.ids if store.get(layer_id).zone == "data"]


@solara.component
def LayerPanel(
    store: LayerStore,
    map_=None,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
):
    """List the data layers of a store, reorderable, with per-layer controls.

    The overlay zone (the AOI and its preview) is not listed.

    Use it as a MapApp section, e.g.
    ``{"title": msg("layer_panel.title"), "icon": "mdi-layers", "content": LayerPanel(store)}``.

    Args:
        store: The layer store to show and edit.
        map_: The ``SepalMap`` whose basemaps the picker switches; no picker when None or
            while the map has a single basemap.
        on_export: Called with a Earth Engine layer's spec when its Export button is clicked.
    """
    version = use_layer_store(store)
    is_dark = use_theme_dark()

    compare = bool(map_.state.get("compare")) if map_ is not None else False
    # only re-renders as compare flips, not on every publish of the map
    _, set_compare = solara.use_state(compare)

    def follow_state():
        if map_ is None:
            return None

        def on_change(change):
            set_compare(bool(change["new"].get("compare")))

        map_.observe(on_change, names=["state"])
        # a new map, or a publish between the render and this effect
        set_compare(bool(map_.state.get("compare")))
        return lambda: map_.unobserve(on_change, names=["state"])

    solara.use_effect(follow_state, [map_])

    ids = _data_ids(store)

    def on_move(layer_id: str, to: int) -> None:
        # ``to`` counts the rows; the store also counts the overlay ids between them
        rows = _data_ids(store)
        if layer_id in rows:
            target = rows[max(0, min(to, len(rows) - 1))]
            store.move(layer_id, store.ids.index(target))

    if ids:
        content = SortableList(
            ids=ids,
            children=[
                LayerRow(store, layer_id, map_, on_export, is_dark, version, compare).key(layer_id)
                for layer_id in ids
            ],
            on_move=on_move,
            handle_label=msg("layer_panel.reorder"),
        )
    else:
        content = solara.Text(msg("layer_panel.empty"), classes=["pysepal-layer-panel__empty"])

    children = [BasemapPicker(map_)] if map_ is not None else []
    return solara.Column(classes=["pysepal-layer-panel"], children=[*children, content])
