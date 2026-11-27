"""WMS preview utilities for AOI selection.

Helper functions for creating and managing WMS preview layers on maps.
"""

from typing import Any

from pysepal.layers import LayerSpec, TileSource
from pysepal.solara.components.aoi.constants import (
    AOI_PREVIEW_LAYER_ID,
    FAO_GAUL_LAYERS,
    FAO_WMS_BASE_URL,
    WMS_PREVIEW_LAYER_NAME,
)


def create_wms_preview_layer(
    level: int,
    admin_code: str,
    name: str = WMS_PREVIEW_LAYER_NAME,
    attribution: str = "",
    layer_id: str = AOI_PREVIEW_LAYER_ID,
) -> LayerSpec:
    """Create the overlay layer that previews an admin boundary.

    It draws FAO's WMS tiles of the boundary, filtered on its code, without
    fetching the full geometry, in FAO's default styling. Tiles have no bounds:
    fetch them with ``fetch_admin_bounds_async`` to zoom on the boundary.

    Args:
        level: Administrative level (0, 1, or 2)
        admin_code: The admin code to highlight
        name: Layer name (default: "aoi_wms_preview")
        attribution: Attribution shown in the map corner while the layer is visible
        layer_id: Layer id in the map's layer store (default: "aoi_preview")

    Returns:
        a spec in the overlay zone, for ``SepalMap.layer_store``

    Example:
        ```python
        from pysepal.solara.components.aoi import create_wms_preview_layer

        # Create preview layer for Colombia
        map_.layer_store.add(create_wms_preview_layer(level=0, admin_code="62"))
        ```
    """
    url = f"{FAO_WMS_BASE_URL}?CQL_FILTER=gaul{level}_code={admin_code}"
    return LayerSpec.from_tiles(
        TileSource.wms(url, FAO_GAUL_LAYERS[level], format="image/png", transparent=True),
        id=layer_id,
        name=name,
        zone="overlay",
        attribution=attribution,
    )


def remove_wms_preview_layer(map_: Any, layer_id: str = AOI_PREVIEW_LAYER_ID) -> None:
    """Remove the WMS preview layer from a map's layer store, if it is there.

    Args:
        map_: The SepalMap instance
        layer_id: The layer id to remove (default: "aoi_preview")
    """
    map_.layer_store.remove(layer_id, missing_ok=True)
