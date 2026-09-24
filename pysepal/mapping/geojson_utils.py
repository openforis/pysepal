"""Utility functions for creating GeoJSON layers."""

import json
from typing import Optional

import geopandas as gpd
from ipyleaflet import GeoJSON

from pysepal import color
from pysepal.frontend import styles as ss

__all__ = ["get_ipygeojson"]


def get_ipygeojson(
    gdf: gpd.GeoDataFrame,
    name: str = "aoi",
    style: Optional[dict] = None,
) -> GeoJSON:
    """Convert a GeoDataFrame into an ipyleaflet GeoJSON layer.

    This is a standalone utility function that creates a GeoJSON layer from a
    GeoDataFrame, suitable for display on an ipyleaflet Map.

    Args:
        gdf: The GeoDataFrame to convert to a GeoJSON layer.
        name: The name to assign to the layer and as a property to features.
        style: Optional style dictionary for the GeoJSON layer. If None, uses
            the default AOI style with primary color. See ipyleaflet GeoJSON
            documentation for style options.

    Returns:
        An ipyleaflet GeoJSON layer ready to be added to a Map.

    Raises:
        ValueError: If the GeoDataFrame is None or empty.

    Example:
        .. code-block:: python

            import geopandas as gpd
            from pysepal.mapping import get_ipygeojson, SepalMap

            # Create a simple GeoDataFrame
            gdf = gpd.read_file("my_shapefile.shp")

            # Create the GeoJSON layer
            geojson_layer = get_ipygeojson(gdf, name="my_layer")

            # Add to map
            m = SepalMap()
            m.add_layer(geojson_layer)
    """
    if gdf is None or gdf.empty:
        raise ValueError("GeoDataFrame cannot be None or empty")

    # Convert to regular GeoDataFrame to avoid issues with pygadm subclasses
    # This is necessary because pygadm 0.5.3 has a bug with pandas 2.3+ where
    # the __init__ method contains a DataFrame comparison that fails during
    # geopandas' internal to_json() process.
    gdf_plain = gpd.GeoDataFrame(gdf)
    data = json.loads(gdf_plain.to_json())

    # Add name as a property to each feature
    for f in data["features"]:
        f["properties"]["name"] = name

    # Apply default style if not provided
    theme_style = None
    if style is None:
        style = json.loads((ss.JSON_DIR / "aoi.json").read_text())
        style.update(color=color.primary, fillColor=color.primary)
        theme_style = {
            is_dark: {"color": colors["primary"], "fillColor": colors["primary"]}
            for is_dark, colors in ss.THEMES.items()
        }

    layer = GeoJSON(data=data, style=style, name=name)
    layer.theme_style = theme_style

    return layer
