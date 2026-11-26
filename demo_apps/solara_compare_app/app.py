"""Compare two dates with the swipe, draw on the map, and pick an area of interest.

One map in compare mode: a 2020 raster on the left side, a 2024 one with five
clearings on the right, and the vector layers on both. The layer panel moves a
layer between the sides, the switch turns compare off and on, and the drawing
buttons start and end a drawing session whose shapes reach Python. Alerts are
pins coloured by status, field plots are clusters coloured by class, and each
side shows the legend of its own layers.

Everything is generated, so the demo needs no session, no credentials and no
network beyond the basemap.

The UI lives in :func:`CompareAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_compare_app/app.py --port 8901
```
"""

from pathlib import Path

import numpy as np
import rasterio as rio
import solara
from rasterio.transform import from_bounds

from pysepal.i18n import catalog
from pysepal.layers import LayerSpec, VectorStyle
from pysepal.mapping import SepalMap
from pysepal.scripts.scratch import scratch_root
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.components.aoi import AoiView
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.map_app import MapApp

setup_solara_server(extra_asset_locations=[])

#: Catalogs, but no importable package: ``gallery.py`` puts every demo directory on
#: ``sys.path``, so the demos stay flat.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg

#: The area the rasters cover, (west, south, east, north), and their size in pixels.
BOUNDS = (-76.4, 5.6, -73.0, 9.4)
SIZE = 96

#: Clearings that appear between the two dates, in raster pixels: (column, row, radius).
CLEARINGS = [(30, 28, 9), (62, 40, 12), (44, 70, 10), (75, 74, 7), (18, 58, 6)]
STATUSES = ["confirmed", "pending", "rejected", "confirmed", "pending"]
DRAW_MODES = ("polygon", "rectangle", "circle", "linestring", "point")


def forest(cleared: bool) -> np.ndarray:
    """A forest-like texture, with the clearings cut out when ``cleared``."""
    rng = np.random.default_rng(4 + cleared)
    cols, rows = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    base = 170 + 50 * np.sin(cols / 9.0) * np.cos(rows / 11.0) + rng.normal(0, 12, (SIZE, SIZE))
    if cleared:
        for col, row, radius in CLEARINGS:
            base[(cols - col) ** 2 + (rows - row) ** 2 <= radius**2] = 25
    return np.clip(base, 0, 255).astype("uint8")


def raster_path(year: str, cleared: bool) -> Path:
    """Write the raster of one date once, and return its path."""
    path = scratch_root() / "pysepal-compare-demo" / f"forest_{year}.tif"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with rio.open(
        path,
        "w",
        driver="GTiff",
        width=SIZE,
        height=SIZE,
        count=1,
        dtype="uint8",
        crs="EPSG:4326",
        transform=from_bounds(*BOUNDS, SIZE, SIZE),
    ) as dataset:
        dataset.write(forest(cleared), 1)
    return path


def lnglat(col: float, row: float) -> list[float]:
    """The (lng, lat) of a raster pixel."""
    west, south, east, north = BOUNDS
    return [west + (east - west) * col / SIZE, north - (north - south) * row / SIZE]


def feature_collection(features: list) -> dict:
    """Wrap features in a FeatureCollection."""
    return {"type": "FeatureCollection", "features": features}


