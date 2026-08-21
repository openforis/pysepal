"""Saving an AOI and getting it back: the two channels of ``AoiView``.

``AoiView`` carries two different things on two different channels, and the
difference is the whole point of this demo:

* ``value``/``on_value`` carries an :class:`AoiResult` -- a GeoDataFrame and,
  when Earth Engine is on, an ``ee`` object. It is what you compute with, and it
  cannot be written to disk.
* ``spec``/``on_spec`` carries an :class:`AoiSpec` -- the small JSON record of
  what the user actually picked. It is what you persist, and passing it back
  rebuilds both the picker and the AOI.

So the app below writes ``spec.to_dict()`` to a file on every successful
selection, and reads it back on load. Pick a country, restart the server, and
the AOI is on the map again with the dropdowns filled in.

Earth Engine is off, so this runs with no credentials at all: the admin
boundaries come from FAO's WFS service and the file methods read local files.
That also means the ASSET method is not offered here -- it needs GEE.

The saved file lives in the scratch directory, so nothing in the repo changes.
Delete it, or press Clear, to start over.

The UI lives in :func:`AoiAppDemo` so the same code serves both runtimes --
``Page`` is the Solara entrypoint and ``ui.ipynb`` is a thin Voila one.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_aoi_app/app.py --port 8901
```
"""

import json
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


def save_spec(spec: Optional[AoiSpec]) -> None:
    """Write a selection to disk, or delete the file when the AOI was cleared.

    Args:
        spec: The selection to persist. ``None`` means the user cleared the AOI,
            which must erase the file rather than leave the old one behind.
    """
    if spec is None:
        SAVED_AOI.unlink(missing_ok=True)
        return
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
    except (ValueError, json.JSONDecodeError):
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

    # Read the file once, at mount. AoiView takes it from here: it seeds the
    # picker, runs the selection, and draws the AOI without the user pressing
    # anything.
    restored = solara.use_memo(load_spec, [])
    aoi = solara.use_reactive(None)
    clear_ref = solara.use_ref(None)

    # The switch below drives AoiView's `autoselect`. Flipping it re-keys the
    # picker so the restore runs again under the new setting -- otherwise the
    # change would only show on the next page load, since a spec is applied
    # once. Remounting is a demo affordance, not how restore normally works.
    autoselect = solara.use_reactive(True)

    def persist(spec: Optional[AoiSpec]) -> None:
        save_spec(spec)
        if spec is None:
            notifications.info(f"Cleared. Removed {SAVED_AOI.name}.")
        else:
            notifications.success(f"Saved {spec.method} selection to {SAVED_AOI.name}.")

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
                "Pick an AOI, then reload the page. The selection comes back, "
                "because only the spec was saved and the geometry was rebuilt."
            ),
        },
        right_panel_content=[
            {
                "title": "Select",
                "icon": "mdi-map-search-outline",
                "content": [
                    rv.Switch(
                        label="Process a restored AOI automatically",
                        v_model=autoselect.value,
                        on_v_model=autoselect.set,
                        dense=True,
                        hint=(
                            "On: the saved AOI is drawn on load. "
                            "Off: the form is filled and you press Select AOI."
                        ),
                        persistent_hint=True,
                    ),
                    AoiView(
                        value=aoi,
                        spec=restored,
                        on_spec=persist,
                        map_=sepal_map,
                        gee=False,
                        clear_ref=clear_ref,
                        autoselect=autoselect.value,
                    ).key(f"aoi-autoselect-{autoselect.value}"),
                ],
                "description": (
                    f"Saved to {SAVED_AOI}. Clearing the AOI deletes that file, so "
                    f"a cleared selection stays cleared across a reload."
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
