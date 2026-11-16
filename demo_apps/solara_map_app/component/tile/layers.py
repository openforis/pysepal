"""Right-panel section holding the standalone layer controls.

A hook returning the section's content, a list of elements that MapApp renders
one under the other.
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
    RADAR_BANDS,
    RADAR_CENTER,
    RADAR_LAYER_ID,
    RADAR_VIS,
)
from component.scripts import (
    band_legend,
    gradient_legend,
    ndvi_composite,
    radar_composite,
    upsert_legends,
)
from ipyleaflet import PMTilesLayer

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

    async def add_radar_layer():
        """Add the Sentinel-1 composite; same loop rule as the NDVI layer."""
        await sepal_map.add_ee_layer_async(
            radar_composite(),
            vis_params=RADAR_VIS,
            name=msg("layers.radar"),
            key=RADAR_LAYER_ID,
        )
        sepal_map.center = RADAR_CENTER
        sepal_map.zoom = 11
        layer_legends.set(
            upsert_legends(
                layer_legends.value,
                LayerLegend(RADAR_LAYER_ID, msg("layers.radar"), band_legend(RADAR_BANDS)),
            )
        )

    ndvi_task = solara.lab.use_task(
        add_ndvi_layer, dependencies=None, raise_error=False, prefer_threaded=False
    )
    ndvi_btn_props = use_task_button(ndvi_task, on_start=ndvi_task)
    radar_task = solara.lab.use_task(
        add_radar_layer, dependencies=None, raise_error=False, prefer_threaded=False
    )
    radar_btn_props = use_task_button(radar_task, on_start=radar_task)

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

    app_model = solara.use_memo(AppModel, [])

    return [
        TaskButtonComponent(
            label=msg("buttons.add_layer"), **ndvi_btn_props, small=True, block=True
        ),
        TaskButtonComponent(
            label=msg("buttons.add_radar"), **radar_btn_props, small=True, block=True
        ),
        solara.Button(
            msg("buttons.add_pmtiles"),
            on_click=add_pmtiles_layer,
            color="primary",
            block=True,
            small=True,
        ),
        solara.Button(
            msg("buttons.remove_all"),
            on_click=remove_all_layers,
            color="primary",
            block=True,
            small=True,
        ),
        AdminButton(app_model, logger_instance=logger),
    ]
