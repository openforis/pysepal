"""Saving an AOI and getting it back: the two channels of ``AoiView``.

``AoiView`` carries two different things on two different channels, and the
difference is the whole point of this demo:

* ``value``/``on_value`` carries an :class:`AoiResult` -- a GeoDataFrame and,
  when Earth Engine is on, an ``ee`` object. It is what you compute with, and it
  cannot be written to disk.
* ``spec``/``on_spec`` carries an :class:`AoiSpec` -- the small JSON record of
  what the user actually picked. It is what you persist, and passing it back
  rebuilds both the picker and the AOI.

The spec channel is two-way and lives entirely in memory. This app holds it in
one reactive: ``AoiView`` writes every successful selection into it, and reading
a saved selection back means writing that reactive. The disk is not part of that
loop -- the **Save** and **Restore** buttons are the only code here that touches
the file, so an app that never persists anything simply never adds them.

Earth Engine is off, so this runs with no credentials at all: the admin
boundaries come from FAO's WFS service and the file methods read local files.
That also means the ASSET method is not offered here -- it needs GEE.

The saved file lives in the scratch directory, so nothing in the repo changes.
Delete it to start over.

The UI lives in :func:`AoiAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_aoi_app/app.py --port 8901
```
"""

import json
from pathlib import Path
from typing import Optional

import reacton.ipyvuetify as rv
import solara

from pysepal import mapping as sm
from pysepal.scripts.scratch import scratch_root
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_theme_state,
    setup_solara_server,
    setup_theme_colors,
)
from pysepal.solara.components.aoi import AoiSpec, AoiView
from pysepal.solara.notifications import NotificationProvider, use_notifications

setup_solara_server(extra_asset_locations=[])

#: Where the demo keeps the persisted selection between runs.
SAVED_AOI = scratch_root() / "demo_aoi_spec.json"

#: Sample AOIs the SHAPE and POINTS pickers open on, in every format they read.
DEMO_DATA = Path(__file__).resolve().parents[1] / "data"


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
def AoiAppDemo():
    """The demo UI, shared by the Solara and Voila entrypoints."""
    setup_theme_colors()
    theme_state = get_current_theme_state()
    notifications = use_notifications()

    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(gee=False, fullscreen=True, theme_state=theme_state), []
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
        notifications.success(f"Saved the {spec.value.method} selection to {SAVED_AOI.name}.")

    def restore() -> None:
        loaded = load_spec()
        if loaded is None:
            has_saved.set(False)
            notifications.warning(f"{SAVED_AOI.name} is missing or unreadable.")
            return
        spec.set(loaded)
        notifications.info(f"Restored a {loaded.method} selection.")

    return MapApp.element(
        app_title="AOI save & restore",
        app_icon="mdi-content-save-move-outline",
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config={
            "title": "Area of interest",
            "icon": "mdi-map-marker-path",
            "width": 400,
            "description": (
                "Pick an AOI and save it. Restoring it later rebuilds the geometry "
                "from the spec alone -- only that small JSON record was written."
            ),
        },
        right_panel_content=[
            {
                "title": "Select",
                "icon": "mdi-map-search-outline",
                "content": [
                    solara.Row(
                        children=[
                            solara.Button(
                                label="Save this AOI",
                                icon_name="mdi-content-save-outline",
                                on_click=save,
                                disabled=spec.value is None,
                                text=True,
                            ),
                            solara.Button(
                                label="Restore saved AOI",
                                icon_name="mdi-restore",
                                on_click=restore,
                                disabled=not has_saved.value,
                                text=True,
                            ),
                        ]
                    ),
                    rv.Switch(
                        label="Process a restored AOI automatically",
                        v_model=autoselect.value,
                        on_v_model=autoselect.set,
                        dense=True,
                        hint=(
                            "On: Restore draws the AOI straight away. "
                            "Off: it fills the form and you press Select AOI."
                        ),
                        persistent_hint=True,
                    ),
                    AoiView(
                        value=aoi,
                        spec=spec,
                        map_=sepal_map,
                        gee=False,
                        file_initial_folder=str(DEMO_DATA),
                        clear_ref=clear_ref,
                        autoselect=autoselect.value,
                    ),
                ],
                "description": (
                    f"Save writes {SAVED_AOI}. Nothing else on this page reads or "
                    f"writes it, so clearing the AOI leaves the saved one alone."
                ),
            }
        ],
        right_panel_open=True,
        theme_state=theme_state,
        dialog_width=750,
    )


@solara.component
def Page():
    """Solara entrypoint -- no SEPAL session, no Earth Engine, no credentials."""
    NotificationProvider()
    AoiAppDemo()
