"""Local raster rendering: continuous ramps, categorical class colors, big files.

Three buttons, one per path through :meth:`~pysepal.mapping.SepalMap.add_raster`:
a continuous colormap, exact per-class colors, and a raster large enough that
preparing it has to happen off the event loop.

Set ``PYSEPAL_DEMO_RASTER_DIR`` to a directory holding ``aa_test_congo.tif`` and
``hansen_bolivia.tif`` to run against real class maps; without it the demo
generates a small synthetic class raster so it still runs anywhere.

The UI lives in :func:`RasterAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_raster_app/app.py --port 8901
```
"""

import os
from pathlib import Path

import solara

import pysepal.sepalwidgets as sw
from pysepal import mapping as sm
from pysepal.i18n import catalog
from pysepal.scripts.scratch import scratch_root
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button
from pysepal.solara.notifications import NotificationProvider, use_notifications

setup_solara_server(extra_asset_locations=[])

#: Points the demo at real class maps instead of the generated stand-in.
RASTER_DIR_ENV_VAR = "PYSEPAL_DEMO_RASTER_DIR"

#: Catalogs, but no importable package: ``gallery.py`` puts every demo directory
#: on ``sys.path``, so a second demo shipping ``component/`` would resolve to
#: whichever one imported first. The map app owns that name; this one stays flat.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg


# aa_test_congo holds these nine classes; codes 2 and 4 are the ones a continuous
# ramp stretched over 2-34 renders as good as black.
CONGO_COLORS = {
    2: "#8ecae6",
    4: "#219ebc",
    11: "#2d6a4f",
    12: "#40916c",
    13: "#95d5b2",
    31: "#e9c46a",
    32: "#f4a261",
    33: "#e76f51",
    34: "#9b2226",
}

# hansen loss year band: 0 is "no loss" and a real, sampleable class, not background
HANSEN_COLORS = {0: "#1b4332", 5: "#e63946"}


def _synthetic_raster(path: Path, codes: dict) -> Path:
    """Write a small class raster, so the demo runs without the real products."""
    import numpy as np
    import rasterio as rio
    from rasterio.transform import from_origin

    if path.exists():
        return path

    values = sorted(codes)
    size = 512
    data = np.zeros((size, size), dtype="int16")
    for band, value in enumerate(values):
        data[:, band * size // len(values) : (band + 1) * size // len(values)] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    with rio.open(
        path,
        "w",
        driver="GTiff",
        height=size,
        width=size,
        count=1,
        dtype="int16",
        crs="EPSG:4326",
        transform=from_origin(20, 0, 0.01, 0.01),
    ) as dataset:
        dataset.write(data, 1)

    return path


def demo_rasters() -> dict:
    """Return the two rasters to draw, generating stand-ins when absent."""
    directory = os.environ.get(RASTER_DIR_ENV_VAR)
    if directory:
        congo = Path(directory) / "aa_test_congo.tif"
        hansen = Path(directory) / "hansen_bolivia.tif"
        if congo.is_file() and hansen.is_file():
            return {"congo": congo, "hansen": hansen, "synthetic": False}

    scratch = scratch_root() / "pysepal-raster-demo"
    return {
        "congo": _synthetic_raster(scratch / "classes.tif", CONGO_COLORS),
        "hansen": _synthetic_raster(scratch / "loss.tif", HANSEN_COLORS),
        "synthetic": True,
    }


@solara.component
def RasterAppDemo():
    """Mount the notification bus, then the app that publishes to it.

    ``use_notifications()`` resolves to a NoopNotifier while no provider is
    mounted, and the tasks close over whatever it returned -- so the hook has to
    run in a child of the provider, not alongside it.
    """
    # Toasts top-right, task progress pill bottom-right.
    NotificationProvider()
    RasterPanel()


