"""Points/CSV file processing for AOI selection.

Contains the process_points function that converts a CSV/TXT file with
point data into an AoiResult.
"""

import asyncio
from pathlib import Path

import geopandas as gpd
import pandas as pd

from pysepal.scripts import utils as su
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec


async def process_points(
    pathname: str,
    id_column: str,
    lat_column: str,
    lng_column: str,
    gee: bool = True,
) -> AoiResult:
    """Process a CSV/TXT file with point data into an AoiResult.

    Reads a tabular file, creates point geometries from lat/lng columns,
    and returns a GeoDataFrame. If GEE is enabled, also creates an
    ee.FeatureCollection.

    Args:
        pathname: Path to the CSV/TXT file.
        id_column: Column name for point IDs.
        lat_column: Column name for latitude values.
        lng_column: Column name for longitude values.
        gee: If True, create Earth Engine FeatureCollection.

    Returns:
        AoiResult with point geometries.

    Raises:
        ValueError: If inputs are invalid or columns don't exist.
    """
    if not pathname:
        raise ValueError("No file selected")

    if not all([id_column, lat_column, lng_column]):
        raise ValueError("All columns (ID, Latitude, Longitude) must be selected")

    cols = [id_column, lat_column, lng_column]
    if len(cols) != len(set(cols)):
        raise ValueError("Duplicate column selected — each column must be different")

    df = await asyncio.to_thread(pd.read_csv, pathname, sep=None, engine="python")

    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Columns not found in file: {', '.join(missing)}")

    gdf = gpd.GeoDataFrame(
        df,
        crs="EPSG:4326",
        geometry=gpd.points_from_xy(df[lng_column], df[lat_column]),
    )

    name = su.normalize_str(Path(pathname).stem)

    feature_collection = None
    if gee:
        su.init_ee()
        feature_collection = await asyncio.to_thread(su.geojson_to_ee, gdf.__geo_interface__)

    return AoiResult(
        method="POINTS",
        name=name,
        gdf=gdf,
        feature_collection=feature_collection,
        admin=None,
        gee=gee,
        spec=AoiSpec(
            method="POINTS",
            pathname=pathname,
            id_column=id_column,
            lat_column=lat_column,
            lng_column=lng_column,
        ),
    )
