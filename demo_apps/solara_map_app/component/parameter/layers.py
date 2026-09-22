"""Layer identifiers, visualisation parameters and class breaks.

Layer ids are the keys the map, the legend selector and the stale-output cleanup
all agree on, so they are declared once here.
"""

NDVI_LAYER_ID = "demo_ndvi"
RADAR_LAYER_ID = "demo_radar"
PIXEL_AREA_LAYER_ID = "demo_pixel_area"
ELEVATION_CLASS_LAYER_ID = "demo_elevation_class"
PMTILES_LAYER_ID = "demo_pmtiles"
AOI_LAYER_IDS = (PIXEL_AREA_LAYER_ID, ELEVATION_CLASS_LAYER_ID)

DEMO_CENTER = [4.75, -74.12]
NDVI_VIS = {"min": -0.2, "max": 0.9, "palette": ["#d7191c", "#ffffbf", "#1a9641"]}
PIXEL_AREA_VIS = {"min": 0, "max": 5000, "palette": ["#fff7bc", "#d95f0e"]}

# Sentinel-1 false colour over the Rio Negro / Solimões confluence at Manaus:
# open water scatters nothing back and reads black, forest and the city read
# bright, so the composite needs no AOI to be legible.
RADAR_CENTER = [-3.12, -59.98]
RADAR_VIS = {"bands": ["VV", "VH", "ratio"], "min": [-18, -26, 2], "max": [0, -10, 14]}
# (catalogue key, chip color) per composite channel, in RGB order, for the legend.
RADAR_BANDS = (
    ("radar.vv", "#d62828"),
    ("radar.vh", "#2e9e44"),
    ("radar.ratio", "#1e5bd6"),
)

# (pixel value, catalogue key, color) -- drives the EE reclassification, the map
# palette and the legend chips from a single source. The middle field is a key,
# not a label: this tuple is built at import, so a label frozen here would stay
# in the language the module was imported in. The legend renders it with msg().
ELEVATION_CLASSES = (
    (1, "elevation.lowland", "#c7e9b4"),
    (2, "elevation.upland", "#41b6c4"),
    (3, "elevation.highland", "#253494"),
)

# Vector tiles read straight from a public archive: the browser range-requests the
# PMTiles itself, so nothing is proxied through the kernel. ``source-layer`` must
# match a layer id inside the archive ("buildings" here) or nothing is painted.
PMTILES_URL = "https://r2-public.protomaps.com/protomaps-sample-datasets/nz-buildings-v3.pmtiles"
PMTILES_CENTER = [-43.5565, 172.6062]
PMTILES_STYLE = {
    "version": 8,
    "sources": {"nz_buildings": {"type": "vector", "url": f"pmtiles://{PMTILES_URL}"}},
    "layers": [
        {
            "id": "buildings-fill",
            "type": "fill",
            "source": "nz_buildings",
            "source-layer": "buildings",
            "paint": {"fill-color": "#41b6c4", "fill-opacity": 0.6},
        },
        {
            "id": "buildings-outline",
            "type": "line",
            "source": "nz_buildings",
            "source-layer": "buildings",
            "paint": {"line-color": "#253494", "line-width": 0.5},
        },
    ],
}
