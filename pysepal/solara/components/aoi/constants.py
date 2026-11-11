"""Constants for FAO GAUL data services.

Centralized configuration for FAO GAUL WMS/WFS service URLs and layer names.
"""

# FAO GAUL WMS Configuration
FAO_WMS_BASE_URL = "https://data.apps.fao.org/map/gsrv/gsrv1/gaul/wms"

# FAO GAUL WFS Configuration
FAO_WFS_BASE_URL = "https://data.apps.fao.org/map/gsrv/gsrv1/gaul/wfs"

# FAO GAUL layers (used by both WMS and WFS)
FAO_GAUL_LAYERS = {
    0: "gaul:gaul_2024_l0",
    1: "gaul:g2024_2023_1",
    2: "gaul:g2024_2023_2",
}

# Boundary dataset behind the admin methods, keyed by ``gee``: FAO's own GAUL 2024
# services without GEE, the sat-io copy of it in the GEE Community Catalog with GEE
# (the asset pygaul reads). Shown as map attribution and stored on AoiResult.
ADMIN_SOURCES = {
    False: {
        "name": "FAO GAUL 2024",
        "url": "https://www.fao.org/hih-geospatial-platform/news/detail/"
        "now-available--the-global-administrative-unit-layers-(gaul)-dataset---2024-edition/en",
    },
    True: {
        "name": "FAO GAUL 2024 (GEE Community Catalog)",
        "url": "https://gee-community-catalog.org/projects/gaul/",
    },
}


def admin_source_attribution(gee: bool) -> str:
    """Return the map attribution link for the admin boundary dataset."""
    source = ADMIN_SOURCES[gee]
    return f'<a href="{source["url"]}" target="_blank">{source["name"]}</a>'


# WMS preview layer name constant
WMS_PREVIEW_LAYER_NAME = "aoi_wms_preview"
