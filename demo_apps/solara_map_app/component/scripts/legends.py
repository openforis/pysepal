"""Turn layer definitions and Earth Engine reductions into legend data."""

import ee
from component.message import msg
from component.model import LayerLegend, ProcessingOutputs
from component.parameter import ELEVATION_CLASSES

from pysepal.solara.components.legend import DiscreteEntry, GradientEntry, LegendData


def upsert_legends(current: tuple, *new: LayerLegend) -> tuple:
    """Replace same-id legends in place and append the rest."""
    by_id = {legend.layer_id: legend for legend in current}
    by_id.update({legend.layer_id: legend for legend in new})
    return tuple(by_id.values())


def gradient_legend(title: str, vis: dict) -> LegendData:
    """Build a continuous legend straight from a layer's vis_params."""
    return LegendData(
        gradients=[
            GradientEntry(
                colors=list(vis["palette"]),
                labels=[f"{vis['min']:g}", f"{vis['max']:g}"],
                title=title,
            )
        ]
    )


def _area_detail(area_km2: float, total_km2: float) -> str:
    """Format one legend detail cell as area plus share of the total."""
    share = (area_km2 / total_km2 * 100) if total_km2 else 0.0
    return f"{area_km2:,.0f} km² · {share:.0f}%"


async def elevation_class_legend(gee_interface, outputs: ProcessingOutputs) -> LegendData:
    """Reduce the classified image to per-class areas and put them in the legend.

    `DiscreteEntry.detail` is what makes this possible: the numbers ride along
    with the color chips instead of needing a separate results table.
    """
    grouped = (
        ee.Image.pixelArea()
        .addBands(outputs.elevation_class)
        .reduceRegion(
            reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
            geometry=outputs.region,
            scale=300,
            maxPixels=1e9,
            bestEffort=True,
        )
    )
    groups = (await gee_interface.get_info_async(grouped)).get("groups", [])
    area_by_class = {int(group["class"]): group["sum"] / 1e6 for group in groups}
    total = sum(area_by_class.values())

    items = [
        DiscreteEntry(
            msg(label_key), color, detail=_area_detail(area_by_class.get(value, 0.0), total)
        )
        for value, label_key, color in ELEVATION_CLASSES
    ]
    # An entry with no color renders without a chip, which reads as a totals row.
    items.append(DiscreteEntry(msg("legend.total"), "", detail=_area_detail(total, total)))

    return LegendData(items=items)
