"""WMS preview utilities for AOI selection.

Helper functions for creating and managing WMS preview layers on maps.
"""

from typing import Any

from ipyleaflet import WMSLayer

from pysepal.solara.components.aoi.constants import (
    FAO_GAUL_LAYERS,
    FAO_WMS_BASE_URL,
    WMS_PREVIEW_LAYER_NAME,
)


def create_wms_preview_layer(
    level: int,
    admin_code: str,
    name: str = WMS_PREVIEW_LAYER_NAME,
    attribution: str = "",
) -> WMSLayer:
    """Create an ipyleaflet WMSLayer for previewing an admin boundary.

    This creates a lightweight WMS layer that displays the admin boundary
    on the map without fetching the full geometry. Uses FAO's default styling.

    Args:
        level: Administrative level (0, 1, or 2)
        admin_code: The admin code to highlight
        name: Layer name for identification (default: "aoi_wms_preview")
        attribution: Attribution shown in the map corner while the layer is visible

    Returns:
        ipyleaflet.WMSLayer configured to display the admin boundary

    Example:
        ```python
        from pysepal.solara.components.aoi import create_wms_preview_layer

        # Create preview layer for Colombia
        layer = create_wms_preview_layer(level=0, admin_code="62")
        map_.add_layer(layer)
        ```
    """
    # Use the appropriate layer for the level
    wms_layer = FAO_GAUL_LAYERS[level]
    cql_filter = f"gaul{level}_code={admin_code}"

    # Build URL with CQL_FILTER
    url = f"{FAO_WMS_BASE_URL}?CQL_FILTER={cql_filter}"

    return WMSLayer(
        url=url,
        layers=wms_layer,
        format="image/png",
        transparent=True,
        name=name,
        attribution=attribution,
    )


def remove_wms_preview_layer(map_: Any, name: str = WMS_PREVIEW_LAYER_NAME) -> None:
    """Remove WMS preview layer from map if it exists.

    Args:
        map_: The ipyleaflet Map or SepalMap instance
        name: The layer name to remove (default: "aoi_wms_preview")
    """
    for layer in list(map_.layers):
        if hasattr(layer, "name") and layer.name == name:
            map_.remove_layer(layer)
