"""Shape/vector file processing for AOI selection.

Contains the process_shape function that converts a local vector file
into an AoiResult.
"""

import asyncio
from pathlib import Path
from typing import Any

import geopandas as gpd
from shapely import force_2d

from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec


async def process_shape(
    pathname: str,
    column: str = "ALL",
    value: Any = None,
    gee: bool = True,
) -> AoiResult:
    """Process a vector file into an AoiResult.

    Reads a local vector file, optionally filters by column/value,
    and creates a GeoDataFrame. If GEE is enabled, also creates an
    ee.FeatureCollection.

    Args:
        pathname: Path to the vector file.
        column: Column to filter by, or "ALL" for all features.
        value: Value to filter for in the column.
        gee: If True, create Earth Engine FeatureCollection.

    Returns:
        AoiResult with the vector geometry.

    Raises:
        ValueError: If pathname is empty or file can't be read.
    """
    if not pathname:
        raise ValueError("No vector file selected")

    if column != "ALL" and value is None:
        raise ValueError("Please select a value when filtering by column")

    gdf = await asyncio.to_thread(gpd.read_file, pathname)
    gdf = gdf.to_crs(epsg=4326)

    # Earth Engine rejects GeoJSON with Z coordinates (common in KML).
    if gdf.geometry.has_z.any():
        gdf["geometry"] = gdf.geometry.apply(force_2d)

    if column != "ALL" and value is not None:
        gdf = gdf[gdf[column] == value]
        if gdf.empty:
            raise ValueError(f"No features found where {column} = {value}")

    name = su.normalize_str(Path(pathname).stem)
    if column != "ALL" and value is not None:
        name = f"{name}_{su.normalize_str(str(value))}"

    feature_collection = None
    if gee:
        su.init_ee()
        feature_collection = await asyncio.to_thread(su.geojson_to_ee, gdf.__geo_interface__)

    return AoiResult(
        method="SHAPE",
        name=name,
        gdf=gdf,
        feature_collection=feature_collection,
        admin=None,
        gee=gee,
        spec=AoiSpec(method="SHAPE", pathname=pathname, column=column, value=value),
    )
