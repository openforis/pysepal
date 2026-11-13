"""The chart every context mounts, as an element and as a plain widget.

No context tells a chart that its box changed: since ipecharts 1.4.2 the chart
watches its own element and redraws when it changes size or becomes visible.
"""

from typing import Optional

import ipyvuetify as v
import solara
from chart_options import bar_option, line_option
from ipecharts import EChartsWidget

#: Tall enough to read, short enough that two fit in a 400px panel.
CHART_HEIGHT = "200px"


@solara.component
def ContextChart(values: list[int], line: bool = False, height: str = CHART_HEIGHT):
    """One chart that fills the width of its container.

    Args:
        values: the series to draw.
        line: draw a line instead of bars.
        height: CSS height for the chart container.
    """
    option = solara.use_memo(
        lambda: line_option(values) if line else bar_option(values),
        [tuple(values), line],
    )
    return EChartsWidget.element(option=option, style={"height": height, "width": "100%"})


def build_map_chart_card(values: list[int], width: Optional[str] = None) -> v.Card:
    """A chart in a card for the map's menu control, which takes widgets, not elements."""
    chart = EChartsWidget(
        option=bar_option(values),
        style={"height": CHART_HEIGHT, "width": "100%"},
    )
    return v.Card(children=[v.CardText(children=[chart])], class_="pa-0", width=width)
