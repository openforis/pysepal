"""Draw geometry processing.

Functions for processing geometries drawn on the map from the map's drawing tools.
"""

from datetime import datetime as dt
from typing import Any, Dict, Optional

import geopandas as gpd

from pysepal.message import msg
from pysepal.scripts import utils as su
from pysepal.scripts.gee_interface import refuse_ambient_session_per_connection
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec

# What a drawn feature carries besides the caller's own properties: the map drops the
# other names Terra Draw reserves.
_DRAWING_PROPERTIES = frozenset({"mode", "radiusKilometers", "style"})


def process_draw(
    geo_json: Dict,
    name: str = "",
    gee: bool = True,
    gee_interface: Optional[Any] = None,
) -> AoiResult:
    """Process a drawn geometry from map interaction.

    Converts a GeoJSON dict (from ``m.draw.features``) into an AoiResult.

    Args:
        geo_json: GeoJSON dict with 'features' key from ``m.draw.features``
        name: Optional name for the AOI. If empty, generates timestamp-based name.
        gee: If True, create Earth Engine FeatureCollection
        gee_interface: The session's interface. Omitting it is only accepted
            where the process serves a single identity.

    Returns:
        AoiResult with the drawn geometry

    Raises:
        ValueError: If geo_json is empty or invalid

    Example:
        ```python
        from pysepal.solara.components.aoi import process_draw

        # From the map's drawing tools
        features = m.draw.features
        result = process_draw(features, name="my_area", gee=False)
        ```
    """
    if not geo_json or not geo_json.get("features"):
        raise ValueError(msg("aoi_sel.exception.no_draw"))

    # Clean style properties from features
    cleaned_features = []
    for feat in geo_json["features"]:
        cleaned_feat = feat.copy()
        if cleaned_feat.get("properties"):
            cleaned_feat["properties"] = {
                k: v for k, v in cleaned_feat["properties"].items() if k not in _DRAWING_PROPERTIES
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
        # Before init_ee(): a refusal must leave the global ee unbound.
        if gee_interface is None:
            refuse_ambient_session_per_connection()

        su.init_ee()
        feature_collection = su.geojson_to_ee(gdf.__geo_interface__)

    return AoiResult(
        method="DRAW",
        name=name,
        gdf=gdf,
        feature_collection=feature_collection,
        admin=None,
        gee=gee,
        spec=AoiSpec(method="DRAW", name=name, geo_json=cleaned_geojson),
    )
