"""Administrative boundary selection processing.

Functions for selecting and processing administrative boundaries using
FAO GAUL 2024 data (both WFS for non-GEE and sat-io asset for GEE).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
import httpx
import pandas as pd
import pygaul

from pysepal.message import ms
from pysepal.scripts import utils as su
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec
from pysepal.solara.components.aoi.constants import FAO_GAUL_LAYERS, FAO_WFS_BASE_URL

# Path to GAUL -> ISO-3 mapping file
GAUL_ISO_MAPPING: Path = Path(__file__).parents[3] / "data" / "gaul_iso.json"

_WFS_GEOMETRY_CACHE: Dict[str, gpd.GeoDataFrame] = {}
_WFS_BOUNDS_CACHE: Dict[str, tuple] = {}


def _build_wfs_params(
    layer: str, level: int, admin_code: str, extra_params: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Build common WFS request parameters."""
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": layer,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326",
        "CQL_FILTER": f"gaul{level}_code={admin_code}",
    }
    if extra_params:
        params.update(extra_params)
    return params


def _fetch_admin_names_from_pygaul(level: int, parent_code: Optional[str] = None) -> pd.DataFrame:
    """Fetch administrative names from pygaul's local parquet file.

    Args:
        level: Administrative level (0, 1, or 2)
        parent_code: Parent admin code for filtering (e.g., "62" for Colombia)

    Returns:
        DataFrame with columns [gaul{level}_name, gaul{level}_code]
    """
    df = pygaul.Names(admin=parent_code if parent_code else None, content_level=level)
    return df.sort_values(by=[df.columns[0]]) if not df.empty else df