def build_map(theme_state) -> SepalMap:
    """The map with both dates, the alerts, the field plots and the concession."""
    m = SepalMap(
        inspector=True,
        coordinates=True,
        gee=False,
        theme_state=theme_state,
        center=(-74.7, 7.5),
        zoom=7.4,
        fullscreen=False,
    )
    for year, cleared, side in (("2020", False, "left"), ("2024", True, "right")):
        m.add_raster(
            raster_path(year, cleared),
            layer_name=msg(f"layers.forest_{year}"),
            key=f"forest_{year}",
            colormap="viridis",
            vmin=0,
            vmax=255,
            side=side,
        )

    alerts = [
        {
            "type": "Feature",
            "properties": {
                "name": f"#{i + 1}",
                "status": STATUSES[i],
                "year": 2024,
                "radius": radius,
            },
            "geometry": {"type": "Point", "coordinates": lnglat(col, row)},
        }
        for i, (col, row, radius) in enumerate(CLEARINGS)
    ]
    m.layer_store.add(
        LayerSpec.from_points(
            feature_collection(alerts),
            name=msg("layers.alerts"),
            id="alerts",
            style=VectorStyle(
                marker="pin",
                color_by="status",
                class_colors={"confirmed": "#d62828", "pending": "#f77f00", "rejected": "#6c757d"},
                class_labels={s: msg(f"alerts.{s}") for s in ("confirmed", "pending", "rejected")},
                popup={
                    "name": msg("alerts.name"),
                    "status": msg("alerts.status"),
                    "year": msg("alerts.year"),
                    "radius": msg("alerts.radius"),
                },
                tooltip={"name": msg("alerts.name")},
            ),
        ),
        side="right",
    )

    rng = np.random.default_rng(7)
    west, south, east, north = BOUNDS
    plots = [
        {
            "type": "Feature",
            "properties": {"plot": f"P-{i:03d}", "kind": int(rng.integers(1, 4))},
            "geometry": {
                "type": "Point",
                "coordinates": [float(rng.uniform(west, east)), float(rng.uniform(south, north))],
            },
        }
        for i in range(150)
    ]
    m.layer_store.add(
        LayerSpec.from_points(
            feature_collection(plots),
            name=msg("layers.plots"),
            id="plots",
            style=VectorStyle(
                cluster=True,
                color_by="kind",
                class_colors={1: "#2a9d8f", 2: "#e9c46a", 3: "#264653"},
                class_labels={1: msg("plots.forest"), 2: msg("plots.shrub"), 3: msg("plots.bare")},
                popup={"plot": msg("plots.plot"), "kind": msg("plots.class")},
            ),
        )
    )

    w, s, e, n = -75.4, 6.5, -74.1, 8.4
    concession = {
        "type": "Feature",
        "properties": {"name": msg("layers.concession")},
        "geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]},
    }
    m.layer_store.add(
        LayerSpec.from_geojson(
            feature_collection([concession]),
            name=msg("layers.concession"),
            id="concession",
            style=VectorStyle(stroke="#ff9f1c", fill="#ff9f1c", fill_opacity=0.08),
        )
    )
    m.compare = True
    return m


@solara.component
def CompareControls(m: SepalMap):
    """The compare switch, and the buttons that start and end a drawing session."""
    on, set_on = solara.use_state(m.compare)
    session = solara.use_ref(None)
    drawn, set_drawn = solara.use_state(0)

    def toggle(value: bool):
        m.compare = value
        set_on(value)

    def begin():
        session.current = m.draw.begin(
            DRAW_MODES, on_change=lambda shapes: set_drawn(len(shapes["features"]))
        )
        set_drawn(0)

    def end():
        if session.current is not None:
            session.current.end()
            session.current = None
        set_drawn(0)

    solara.Switch(label=msg("compare.switch"), value=on, on_value=toggle)
    with solara.Row():
        solara.Button(msg("draw.start"), on_click=begin, outlined=True)
        solara.Button(msg("draw.end"), on_click=end, text=True)
    solara.Text(msg("draw.count", count=drawn))


@solara.component
def CompareAppDemo():
    """The compare map in a MapApp, with the layers and the AOI in its right panel."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    m = solara.use_memo(lambda: build_map(theme_state), [])
    aoi = solara.use_reactive(None)
    MapApp(
        app_title=msg("app.title"),
        app_icon="mdi-compare-horizontal",
        main_map=[m],
        steps_data=[],
        right_panel_open=True,
        is_pinned=False,
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-layers",
            "width": 380,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("tabs.layers"),
                "icon": "mdi-layers",
                "content": [CompareControls(m), LayerPanel(m.layer_store, map_=m)],
            },
            {
                "title": msg("tabs.aoi"),
                "icon": "mdi-map",
                "content": [AoiView(value=aoi, map_=m, gee=False)],
            },
        ],
    )


@solara.component
def Page():
    """Solara entrypoint -- no SEPAL session, everything is generated."""
    CompareAppDemo()
