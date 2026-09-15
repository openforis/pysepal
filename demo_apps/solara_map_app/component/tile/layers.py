"""Right-panel section holding the standalone layer controls.

This section is a hook returning MapApp content rather than a
``@solara.component``: it mixes Solara elements with pre-built ipyvuetify
buttons, and ``solara.display`` re-creates a widget instead of embedding the
instance, which would drop the ``on_event`` handlers wired below. Handing the
widgets straight to MapApp's content list keeps them intact.
"""

import logging

import solara
from component.message import msg
from component.model import AppModel, LayerLegend
from component.parameter import (
    DEMO_CENTER,
    NDVI_LAYER_ID,
    NDVI_VIS,
    PMTILES_CENTER,
    PMTILES_LAYER_ID,
    PMTILES_STYLE,
    PMTILES_URL,
)
from component.scripts import gradient_legend, ndvi_composite, upsert_legends
from ipyleaflet import PMTilesLayer

import pysepal.sepalwidgets as sw
from pysepal.solara.components.admin import AdminButton
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

logger = logging.getLogger("SEPALUI.map_app")


def use_layer_tools(sepal_map, layer_legends, outputs) -> list:
    """Return the content of the "Layers" panel section."""

    async def add_ndvi_layer():
        """Add the demo layer.

        Scheduled through ``use_task`` rather than ``gee_interface.create_task``: the
        latter runs on GEEInterface's own event loop, and two loops sharing the
        eeclient http/2 client crash it mid-request.
        """
        await sepal_map.add_ee_layer_async(
            ndvi_composite(),
            vis_params=NDVI_VIS,
            name=msg("layers.ndvi"),
            key=NDVI_LAYER_ID,
        )
        sepal_map.center = DEMO_CENTER
        sepal_map.zoom = 12
        layer_legends.set(
            upsert_legends(
                layer_legends.value,
                LayerLegend(
                    NDVI_LAYER_ID,
                    msg("layers.ndvi"),
                    gradient_legend(msg("layers.ndvi_short"), NDVI_VIS),
                ),
            )
        )

    ndvi_task = solara.lab.use_task(
        add_ndvi_layer, dependencies=None, raise_error=False, prefer_threaded=False
    )
    ndvi_btn_props = use_task_button(ndvi_task, on_start=ndvi_task)

    def build_layer_buttons():
        """Build the sync ipyvuetify buttons once; they close over stable reactives."""
        btn_pmtiles = sw.Btn(msg("buttons.add_pmtiles"), small=True, block=True)
        btn_remove = sw.Btn(msg("buttons.remove_all"), small=True, block=True)

        def add_pmtiles_layer():
            """Add vector tiles, which the layer control drives without Earth Engine."""
            sepal_map.add_layer(
                PMTilesLayer(name=msg("layers.pmtiles"), url=PMTILES_URL, style=PMTILES_STYLE),
                key=PMTILES_LAYER_ID,
            )
            sepal_map.center = PMTILES_CENTER
            sepal_map.zoom = 14

        def remove_all_layers():
            sepal_map.remove_all()
            sepal_map.center = DEMO_CENTER
            sepal_map.zoom = 5
            layer_legends.set(())
            outputs.set(None)

        btn_pmtiles.on_event("click", lambda *args: add_pmtiles_layer())
        btn_remove.on_event("click", lambda *args: remove_all_layers())
        return btn_pmtiles, btn_remove

    btn_pmtiles, btn_remove = solara.use_memo(
        build_layer_buttons, [id(sepal_map), msg("buttons.add_pmtiles")]
    )
    app_model = solara.use_memo(AppModel, [])

    return [
        TaskButtonComponent(
            label=msg("buttons.add_layer"), **ndvi_btn_props, small=True, block=True
        ),
        btn_pmtiles,
        btn_remove,
        AdminButton(app_model, logger_instance=logger),
    ]
