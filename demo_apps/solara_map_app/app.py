"""SEPAL Solara map application demo.

One app exercising what a real SEPAL module needs: AOI selection, async
processing with progress notifications, layer management, a floating map legend
driven by the layers currently on the map, and Earth Engine / Drive / SEPAL
exports.

This module is only the shell: it opens the session, holds the reactives the
sections share and lays them out. The pieces live under ``component/``:

- ``component/parameter`` -- layer ids, vis params, class breaks, sample paths
- ``component/message`` -- the locale-following translator
- ``component/model`` -- the app model and the dataclasses carried in reactives
- ``component/scripts`` -- Earth Engine work, legend numbers, export sources (no UI)
- ``component/tile`` -- the right-panel sections
- ``component/widget`` -- the map, its layer lifecycle and the floating legend

The UI lives in :func:`MapAppDemo` so the same code serves both runtimes --
``Page`` wraps it with SEPAL session auth for Solara, and ``ui.ipynb`` is a thin
Voila entrypoint that displays it directly.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_map_app/app.py --port 8901
```
"""

import solara
from component.message import use_translator
from component.parameter import DUMMY_DATA_DIR
from component.scripts import load_spec, save_spec
from component.tile import ExportPanel, ProcessPanel, use_layer_tools
from component.widget import MapLegend, use_aoi_scoped_layers, use_sepal_map

from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import (
    get_current_drive_interface,
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.components.aoi import AoiView
from pysepal.solara.notifications import NotificationProvider

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    """Set up sessions management."""
    return setup_sessions()


@solara.component
def MapAppDemo():
    """MapApp shell wiring AOI, processing, layers, legend and export together."""
    setup_theme_colors()

    gee_interface = get_current_gee_interface()
    drive_interface = get_current_drive_interface()
    theme_state = get_current_theme_state()

    # Rebuilt whenever the app-bar picker resolves a new locale, so a language
    # change re-renders in place -- no page reload, and no ~/.sepal-ui-config.
    cm = use_translator()

    # State shared between the sections; each section owns whatever is private to it.
    aoi_data = solara.use_reactive(None)
    aoi_loading = solara.use_reactive(False)
    outputs = solara.use_reactive(None)
    layer_legends = solara.use_reactive(())

    sepal_map = use_sepal_map(gee_interface, theme_state)
    use_aoi_scoped_layers(aoi_data, sepal_map, outputs, layer_legends)
    layer_tools = use_layer_tools(sepal_map, layer_legends, outputs)

    # Read this user's saved selection once, at mount. AoiView seeds the picker
    # from it, reruns the selection and redraws the AOI — so the module reopens
    # where its user left off, including a filtered Earth Engine asset.
    restored_aoi = solara.use_memo(load_spec, [])

    aoi_view = AoiView(
        value=aoi_data,
        loading=aoi_loading,
        methods="ALL",
        map_=sepal_map,
        gee=True,
        file_initial_folder=str(DUMMY_DATA_DIR),
        spec=restored_aoi,
        on_spec=save_spec,
    )

    right_panel_config = {
        "title": cm.panel.title,
        "icon": "mdi-map-marker-check",
        "width": 400,
        "description": cm.panel.description,
    }

    right_panel_content = [
        {
            "title": cm.section.aoi.title,
            "icon": "mdi-map-marker-check",
            "content": [aoi_view],
        },
        {
            "title": cm.section.process.title,
            "icon": "mdi-cog-outline",
            "content": [
                ProcessPanel(
                    aoi_data=aoi_data,
                    outputs=outputs,
                    layer_legends=layer_legends,
                    sepal_map=sepal_map,
                    gee_interface=gee_interface,
                )
            ],
            "description": cm.section.process.description,
        },
        {
            "title": cm.section.layers.title,
            "icon": "mdi-layers",
            "content": layer_tools,
            "description": cm.section.layers.description,
            "divider": True,
        },
        {
            "title": cm.section.export.title,
            "icon": "mdi-export-variant",
            "content": [
                ExportPanel(
                    aoi_data=aoi_data,
                    outputs=outputs,
                    gee_interface=gee_interface,
                    drive_interface=drive_interface,
                )
            ],
            "description": cm.section.export.description,
        },
    ]

    # Toasts top-right, task progress pill bottom-right.
    NotificationProvider()

    MapLegend(layer_legends)

    MapApp.element(
        app_title=cm.app.title,
        app_icon="mdi-earth",
        main_map=[sepal_map],
        steps_data=[],
        right_panel_config=right_panel_config,
        right_panel_content=right_panel_content,
        right_panel_open=True,
        theme_state=theme_state,
        # The picker offers these catalogs and writes the pick to the
        # connection's LocaleState -- the same one use_translator reads.
        locales=cm.available_locales(),
        dialog_width=750,
    )


@solara.component
@with_sepal_sessions(module_name="solara_map_app")
def Page():
    """Authenticated Solara-server entrypoint for the map app demo."""
    MapAppDemo()
