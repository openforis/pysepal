"""The chart every context mounts, and the menu that holds it on the map.

No context tells a chart that its box changed: since ipecharts 1.4.2 the chart
watches its own element and redraws when it changes size or becomes visible.
"""

import reacton.ipyvuetify as rv
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


@solara.component
def MapChartMenu(values: list[int], title: str, width: str = "360px"):
    """A button over the map that opens the chart in a card.

    The menu builds its content on the first open, so the chart starts in a box
    that has no size yet.

    Args:
        values: the series to draw.
        title: the card's title.
        width: CSS width of the card.
    """
    open_, set_open = solara.use_state(False)
    button = rv.Btn(
        v_bind="menu.props",
        icon=True,
        size="small",
        attributes={"aria-label": title},
        children=[rv.Icon(children=["mdi-chart-bar"])],
    )
    card = rv.Card(
        width=width,
        children=[rv.CardTitle(children=[title]), rv.CardText(children=[ContextChart(values)])],
    )
    return rv.Menu(
        v_model=open_,
        on_v_model=set_open,
        close_on_content_click=False,
        location="bottom end",
        v_slots=[{"name": "activator", "variable": "menu", "children": [button]}],
        children=[card],
    )
