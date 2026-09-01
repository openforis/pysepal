"""Draw geometry processing.

Functions for processing geometries drawn on the map using DrawControl.
"""

from datetime import datetime as dt
from typing import Dict

import geopandas as gpd

from pysepal.message import msg
from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.aoi_result import AoiResult


def process_draw(
    geo_json: Dict,
    name: str = "",
    gee: bool = True,
) -> AoiResult:
    """Process a drawn geometry from map interaction.

    Converts a GeoJSON dict (from DrawControl) into an AoiResult.

    Args:
        geo_json: GeoJSON dict with 'features' key from DrawControl.get_data()
        name: Optional name for the AOI. If empty, generates timestamp-based name.
        gee: If True, create Earth Engine FeatureCollection

    Returns:
        AoiResult with the drawn geometry

    Raises:
        ValueError: If geo_json is empty or invalid

    Example:
        ```python
        from pysepal.solara.components.aoi import process_draw

        # From DrawControl
        features = draw_control.get_data()
        result = process_draw(features, name="my_area", gee=False)
        ```
    """
    if not geo_json or not geo_json.get("features"):
        raise ValueError(msg("aoi_sel.exception.no_draw"))

    # Clean style properties from features
    cleaned_features = []
    for feat in geo_json["features"]:
        cleaned_feat = feat.copy()
        if "properties" in cleaned_feat and "style" in cleaned_feat.get("properties", {}):
            cleaned_feat["properties"] = {
                k: v for k, v in cleaned_feat["properties"].items() if k != "style"
            }
        cleaned_features.append(cleaned_feat)

    cleaned_geojson = {"type": "FeatureCollection", "features": cleaned_features}

    # Create GeoDataFrame
    gdf = gpd.GeoDataFrame.from_features(cleaned_geojson).set_crs(epsg=4326)

    # Generate name if not provided
    if not name:
        name = f"drawn_{dt.now().strftime('%Y%m%d_%H%M%S')}"
    else:
        name = su.normalize_str(name)

    feature_collection = None
    if gee:
        su.init_ee()
        feature_collection = su.geojson_to_ee(gdf.__geo_interface__)

    return AoiResult(
        method="DRAW",
        name=name,
        gdf=gdf,
        feature_collection=feature_collection,
        admin=None,
        gee=gee,
    )
