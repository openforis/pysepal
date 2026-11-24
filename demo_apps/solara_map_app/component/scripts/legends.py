"""Legends that say more than a layer's style, for the map to show.

``MapView`` derives a legend from each layer's style: a gradient for a palette,
a chip for a vector. A layer given its own legend shows that one instead, which
is how a composite names its channels and a classification shows its areas.
"""

import ee
from component.message import msg
from component.model import ProcessingOutputs
from component.parameter import ELEVATION_CLASSES

from pysepal.layers import Legend, LegendItem


def band_legend(bands) -> Legend:
    """One chip per channel of an RGB composite, labelled with what the channel carries."""
    return Legend(items=[LegendItem(label=msg(key), color=color) for key, color in bands])


def _area_detail(area_km2: float, total_km2: float) -> str:
    """Format one legend detail cell as area plus share of the total."""
    share = (area_km2 / total_km2 * 100) if total_km2 else 0.0
    return f"{area_km2:,.0f} km² · {share:.0f}%"


async def elevation_class_legend(gee_interface, outputs: ProcessingOutputs) -> Legend:
    """Reduce the classified image to per-class areas and put them in the legend.

    `LegendItem.detail` is what makes this possible: the numbers ride along
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
        LegendItem(
            label=msg(label_key),
            color=color,
            detail=_area_detail(area_by_class.get(value, 0.0), total),
        )
        for value, label_key, color in ELEVATION_CLASSES
    ]
    # An entry with no color renders without a chip, which reads as a totals row.
    items.append(LegendItem(label=msg("legend.total"), color="", detail=_area_detail(total, total)))

    return Legend(items=items)
