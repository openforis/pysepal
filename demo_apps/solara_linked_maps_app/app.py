"""Three maps side by side, two of them linked: move one and the other follows.

Maps 1 and 2 share the link group ``demo``, so a pan, a zoom or a camera call on
either moves both; map 3 starts outside the group. Each map's switch moves it in
or out of the group while the page runs. Map 2 opens elsewhere and jumps to map 1
as soon as it joins, and the buttons move a map from Python to show that a camera
call travels through the group too.

Everything is generated, so the demo needs no session, no credentials and no
network beyond the basemap.

The UI lives in :func:`LinkedMapsDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_linked_maps_app/app.py --port 8901
```
"""

from pathlib import Path

import numpy as np
import rasterio as rio
import solara
from rasterio.transform import from_bounds

from pysepal.i18n import catalog
from pysepal.mapping import SepalMap
from pysepal.scripts.scratch import scratch_root
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.components.map_view import MapView

setup_solara_server(extra_asset_locations=[])

#: Catalogs, but no importable package: ``gallery.py`` puts every demo directory on
#: ``sys.path``, so the demos stay flat.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg

GROUP = "demo"

#: The area the rasters cover, (west, south, east, north), and their size in pixels.
BOUNDS = (-76.4, 5.6, -73.0, 9.4)
SIZE = 96
CLEARINGS = [(30, 28, 9), (62, 40, 12), (44, 70, 10), (75, 74, 7), (18, 58, 6)]

#: Each map: its raster's year, whether the clearings are cut, its camera, its group.
MAPS = (
    ("2020", False, (-74.7, 7.5), 6.0, GROUP),
    ("2024", True, (-60.0, 0.0), 3.0, GROUP),
    ("2024", True, (-74.7, 7.5), 8.0, None),
)
HEIGHT = "620px"


def raster_path(year: str, cleared: bool) -> Path:
    """Write the raster of one date once, and return its path."""
    path = scratch_root() / "pysepal-linked-maps-demo" / f"forest_{year}.tif"
    if path.exists():
        return path
    rng = np.random.default_rng(4)
    cols, rows = np.meshgrid(np.arange(SIZE), np.arange(SIZE))
    data = 170 + 50 * np.sin(cols / 9.0) * np.cos(rows / 11.0) + rng.normal(0, 12, (SIZE, SIZE))
    if cleared:
        for col, row, radius in CLEARINGS:
            data[(cols - col) ** 2 + (rows - row) ** 2 <= radius**2] = 25
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
        dataset.write(np.clip(data, 0, 255).astype("uint8"), 1)
    return path


def build_maps(theme_state) -> list[SepalMap]:
    """One map per entry of ``MAPS``, each drawing its date's raster."""
    maps = []
    for number, (year, cleared, center, zoom, group) in enumerate(MAPS, start=1):
        m = SepalMap(
            gee=False,
            theme_state=theme_state,
            center=center,
            zoom=zoom,
            fullscreen=False,
            height=HEIGHT,
            link_group=group,
        )
        m.add_raster(
            raster_path(year, cleared),
            layer_name=msg("layers.forest", number=number, year=year),
            key="forest",
            colormap="viridis",
            vmin=0,
            vmax=255,
        )
        maps.append(m)
    return maps


@solara.component
def GroupSwitch(m: SepalMap, number: int):
    """Move one map in or out of the group."""
    on, set_on = solara.use_state(m.link_group is not None)

    def toggle(value: bool):
        m.link_group = GROUP if value else None
        set_on(value)

    solara.Switch(label=msg("switch", number=number, group=GROUP), value=on, on_value=toggle)


@solara.component
def LinkedMapsDemo():
    """The three maps, each with its switch, under the buttons that move them from Python."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    maps = solara.use_memo(lambda: build_maps(theme_state), [])

    with solara.Column(style={"width": "100%", "padding": "6px"}):
        with solara.Row(style={"gap": "12px", "align-items": "center"}):
            solara.Button(msg("buttons.fit"), on_click=lambda: maps[0].zoom_raster("forest"))
            solara.Button(msg("buttons.center"), on_click=lambda: maps[1].set_center(0, 0, 3))
        with solara.Row(style={"width": "100%", "gap": "6px"}):
            for number, m in enumerate(maps, start=1):
                with solara.Column(style={"flex": "1", "min-width": "0"}):
                    GroupSwitch(m, number)
                    with solara.Div(style={"height": HEIGHT}):
                        MapView(m)


@solara.component
def Page():
    """Solara entrypoint -- no SEPAL session, everything is generated."""
    LinkedMapsDemo()
