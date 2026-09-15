"""Right-panel section that runs the demo processing."""

import asyncio

import solara
from component.message import msg
from component.model import LayerLegend
from component.parameter import (
    ELEVATION_CLASS_LAYER_ID,
    ELEVATION_CLASSES,
    PIXEL_AREA_LAYER_ID,
    PIXEL_AREA_VIS,
)
from component.scripts import (
    build_outputs,
    elevation_class_legend,
    gradient_legend,
    upsert_legends,
)

from pysepal.solara.notifications import use_notifications


@solara.component
def ProcessPanel(aoi_data, outputs, layer_legends, sepal_map, gee_interface):
    """Run the demo processing, add its layers and publish their legends."""
    notifications = use_notifications()

    async def run_process():
        if aoi_data.value is None or aoi_data.value.feature_collection is None:
            raise ValueError(msg("errors.no_aoi"))

        built = build_outputs(aoi_data.value)

        with notifications.track(msg("tasks.process"), total_steps=4) as task:
            task.step(msg("tasks.building"))
            await asyncio.sleep(0.5)
            task.set_progress(0.2)

            task.step(msg("tasks.adding_layers"))
            await sepal_map.add_ee_layer_async(
                built.pixel_area,
                vis_params=PIXEL_AREA_VIS,
                name=msg("layers.pixel_area"),
                key=PIXEL_AREA_LAYER_ID,
            )
            await sepal_map.add_ee_layer_async(
                built.elevation_class,
                vis_params={
                    "min": 1,
                    "max": len(ELEVATION_CLASSES),
                    "palette": [color for _, _, color in ELEVATION_CLASSES],
                },
                name=msg("layers.elevation"),
                key=ELEVATION_CLASS_LAYER_ID,
            )
            task.set_progress(0.6)

            task.step(msg("tasks.measuring"))
            class_legend = await elevation_class_legend(gee_interface, built)
            task.set_progress(0.9)

            task.step(msg("tasks.publishing"))
            layer_legends.set(
                upsert_legends(
                    layer_legends.value,
                    LayerLegend(
                        PIXEL_AREA_LAYER_ID,
                        msg("layers.pixel_area"),
                        gradient_legend(msg("layers.pixel_area"), PIXEL_AREA_VIS),
                    ),
                    LayerLegend(ELEVATION_CLASS_LAYER_ID, msg("layers.elevation"), class_legend),
                )
            )
            outputs.set(built)

        notifications.success(msg("toasts.process_done"))

    async def run_failing_process():
        """Simulate a Python exception mid-task to exercise error handling."""
        with notifications.track(msg("tasks.risky"), total_steps=2) as task:
            task.step(msg("tasks.calling"))
            await asyncio.sleep(1)
            task.set_progress(0.5)

            task.step(msg("tasks.parsing"))
            await asyncio.sleep(0.5)
            raise RuntimeError(msg("errors.simulated"))

    process_task = solara.lab.use_task(
        run_process, dependencies=None, raise_error=False, prefer_threaded=False
    )
    failing_task = solara.lab.use_task(
        run_failing_process, dependencies=None, raise_error=False, prefer_threaded=False
    )

    has_aoi = aoi_data.value is not None and aoi_data.value.feature_collection is not None

    with solara.Column(style="gap: 8px;"):
        solara.Button(
            msg("buttons.process"),
            on_click=process_task,
            color="primary",
            loading=process_task.pending,
            disabled=process_task.pending or not has_aoi,
            small=True,
            block=True,
        )
        solara.Button(
            msg("buttons.simulate"),
            on_click=failing_task,
            color="error",
            outlined=True,
            loading=failing_task.pending,
            disabled=failing_task.pending,
            small=True,
            block=True,
        )
