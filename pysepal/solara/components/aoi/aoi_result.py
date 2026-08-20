"""AOI result dataclass.

Common dataclass used across all AOI selection methods.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

import geopandas as gpd
from deprecated.sphinx import versionadded

from pysepal.solara.components.aoi.aoi_spec import AoiSpec


@dataclass(frozen=True)
@versionadded(version="3.1", reason="Pure Solara AOI result dataclass")
class AoiResult:
    """Immutable result from AOI selection.

    This dataclass represents the output of any AOI selection method.
    It is designed to be immutable (frozen) for predictable state management.

    For admin boundaries, geometry (GDF) is NOT fetched automatically to keep
    selections fast. Use `get_gdf_async()` to fetch the geometry when needed.

    Attributes:
        method: Selection method used (e.g., "ADMIN0", "ADMIN1", "ADMIN2", "DRAW")
        name: Human-readable name for the AOI (e.g., "COL_Cundinamarca")
        gdf: GeoDataFrame with the geometry (None for admin methods - use get_gdf_async())
        feature_collection: ee.ComputedObject for GEE workflows (FeatureCollection, Image, etc.; None otherwise)
        admin: Admin code for admin methods (None for other methods)
        gee: Whether this result was created with GEE binding
        spec: The serializable record of the inputs that produced this result.
            Persist ``spec.to_dict()`` and pass the rebuilt spec back to
            ``AoiView(spec=...)`` to restore the selection.

    Example:
        ```python
        from pysepal.solara.components.aoi import process_admin

        result = await process_admin("ADMIN1", "3431", gee=False)
        print(f"Selected: {result.name}")

        # Fetch geometry when needed
        gdf = await result.get_gdf_async()
        ```
    """

    method: str
    name: str
    gdf: Optional[gpd.GeoDataFrame] = field(default=None, repr=False)
    feature_collection: Optional[Any] = field(default=None, repr=False)  # ee.ComputedObject
    admin: Optional[str] = None
    gee: bool = False
    spec: Optional[AoiSpec] = None

    async def get_gdf_async(self) -> Optional[gpd.GeoDataFrame]:
        """Fetch the GeoDataFrame asynchronously.

        For admin boundaries (non-GEE), this fetches the geometry from FAO WFS.
        For GEE results, this returns None (use feature_collection instead).
        For DRAW results, this returns the already-available gdf.

        Returns:
            GeoDataFrame with the geometry, or None for GEE results.
        """
        # If we already have a GDF, return it
        if self.gdf is not None:
            return self.gdf

        # For GEE results, we don't fetch GDF (users should use feature_collection)
        if self.gee:
            return None

        # For admin methods, fetch from WFS
        if self.admin is not None and self.method in ["ADMIN0", "ADMIN1", "ADMIN2"]:
            # Import here to avoid circular dependency (admin.py imports AoiResult)
            from pysepal.solara.components.aoi.admin import _fetch_wfs_geometry_async

            level = int(self.method[-1])
            return await _fetch_wfs_geometry_async(level, self.admin)

        return None
