"""Paths used by the application.

A real module keeps user files in the SEPAL workspace through ``SepalClient``;
these local paths seed the AOI file picker with the samples shipped beside the
demos, so SHAPE and POINTS have something to open out of the box, and give the
map two layers to open with that need no Earth Engine.
"""

from pathlib import Path

DUMMY_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
SAMPLE_RASTER = DUMMY_DATA_DIR / "demo_raster.tif"
SAMPLE_VECTOR = DUMMY_DATA_DIR / "demo_aoi.gpkg"
