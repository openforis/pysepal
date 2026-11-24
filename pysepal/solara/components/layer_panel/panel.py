"""The layer panel for the MapApp right panel."""

from typing import Callable, Optional

import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.message import msg
from pysepal.solara.theme import use_theme_dark

from .hooks import use_layer_store
from .row import LayerRow
from .sortable import SortableList


def _zone_ids(store: LayerStore, zone: str) -> list[str]:
    """The ids of one zone, top first."""
    return [layer_id for layer_id in store.ids if store.get(layer_id).zone == zone]


@solara.component
def LayerPanel(
    store: LayerStore,
    map_=None,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
):
    """List the layers of a store, reorderable, with per-layer controls.

    The overlay zone (the AOI and its preview) comes first, as the map draws it above
    every data layer, and keeps its place: its handles are dimmed, and no data row moves
    above it.

    Use it as a MapApp section, e.g.
    ``{"title": msg("layer_panel.title"), "icon": "mdi-layers", "content": LayerPanel(store)}``.

    Args:
        store: The layer store to show and edit.
        map_: The ``SepalMap`` the rows zoom and whose compare they follow; without it the
            rows have no zoom button and no side choice.
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

    ids = store.ids  # the overlay zone first

    def on_move(layer_id: str, to: int) -> None:
        # ``to`` counts every row; the data rows come after the overlay ones
        overlay, rows = _zone_ids(store, "overlay"), _zone_ids(store, "data")
        if layer_id in rows:
            target = rows[max(0, min(to - len(overlay), len(rows) - 1))]
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
            locked=_zone_ids(store, "overlay"),
        )
    else:
        content = solara.Text(msg("layer_panel.empty"), classes=["pysepal-layer-panel__empty"])

    return solara.Column(classes=["pysepal-layer-panel"], children=[content])
