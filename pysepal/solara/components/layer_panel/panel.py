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


@solara.component
def LayerPanel(
    store: LayerStore,
    map_=None,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
):
    """List the layers of a store, reorderable, with per-layer controls.

    Use it as a MapApp section, e.g.
    ``{"title": msg("layer_panel.title"), "icon": "mdi-layers", "content": LayerPanel(store)}``.

    Args:
        store: The layer store to show and edit.
        map_: The ``SepalMap`` whose basemaps the picker switches; no picker when None.
        on_export: Called with a Earth Engine layer's spec when its Export button is clicked.
    """
    version = use_layer_store(store)
    is_dark = use_theme_dark()

    ids = store.ids
    if ids:
        content = SortableList(
            ids=ids,
            children=[
                LayerRow(store, layer_id, on_export, is_dark, version).key(layer_id)
                for layer_id in ids
            ],
            on_move=store.move,
        )
    else:
        content = solara.Text(msg("layer_panel.empty"), classes=["pysepal-layer-panel__empty"])

    children = [BasemapPicker(map_)] if map_ is not None else []
    return solara.Column(classes=["pysepal-layer-panel"], children=[*children, content])
