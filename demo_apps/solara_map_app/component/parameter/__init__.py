"""Constants and configuration for the Solara map application.

Everything the demo hardcodes -- layer ids, visualisation parameters, class
breaks, sample data paths -- lives here so the UI and the processing code read
the same values.
"""

from .directory import DUMMY_DATA_DIR
from .layers import (
    AOI_LAYER_IDS,
    DEMO_CENTER,
    ELEVATION_CLASS_LAYER_ID,
    ELEVATION_CLASSES,
    NDVI_LAYER_ID,
    NDVI_VIS,
    PIXEL_AREA_LAYER_ID,
    PIXEL_AREA_VIS,
    PMTILES_CENTER,
    PMTILES_LAYER_ID,
    PMTILES_STYLE,
    PMTILES_URL,
    RADAR_BANDS,
    RADAR_CENTER,
    RADAR_LAYER_ID,
    RADAR_VIS,
)

__all__ = [
    "AOI_LAYER_IDS",
    "DEMO_CENTER",
    "DUMMY_DATA_DIR",
    "ELEVATION_CLASSES",
    "ELEVATION_CLASS_LAYER_ID",
    "NDVI_LAYER_ID",
    "NDVI_VIS",
    "PIXEL_AREA_LAYER_ID",
    "PIXEL_AREA_VIS",
    "PMTILES_CENTER",
    "PMTILES_LAYER_ID",
    "PMTILES_STYLE",
    "PMTILES_URL",
    "RADAR_BANDS",
    "RADAR_CENTER",
    "RADAR_LAYER_ID",
    "RADAR_VIS",
]
