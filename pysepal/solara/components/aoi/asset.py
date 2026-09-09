"""GEE asset processing for AOI selection.

Contains the process_asset function that converts a supported GEE asset
into an AoiResult that can be rendered on the map.
"""

from pathlib import PurePosixPath
from typing import Any

import ee

from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec


async def process_asset(
    asset_id: str,
    asset_type: str = "TABLE",
    column: str = "ALL",
    value: Any = None,
) -> AoiResult:
    """Process a supported GEE asset into an AoiResult.

    Vector assets are returned as FeatureCollections and can optionally be
    filtered by column/value. Raster assets are returned as EE image objects
    and are rendered directly on the map.

    Args:
        asset_id: GEE asset path (e.g., "users/username/my_asset").
        asset_type: Earth Engine asset type reported by AssetSelectComponent.
        column: Column to filter by, or "ALL" for all features.
        value: Value to filter for in the column.

    Returns:
        AoiResult with the selected EE asset.

    Raises:
        ValueError: If asset_id is empty, filtering is invalid, or the asset
            type is not supported by the AOI asset workflow.
    """
    if not asset_id:
        raise ValueError("No GEE asset selected")

    if asset_type != "TABLE" and column != "ALL":
        raise ValueError("Column filtering is only available for TABLE assets")

    if column != "ALL" and value is None:
        raise ValueError("Please select a value when filtering by column")

    su.init_ee()

    if asset_type == "TABLE":
        ee_object = ee.FeatureCollection(asset_id)
        if column != "ALL" and value is not None:
            ee_object = ee_object.filter(ee.Filter.eq(column, value))
    elif asset_type == "IMAGE":
        ee_object = ee.Image(asset_id)
    elif asset_type == "IMAGE_COLLECTION":
        ee_object = ee.ImageCollection(asset_id)
    else:
        raise ValueError(f"Unsupported asset type for AOI rendering: {asset_type}")

    name = su.normalize_str(PurePosixPath(asset_id).stem)
    if asset_type == "TABLE" and column != "ALL" and value is not None:
        name = f"{name}_{su.normalize_str(str(value))}"

    return AoiResult(
        method="ASSET",
        name=name,
        gdf=None,
        feature_collection=ee_object,
        admin=None,
        gee=True,
        spec=AoiSpec(
            method="ASSET",
            asset_id=asset_id,
            asset_type=asset_type,
            column=column,
            value=value,
        ),
    )
