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

The same download also runs off the kernel's event loop: through
``asyncio.to_thread``, through a one-worker ``ThreadPoolExecutor`` that every
connection shares (start it in two browser tabs at once: each pill shows only
its own run).

The UI lives in :func:`ProgressAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_progress_app/app.py --port 8901
```
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
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

#: One worker for every connection, so two tabs' downloads share one thread.
SHARED_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="progress-demo")


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


def layer_texts() -> list[dict]:
    """Translate every message a layer needs, on the kernel's side.

    ``msg()`` reads the connection's locale from its kernel, and a worker thread
    has none, so a worker gets these strings ready-made. ``tile`` keeps a
    ``{tile}`` placeholder for the worker to fill.
    """
    return [
        {
            "name": layer,
            "title": msg("tasks.download.layer", index=index, total=len(LAYERS), layer=layer),
            "tile": msg("tasks.download.tile", layer=layer, tile="{tile}", total=TILES_PER_LAYER),
            "done": msg("tasks.download.layer_done", layer=layer),
        }
        for index, layer in enumerate(LAYERS, start=1)
    ]


def report_tile(task, layer: dict, tile: int, last_pct) -> int:
    """Publish one tile's progress on whole-percent changes only; return the percent.

    set_progress pushes the whole task list to the browser, so a many-item
    source skips the calls that would not change what the pill shows.
    """
    pct = tile * 100 // TILES_PER_LAYER
    if pct != last_pct:
        task.set_progress(tile / TILES_PER_LAYER, detail=layer["tile"].format(tile=tile))
    return pct


async def run_download(notifications) -> None:
    """Many tiles over several layers, on the kernel's event loop."""
    with notifications.track(msg("tasks.download.title")) as task:
        # A detail with no value: the ring spins and the pill says why it waits.
        task.set_progress(None, detail=msg("tasks.download.waiting"))
        await asyncio.sleep(WAIT_SECONDS)
        task.step(msg("tasks.download.started", layers=len(LAYERS)))

        for layer in layer_texts():
            task.update(layer["title"])
            # Between items: back to indeterminate, so the previous layer's 100%
            # does not sit on the ring while the next one starts.
            task.set_progress(None)
            last_pct = None
            for tile in range(1, TILES_PER_LAYER + 1):
                await asyncio.sleep(TILE_SECONDS)
                last_pct = report_tile(task, layer, tile, last_pct)
            task.step(layer["done"])
        task.complete(msg("tasks.download.done"))


def download_blocking(task, layers: list[dict]) -> None:
    """The same download as blocking code, for a worker thread."""
    for layer in layers:
        task.update(layer["title"])
        task.set_progress(None)
        last_pct = None
        for tile in range(1, TILES_PER_LAYER + 1):
            time.sleep(TILE_SECONDS)
            last_pct = report_tile(task, layer, tile, last_pct)
        task.step(layer["done"])


async def run_to_thread(notifications) -> None:
    """The tracker opens here, on the kernel's side, and the worker reports through it."""
    with notifications.track(msg("tasks.download.title")) as task:
        await asyncio.to_thread(download_blocking, task, layer_texts())
        task.complete(msg("tasks.download.done"))


async def run_pool(notifications) -> None:
    """Through the pool every connection shares: two tabs, one thread, two pills."""
    with notifications.track(msg("tasks.download.title")) as task:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(SHARED_POOL, download_blocking, task, layer_texts())
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
        "to_thread": use_run(run_to_thread),
        "pool": use_run(run_pool),
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
                    run_button("to_thread", "mdi-swap-horizontal"),
                    run_button("pool", "mdi-account-multiple-outline"),
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
