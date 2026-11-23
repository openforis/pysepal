"""SEPAL Solara map application demo.

One app exercising what a real SEPAL module needs: AOI selection, async
processing with progress notifications, a layer panel over the map's layer store
(opening on a local raster and vector), layer legends that the map shows for the
layers on it, Earth Engine / Drive / SEPAL exports, and every way the file input
selects paths (a dialog step).

This module is only the shell: it opens the session, holds the reactives the
sections share and lays them out. The pieces live under ``component/``:

- ``component/parameter`` -- layer ids, vis params, class breaks, sample paths
- ``component/message`` -- the message catalogue, read through ``msg``
- ``component/model`` -- the app model and the dataclasses carried in reactives
- ``component/scripts`` -- Earth Engine work, layer legends, export sources (no UI)
- ``component/tile`` -- the right-panel sections and the file selection step
- ``component/widget`` -- the map and the lifecycle of its layers

The UI lives in :func:`MapAppDemo` so the same code serves both runtimes --
``Page`` wraps it with SEPAL session auth for Solara, and ``ui.ipynb`` is a thin
Voila entrypoint that displays it directly.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/solara_map_app/app.py --port 8901
```
"""

import solara
from component.message import messages, msg
from component.scripts import sample_folder
from component.tile import ExportPanel, FilesPanel, ProcessPanel, use_layer_tools
from component.widget import use_aoi_scoped_layers, use_sepal_map

from pysepal.message import msg as pysepal_msg
from pysepal.solara import (
    get_current_drive_interface,
    get_current_filesystem,
    get_current_gee_interface,
    get_current_theme_state,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.components.aoi import AoiView
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.notifications import NotificationProvider

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    """Set up sessions management."""
    return setup_sessions()


@solara.component
def MapAppDemo():
    """MapApp shell wiring AOI, processing, layers and export together."""
    setup_theme_colors()

    gee_interface = get_current_gee_interface()
    drive_interface = get_current_drive_interface()
    theme_state = get_current_theme_state()
    samples = sample_folder(get_current_filesystem())

    # State shared between the sections; each section owns whatever is private to it.
    aoi_data = solara.use_reactive(None)
    aoi_loading = solara.use_reactive(False)
    outputs = solara.use_reactive(None)

    sepal_map = use_sepal_map(gee_interface, theme_state)
    use_aoi_scoped_layers(aoi_data, sepal_map, outputs)
    layer_tools = use_layer_tools(sepal_map, outputs)

    aoi_view = AoiView(
        value=aoi_data,
        loading=aoi_loading,
        methods="ALL",
        map_=sepal_map,
        gee=True,
        file_initial_folder=samples,
    )

    right_panel_config = {
        "title": msg("panel.title"),
        "icon": "mdi-map-marker-check",
        "width": 400,
        "description": msg("panel.description"),
    }

    right_panel_content = [
        {
            "title": msg("section.aoi.title"),
            "icon": "mdi-map-marker-check",
            "content": [aoi_view],
        },
        {
            "title": msg("section.process.title"),
            "icon": "mdi-cog-outline",
            "content": [
                ProcessPanel(
                    aoi_data=aoi_data,
                    outputs=outputs,
                    sepal_map=sepal_map,
                    gee_interface=gee_interface,
                )
            ],
            "description": msg("section.process.description"),
        },
        {
            "title": pysepal_msg("layer_panel.title"),
            "icon": "mdi-layers",
            "content": LayerPanel(store=sepal_map.layer_store, map_=sepal_map),
            "description": msg("section.layer_panel.description"),
        },
        {
            "title": msg("section.add_layers.title"),
            "icon": "mdi-layers-plus",
            "content": layer_tools,
            "description": msg("section.add_layers.description"),
            "divider": True,
        },
        {
            "title": msg("section.export.title"),
            "icon": "mdi-export-variant",
            "content": [
                ExportPanel(
                    aoi_data=aoi_data,
                    outputs=outputs,
                    gee_interface=gee_interface,
                    drive_interface=drive_interface,
                )
            ],
            "description": msg("section.export.description"),
        },
    ]

    steps_data = [
        {
            "id": 1,
            "name": msg("steps.files"),
            "icon": "mdi-file-multiple-outline",
            "display": "dialog",
            "content": [FilesPanel(samples=samples)],
            "actions": [{"label": msg("buttons.close"), "close": True}],
        },
    ]

    # Toasts top-right, task progress pill bottom-right.
    NotificationProvider()

    MapApp(
        app_title=msg("app.title"),
        app_icon="mdi-earth",
        main_map=[sepal_map],
        steps_data=steps_data,
        right_panel_config=right_panel_config,
        right_panel_content=right_panel_content,
        right_panel_open=True,
        theme_state=theme_state,
        # The picker offers these catalogs and writes the pick to the scope's
        # locale, which msg reads.
        locales=messages.available_locales(),
        dialog_width=750,
    )


@solara.component
@with_sepal_sessions(module_name="solara_map_app")
def Page():
    """Authenticated Solara-server entrypoint for the map app demo."""
    MapAppDemo()