async def _fetch_wfs_geometry_async(level: int, admin_code: str) -> gpd.GeoDataFrame:
    """Fetch administrative geometry from FAO WFS asynchronously.

    Uses the appropriate GAUL 2024 WFS layer for each level:
    - Level 0: gaul:gaul_2024_l0 (272 countries)
    - Level 1: gaul:g2024_2023_1
    - Level 2: gaul:g2024_2023_2

    Args:
        level: Administrative level (0, 1, or 2)
        admin_code: The admin code to fetch

    Returns:
        GeoDataFrame with the geometry
    """
    cache_key = f"wfs_{level}_{admin_code}"
    if cache_key in _WFS_GEOMETRY_CACHE:
        return _WFS_GEOMETRY_CACHE[cache_key]

    layer = FAO_GAUL_LAYERS[level]
    params = _build_wfs_params(layer, level, admin_code)

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(FAO_WFS_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    if not data.get("features"):
        raise ValueError(f"No features found for gaul{level}_code={admin_code}")

    gdf = gpd.GeoDataFrame.from_features(data["features"], crs="EPSG:4326")

    _WFS_GEOMETRY_CACHE[cache_key] = gdf
    return gdf


async def fetch_admin_bounds_async(level: int, admin_code: str) -> tuple:
    """Fetch bounding box for an admin boundary from FAO WFS.

    This fetches only the bbox without the full geometry, making it faster
    for zoom operations. The bbox is cached for subsequent calls.

    Args:
        level: Administrative level (0, 1, or 2)
        admin_code: The admin code to fetch bounds for

    Returns:
        Tuple of (minx, miny, maxx, maxy) in EPSG:4326

    Example:
        ```python
        from pysepal.solara.components.aoi import fetch_admin_bounds_async

        bounds = await fetch_admin_bounds_async(level=0, admin_code="62")
        map_.zoom_bounds(bounds)
        ```
    """
    cache_key = f"bounds_{level}_{admin_code}"
    if cache_key in _WFS_BOUNDS_CACHE:
        return _WFS_BOUNDS_CACHE[cache_key]

    layer = FAO_GAUL_LAYERS[level]
    # Request only non-geometry properties to reduce payload
    # The bbox is still included in the response metadata
    params = _build_wfs_params(
        layer, level, admin_code, {"propertyName": f"gaul{level}_code,gaul{level}_name"}
    )

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(FAO_WFS_BASE_URL, params=params)
        response.raise_for_status()
        data = response.json()

    # bbox is at feature level when using propertyName (geometry excluded)
    features = data.get("features", [])
    if not features or "bbox" not in features[0]:
        raise ValueError(f"No bbox found for gaul{level}_code={admin_code}")

    bounds = tuple(features[0]["bbox"])

    _WFS_BOUNDS_CACHE[cache_key] = bounds
    return bounds


def fetch_admin_items(
    level: int,
    parent_code: str = "",
) -> List[Dict[str, str]]:
    """Fetch administrative region items for dropdown selection.

    Retrieves a list of administrative regions at the specified level,
    optionally filtered by a parent region code.

    Uses pygaul's local GAUL 2024 parquet file for instant lookups (~1ms).

    Args:
        level: Administrative level (0, 1, or 2)
        parent_code: Parent admin code to filter results. Empty string for level 0.

    Returns:
        List of dicts with 'text' (display name) and 'value' (admin code) keys.

    Example:
        ```python
        from pysepal.solara.components.aoi import fetch_admin_items

        # Get all countries (instant from local parquet)
        countries = fetch_admin_items(level=0)

        # Get regions within Colombia (code 62 in GAUL 2024)
        regions = fetch_admin_items(level=1, parent_code="62")
        ```
    """
    df = _fetch_admin_names_from_pygaul(level, parent_code or None)

    name_col = df.columns[0]  # gaul{level}_name
    code_col = df.columns[1]  # gaul{level}_code

    item_list = []
    for _, r in df.iterrows():
        text = su.normalize_str(r[name_col], folder=False)
        item_list.append({"text": text, "value": str(r[code_col])})

    return item_list


def _derive_admin_chain(level: int, admin_code: str) -> Tuple[str, ...]:
    """Return every GAUL code from level 0 down to ``admin_code``.

    ``AoiView`` already knows the whole cascade and passes it in. A caller reaching
    ``process_admin`` directly knows only the leaf, and falling back to ``(leaf,)``
    would record a chain that a restore reads as a *level-0* selection — so an
    ADMIN2 spec built outside the picker could never be restored.

    Args:
        level: The admin level of ``admin_code`` (1 or 2; level 0 needs no lookup).
        admin_code: The leaf GAUL 2024 code.

    Returns:
        The codes for levels 0..``level``.

    Raises:
        ValueError: If ``admin_code`` is not a GAUL 2024 code. ``pygaul`` raises this
            itself, which is the validation we want — a bad code must fail loudly.
    """
    row = pygaul.Names(admin=str(admin_code), complete=True).iloc[0]
    return tuple(str(row[f"gaul{lvl}_code"]) for lvl in range(level + 1))


async def process_admin(
    method: str,
    admin_code: str,
    gee: bool = True,
    gee_interface: Optional[Any] = None,
    admin_codes: Sequence[str] = (),
) -> AoiResult:
    """Process administrative boundary selection.

    Configures an administrative boundary selection using either Earth Engine
    (sat-io GAUL 2024 asset) or FAO GAUL 2024 WFS service. The geometry is
    fetched lazily - use `AoiResult.get_gdf_async()` to retrieve it when needed.

    Both modes use the same GAUL 2024 codes from pygaul's local parquet.

    Args:
        method: The admin method ("ADMIN0", "ADMIN1", or "ADMIN2")
        admin_code: The administrative code to fetch (GAUL 2024 code)
        gee: If True, use Earth Engine with sat-io's GAUL 2024 asset.
             If False, use FAO GAUL 2024 WFS service.
        gee_interface: Optional GEEInterface for Earth Engine operations
        admin_codes: Every GAUL code from level 0 down to ``admin_code``. Recorded on
            the result's spec so a restore can seed the whole cascade. When omitted it
            is ``(admin_code,)`` at level 0, and derived from ``pygaul`` otherwise.

    Returns:
        AoiResult with gdf=None (geometry fetched lazily via get_gdf_async())

    Raises:
        ValueError: If admin_code is empty or invalid

    Example:
        ```python
        from pysepal.solara.components.aoi import process_admin

        # Select Colombia (non-GEE, using FAO WFS)
        result = await process_admin("ADMIN0", "62", gee=False)

        # Fetch geometry when needed
        gdf = await result.get_gdf_async()

        # Select Colombia (GEE, using sat-io asset)
        result = await process_admin("ADMIN0", "62", gee=True)
        ```
    """
    if not admin_code:
        raise ValueError(ms.aoi_sel.exception.no_admlyr)

    if method not in ["ADMIN0", "ADMIN1", "ADMIN2"]:
        raise ValueError(f"Invalid admin method: {method}")

    level = int(method[-1])  # Extract level from method name

    # At level 0 the leaf is already the whole chain, so no lookup is needed — and
    # skipping it there keeps callers that pass a non-GAUL-2024 code working exactly
    # as before, since only levels 1-2 pay pygaul's validation.
    codes = tuple(str(code) for code in admin_codes) or (
        (str(admin_code),) if level == 0 else _derive_admin_chain(level, admin_code)
    )

    if gee:
        # Resolve the interface first: it refuses a session-less one in a
        # per-connection runtime, and init_ee() would already have bound the
        # global ee to the container's credentials by the time it raised.
        created_interface = gee_interface is None
        interface = gee_interface or GEEInterface()

        su.init_ee()

        try:
            # Use pygaul.Items to get the feature collection (handles all the EE logic)
            feature_collection = pygaul.Items(admin=admin_code)

            # Get properties for naming (async call)
            feature = feature_collection.first()
            properties = await interface.get_info_async(
                feature.toDictionary(feature.propertyNames())
            )

            # Build name from ISO code and admin names
            # GAUL 2024 uses: iso3_code, gaul0_name, gaul1_name, gaul2_name
            iso = properties.get("iso3_code", "")
            if not iso or iso.startswith("x"):  # 'x' prefix means disputed/unknown
                iso_mapping = json.loads(GAUL_ISO_MAPPING.read_text())
                gaul0_code = str(properties.get("gaul0_code", ""))
                iso = iso_mapping.get(gaul0_code, "UNK")

            # Collect admin names from all levels up to current
            names = [iso]
            for lvl in range(1, level + 1):
                name_col = f"gaul{lvl}_name"
                if name_col in properties and properties.get(name_col):
                    names.append(su.normalize_str(properties[name_col]))

            name = "_".join(names)

            return AoiResult(
                method=method,
                name=name,
                gdf=None,  # Lazy - users can use get_gdf_async() if needed
                feature_collection=feature_collection,
                admin=admin_code,
                gee=True,
                spec=AoiSpec(method=method, admin_codes=codes),
            )
        finally:
            if created_interface:
                interface.close()

    else:

        # Get admin info from pygaul's full parquet (includes iso3_code)
        full_df = pygaul._df()
        code_col = f"gaul{level}_code"
        admin_rows = full_df[full_df[code_col] == str(admin_code)]

        if admin_rows.empty:
            raise ValueError(f"Admin code {admin_code} not found in GAUL 2024")

        # Get first row for name building
        row = admin_rows.iloc[0]

        # Build name from ISO code and admin names
        iso = row.get("iso3_code", "")
        if not iso or (isinstance(iso, str) and iso.startswith("x")):
            # Fall back to mapping file
            iso_mapping = json.loads(GAUL_ISO_MAPPING.read_text())
            gaul0_code = str(row.get("gaul0_code", ""))
            iso = iso_mapping.get(gaul0_code, "UNK")

        # Collect admin names from all levels up to current
        names = [iso]
        for lvl in range(1, level + 1):
            name_col = f"gaul{lvl}_name"
            if name_col in full_df.columns and row.get(name_col):
                names.append(su.normalize_str(row[name_col]))

        name = "_".join(names)

        return AoiResult(
            method=method,
            name=name,
            gdf=None,  # Lazy - users can use AoiResult.get_gdf_async() when needed
            feature_collection=None,
            admin=admin_code,
            gee=False,
            spec=AoiSpec(method=method, admin_codes=codes),
        )