@solara.component
def RasterPanel():
    """Map plus a panel of buttons, one per raster-rendering path."""
    setup_theme_colors()
    # Theme is scope-keyed UI state, so this reads nothing from the session --
    # which is what lets the demo run undecorated, and run inside the gallery
    # where the map app's session manager is active process-wide.
    theme_state = get_current_theme_state()
    notifications = use_notifications()

    rasters = solara.use_memo(demo_rasters, [])

    def build_map():
        return sm.SepalMap(
            zoom=3, center=[0, 0], gee=False, fullscreen=True, theme_state=theme_state
        )

    sepal_map = solara.use_memo(build_map, [])

    async def add_continuous():
        """What every raster looked like before class_colors: a stretched ramp."""
        with notifications.track(msg("tasks.continuous")) as task:
            task.step(msg("tasks.preparing"))
            await sepal_map.add_raster_async(
                rasters["congo"],
                layer_name=msg("layers.continuous"),
                key="continuous",
                colormap="inferno",
            )
        notifications.success(msg("toasts.continuous"))

    async def add_class_colors():
        """The same raster, each class in its own color."""
        with notifications.track(msg("tasks.classes")) as task:
            task.step(msg("tasks.preparing"))
            await sepal_map.add_raster_async(
                rasters["congo"],
                layer_name=msg("layers.exact"),
                key="classes",
                class_colors=CONGO_COLORS,
            )
        notifications.success(msg("toasts.classes", count=len(CONGO_COLORS)))

    async def add_large():
        """A raster with no overviews, which is the case ``optimize`` exists for."""
        with notifications.track(msg("tasks.large")) as task:
            task.step(msg("tasks.preparing_overviews"))
            await sepal_map.add_raster_async(
                rasters["hansen"],
                layer_name=msg("layers.loss"),
                key="large",
                class_colors=HANSEN_COLORS,
            )
        notifications.success(msg("toasts.large"))

    continuous_task = solara.lab.use_task(
        add_continuous, dependencies=None, raise_error=False, prefer_threaded=False
    )
    classes_task = solara.lab.use_task(
        add_class_colors, dependencies=None, raise_error=False, prefer_threaded=False
    )
    large_task = solara.lab.use_task(
        add_large, dependencies=None, raise_error=False, prefer_threaded=False
    )

    continuous_props = use_task_button(continuous_task, on_start=continuous_task)
    classes_props = use_task_button(classes_task, on_start=classes_task)
    large_props = use_task_button(large_task, on_start=large_task)

    def build_clear_button():
        """A plain ipyvuetify button, handed to MapApp intact with its handler."""
        button = sw.Btn(msg("buttons.clear_rasters"), small=True, block=True)

        def clear():
            for key in ("continuous", "classes", "large"):
                sepal_map.remove_layer(key, none_ok=True)

        button.on_event("click", lambda *args: clear())
        return button

    # Rebuilt on a language change too: it is a widget, not an element, so its
    # label is set at construction and nothing re-renders it.
    clear_button = solara.use_memo(
        build_clear_button, [id(sepal_map), msg("buttons.clear_rasters")]
    )

    source = msg("source.synthetic") if rasters["synthetic"] else msg("source.real")

    MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-layers",
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-image",
            "width": 380,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("section.title"),
                "icon": "mdi-image",
                "content": [
                    TaskButtonComponent(
                        label=msg("buttons.continuous"), **continuous_props, small=True, block=True
                    ),
                    TaskButtonComponent(
                        label=msg("buttons.classes"), **classes_props, small=True, block=True
                    ),
                    TaskButtonComponent(
                        label=msg("buttons.large"), **large_props, small=True, block=True
                    ),
                    clear_button,
                ],
                "description": msg(
                    "section.description", source=source, env_var=RASTER_DIR_ENV_VAR
                ),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
        locales=messages.available_locales(),
        dialog_width=750,
    )


@solara.component
def Page():
    """Solara entrypoint -- no SEPAL session, the raster path is entirely local."""
    RasterAppDemo()
