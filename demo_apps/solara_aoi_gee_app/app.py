"""Saving an AOI and getting it back, with Earth Engine on.

``solara_aoi_app`` is the same demo with ``gee=False``. Read that one first: it
explains the two channels of :class:`AoiView` -- ``value`` carries the computed
:class:`AoiResult`, ``spec`` carries the small JSON :class:`AoiSpec` -- and the
save/restore loop here is identical to it, line for line.

What this one adds is the half the local demo cannot reach:

* **ASSET.** The method only exists with Earth Engine, so only here does the
  round-trip cover ``asset_id`` and ``asset_type``. Pick a GEE table, save,
  clear, restore: the spec rebuilds the ``ee.FeatureCollection``, not just the
  form.
* **DRAW against the session.** ``process_draw`` converts the drawn GeoJSON
  with ``geojson_to_ee``. The interface this app authenticated is threaded into
  that call, so the geometry is built for the user whose connection asked --
  not on whatever credentials the container happens to hold.

SHAPE and POINTS are excluded. They read server-local paths, so the ``pathname``
a spec persists means nothing to the next user of a shared container -- see
``docs/guides/solara-gee-patterns.md``, "AOI Method Restrictions". That is the
other thing worth seeing here: which methods survive being written down.

The saved file lives in the scratch directory under its own name, so the two AOI
demos never read each other's. Delete it to start over.

The UI lives in :func:`AoiGeeAppDemo` so the same code serves both runtimes --
``Page`` adds the SEPAL session for Solara and ``ui.ipynb`` is a thin Voila one.

To run (needs SEPAL credentials in a ``.env`` at the repo root):

```bash
pysepal$ ./run_solara.sh demo_apps/solara_aoi_gee_app/app.py --port 8901
```
"""

import json
from pathlib import Path
from typing import Optional

import reacton.ipyvuetify as rv
import solara

from pysepal import mapping as sm
from pysepal.i18n import catalog
from pysepal.scripts.scratch import scratch_root
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.components.aoi import AoiSpec, AoiView
from pysepal.solara.notifications import NotificationProvider, use_notifications

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    """Set up sessions management."""
    return setup_sessions()


#: Catalogs, but no importable package: ``gallery.py`` puts every demo directory
#: on ``sys.path``, so a second demo shipping ``component/`` would resolve to
#: whichever one imported first. The map app owns that name; this one stays flat.
MESSAGE_DIR = Path(__file__).parent / "message"
messages = catalog(MESSAGE_DIR)
msg = messages.msg

#: Its own name, so this demo and the local one never restore each other's AOI.
SAVED_AOI = scratch_root() / "demo_aoi_gee_spec.json"

#: Everything a spec can carry across users. The file methods persist a
#: server-local pathname, which the next connection cannot resolve.
METHODS = ["-SHAPE", "-POINTS"]


def save_spec(spec: AoiSpec) -> None:
    """Write a selection to disk.

    Args:
        spec: The selection to persist.
    """
    SAVED_AOI.parent.mkdir(parents=True, exist_ok=True)
    SAVED_AOI.write_text(json.dumps(spec.to_dict(), indent=2))


def load_spec() -> Optional[AoiSpec]:
    """Return the persisted selection, or None when there is nothing usable.

    A payload written by a newer pysepal, or one corrupted by hand, is treated as
    absent: a demo that refuses to start because of a stale file is worse than one
    that opens empty.

    Returns:
        The restored spec, or None.
    """
    if not SAVED_AOI.exists():
        return None
    try:
        return AoiSpec.from_dict(json.loads(SAVED_AOI.read_text()))
    except (ValueError, OSError, json.JSONDecodeError):
        return None


@solara.component
def AoiGeeAppDemo():
    """The demo UI, shared by the Solara and Voila entrypoints.

    Only mounts the bus and the shell below it. ``NotificationProvider`` creates
    the bus when its element renders, which is after this body has finished, so
    a component cannot mount a provider for its own ``use_notifications()`` --
    the consumer has to be a separate component rendered after it. Keeping the
    provider here rather than in ``Page`` is what gives the Voila entrypoint,
    which displays this component directly, a working bus too.
    """
    NotificationProvider()
    _AoiGeeShell()


@solara.component
def _AoiGeeShell():
    """Everything the demo shows, one level below the bus it publishes to."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    gee_interface = get_current_gee_interface()
    notifications = use_notifications()

    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(
            zoom=3,
            center=[0, 0],
            gee=True,
            gee_interface=gee_interface,
            fullscreen=True,
            theme_state=theme_state,
        ),
        [id(gee_interface)],
    )

    aoi = solara.use_reactive(None)
    clear_ref = solara.use_ref(None)

    # The live spec channel. AoiView publishes each successful selection here and
    # restores from here, so both buttons below are ordinary reads and writes of
    # one reactive; nothing reaches the file except on a click.
    spec = solara.use_reactive(None)
    has_saved = solara.use_reactive(solara.use_memo(SAVED_AOI.exists, []))

    # Whether restoring also runs the selection, or only fills the form and waits
    # for Select AOI. Read when a spec arrives, so flipping it applies to the next
    # restore rather than to the current AOI.
    autoselect = solara.use_reactive(True)

    def save() -> None:
        save_spec(spec.value)
        has_saved.set(True)
        notifications.success(msg("toasts.saved", method=spec.value.method, file=SAVED_AOI.name))

    def restore() -> None:
        loaded = load_spec()
        if loaded is None:
            has_saved.set(False)
            notifications.warning(msg("toasts.missing", file=SAVED_AOI.name))
            return
        spec.set(loaded)
        notifications.info(msg("toasts.restored", method=loaded.method))

    return MapApp.element(
        app_title=msg("app.title"),
        app_icon="mdi-content-save-move-outline",
        locales=messages.available_locales(),
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": msg("panel.title"),
            "icon": "mdi-map-marker-path",
            "width": 400,
            "description": msg("panel.description"),
        },
        right_panel_content=[
            {
                "title": msg("section.title"),
                "icon": "mdi-map-search-outline",
                "content": [
                    solara.Button(
                        label=msg("buttons.restore"),
                        icon_name="mdi-restore",
                        on_click=restore,
                        disabled=not has_saved.value,
                        color="primary",
                        small=True,
                        block=True,
                    ),
                    rv.Switch(
                        label=msg("switch.label"),
                        v_model=autoselect.value,
                        on_v_model=autoselect.set,
                        dense=True,
                        hint=msg("switch.hint"),
                        persistent_hint=True,
                    ),
                    AoiView(
                        value=aoi,
                        spec=spec,
                        map_=sepal_map,
                        gee=True,
                        methods=METHODS,
                        clear_ref=clear_ref,
                        autoselect=autoselect.value,
                    ),
                    solara.Button(
                        label=msg("buttons.save"),
                        icon_name="mdi-content-save-outline",
                        on_click=save,
                        disabled=spec.value is None,
                        color="primary",
                        small=True,
                        block=True,
                        classes=["mt-2"],
                    ),
                ],
                "description": msg("section.description", path=SAVED_AOI),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
        dialog_width=750,
    )


@solara.component
@with_sepal_sessions(module_name="solara_aoi_gee_app")
def Page():
    """Authenticated Solara-server entrypoint for the GEE AOI demo."""
    AoiGeeAppDemo()
