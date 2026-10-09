"""Task progress in the notification pill: steps, a fraction, and a detail.

A tracked task can report how far it has got in two ways, and this demo runs
one task of each kind so the difference shows in the pill and in its log:

* ``task.step(message)`` records a milestone. The pill shows the latest one
  after the title, and every step lands in the log -- right for a handful of
  named phases, wrong for hundreds of tiles.
* ``task.set_progress(value, detail=None)`` reports a fraction from 0.0 to 1.0.
  It turns the pill's ring determinate and never writes to the log. A
  ``detail`` string adds the current item: the pill then alternates between
  the task title and ``{pct}% {detail}``. ``set_progress(None)`` puts the ring
  back to indeterminate, which a per-item run does between items so the last
  item's 100% does not linger, and a detail with no value explains a wait.

The download run is the case the detail exists for: several layers, each made
of many tiles, where the title says which layer is running and the detail says
how far into it the run is. Nothing is downloaded -- the tiles are timed sleeps.

The UI lives in :func:`ProgressAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_progress_app/app.py --port 8901
```
"""

import asyncio
from pathlib import Path

import solara

from pysepal import mapping as sm
from pysepal.i18n import catalog
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.notifications import NotificationProvider, use_notifications

setup_solara_server(extra_asset_locations=[])

#: Catalogs, but no importable package: ``gallery.py`` puts every demo directory
#: on ``sys.path``, so a second demo shipping ``component/`` would resolve to
#: whichever one imported first. The map app owns that name; this one stays flat.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg

#: The simulated download: layer names, tiles per layer, seconds per tile.
LAYERS = ("forest_cover", "roads", "elevation")
TILES_PER_LAYER = 40
TILE_SECONDS = 0.1

#: How long the download waits for a free slot before its first layer starts.
WAIT_SECONDS = 3.0


async def run_steps(notifications) -> None:
    """A few named phases: ``step()`` only, the pill's long-standing behaviour."""
    with notifications.track(msg("tasks.steps.title"), total_steps=4) as task:
        for key in ("prepare", "compute", "write", "publish"):
            task.step(msg(f"tasks.steps.{key}"))
            await asyncio.sleep(1.5)
        task.complete(msg("tasks.steps.done"))


async def run_fraction(notifications) -> None:
    """A known fraction and nothing else: the ring fills, the text stays put."""
    with notifications.track(msg("tasks.fraction.title")) as task:
        for done in range(1, 21):
            await asyncio.sleep(0.3)
            task.set_progress(done / 20)
        task.complete(msg("tasks.fraction.done"))


async def run_download(notifications) -> None:
    """Many tiles over several layers: title per layer, detail per tile."""
    with notifications.track(msg("tasks.download.title")) as task:
        # A detail with no value: the ring spins and the pill says why it waits.
        task.set_progress(None, detail=msg("tasks.download.waiting"))
        await asyncio.sleep(WAIT_SECONDS)
        task.step(msg("tasks.download.started", layers=len(LAYERS)))

        for index, layer in enumerate(LAYERS, start=1):
            task.update(msg("tasks.download.layer", index=index, total=len(LAYERS), layer=layer))
            # Between items: back to indeterminate, so the previous layer's 100%
            # does not sit on the ring while the next one starts.
            task.set_progress(None)
            last_pct = None
            for tile in range(1, TILES_PER_LAYER + 1):
                await asyncio.sleep(TILE_SECONDS)
                # set_progress pushes the whole task list to the browser, so a
                # many-item source publishes on whole-percent changes only.
                pct = tile * 100 // TILES_PER_LAYER
                if pct == last_pct:
                    continue
                last_pct = pct
                task.set_progress(
                    tile / TILES_PER_LAYER,
                    detail=msg(
                        "tasks.download.tile", layer=layer, tile=tile, total=TILES_PER_LAYER
                    ),
                )
            task.step(msg("tasks.download.layer_done", layer=layer))
        task.complete(msg("tasks.download.done"))


@solara.component
def ProgressAppDemo():
    """The demo UI, shared by the Solara and Voila entrypoints.

    Only mounts the bus and the shell below it: ``NotificationProvider`` creates
    the bus when its element renders, after this body has finished, so the
    ``use_notifications()`` consumer has to be a separate component.
    """
    NotificationProvider()
    _ProgressShell()


@solara.component
def _ProgressShell():
    """Everything the demo shows, one level below the bus it publishes to."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    notifications = use_notifications()

    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(
            zoom=3, center=[0, 0], gee=False, fullscreen=True, theme_state=theme_state
        ),
        [],
    )

    def use_run(run):
        # use_task only awaits a coroutine *function*; a lambda returning a
        # coroutine would run on a thread and drop it unawaited.
        async def start():
            await run(notifications)

        return solara.lab.use_task(
            start, dependencies=None, raise_error=False, prefer_threaded=False
        )

    tasks = {
        "steps": use_run(run_steps),
        "fraction": use_run(run_fraction),
        "download": use_run(run_download),
    }

    def run_button(name: str, icon: str):
        task = tasks[name]
        return solara.Button(
            label=msg(f"buttons.{name}"),
            icon_name=icon,
            on_click=task,
            loading=task.pending,
            disabled=task.pending,
            color="primary",
            small=True,
            block=True,
            classes=["mb-2"],
        )

    return MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-progress-download",
        locales=messages.available_locales(),
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-progress-clock",
            "width": 400,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("section.title"),
                "icon": "mdi-play-circle-outline",
                "content": [
                    run_button("steps", "mdi-format-list-numbered"),
                    run_button("fraction", "mdi-circle-slice-5"),
                    run_button("download", "mdi-cloud-download-outline"),
                ],
                "description": msg("section.description"),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
    )


@solara.component
def Page():
    """Solara entrypoint -- no SEPAL session, no Earth Engine, no credentials."""
    ProgressAppDemo()
