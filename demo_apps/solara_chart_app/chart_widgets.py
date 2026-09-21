"""The chart pair every context mounts, and the one lever that reaches ``resize()``.

Each context shows the same data twice: once as ipecharts mounts it, once with the
app telling it that its box changed. The difference between the two is the whole
demo -- see ``docs/guides/ipecharts.md`` for why the widget cannot always work
that out on its own.
"""

import asyncio
from typing import Callable, Optional

import ipyvuetify as v
import solara
from chart_messages import msg
from chart_options import bar_option, line_option
from ipecharts import EChartsWidget

#: Toggled on the widget to ask for a redraw. The value means nothing; the change does.
RESIZE_CLASS = "pysepal-chart-nudge"

#: How long to leave the browser to apply a layout change before measuring again.
SETTLE_SECONDS = 0.25

#: Tall enough to read, short enough that two fit in a 400px panel.
CHART_HEIGHT = "200px"


def nudge_resize(widget: EChartsWidget, token: int) -> None:
    """Make ipecharts measure its container again.

    The widget exposes no resize API: its frontend calls ``chart.resize()`` from
    ``update_classes`` and from ``setStyle``, and nowhere else that Python can
    reach. Swapping a class is the cheapest of the two, and ``token`` only has to
    differ from the last one for the trait to fire.
    """
    widget.remove_class(f"{RESIZE_CLASS}-{(token + 1) % 2}")
    widget.add_class(f"{RESIZE_CLASS}-{token % 2}")


def build_chart_widget(values: list[int], height: str = CHART_HEIGHT) -> EChartsWidget:
    """A chart as a plain widget, for the places that take widgets and not elements."""
    return EChartsWidget(
        option=bar_option(values),
        style={"height": height, "width": "100%"},
    )


@solara.component
def ContextChart(
    values: list[int],
    resize_token: int,
    follow_layout: bool,
    height: str = CHART_HEIGHT,
    line: bool = False,
):
    """One chart, which either hears about layout changes or does not.

    Args:
        values: the series to draw.
        resize_token: any value that changes when the chart's box changes.
        follow_layout: whether to act on that token. ``False`` is the control.
        height: CSS height for the chart container.
        line: draw a line instead of bars.
    """
    option = solara.use_memo(
        lambda: line_option(values) if line else bar_option(values),
        [tuple(values), line],
    )
    chart = EChartsWidget.element(option=option, style={"height": height, "width": "100%"})
    widget_ref = solara.use_ref(None)

    def capture():
        # get_widget needs a render context, which a task body does not have.
        widget_ref.current = solara.get_widget(chart)

    solara.use_effect(capture, [])

    async def follow():
        if not follow_layout or widget_ref.current is None:
            return
        # The chart measures its box the moment the trait lands, which can be
        # before the browser has applied the layout change that prompted it --
        # measured: a same-batch nudge redraws at the old width. Let it settle.
        await asyncio.sleep(SETTLE_SECONDS)
        nudge_resize(widget_ref.current, resize_token)

    solara.lab.use_task(
        follow,
        dependencies=[resize_token, follow_layout],
        raise_error=False,
        prefer_threaded=False,
    )


@solara.component
def ChartPair(values: list[int], resize_token: int, line: bool = False):
    """The same chart twice, labelled, so a wrong width shows up as a difference."""
    with solara.Column(gap="4px"):
        solara.Text(msg("chart.raw"), style={"font-size": "0.75rem", "opacity": "0.7"})
        ContextChart(values, resize_token=resize_token, follow_layout=False, line=line)
        solara.Text(msg("chart.nudged"), style={"font-size": "0.75rem", "opacity": "0.7"})
        ContextChart(values, resize_token=resize_token, follow_layout=True, line=line)


def build_widget_button(label: str, on_click: Callable[[], None]) -> v.Btn:
    """A plain ipyvuetify button, for the widget-only slots MapApp exposes.

    Its label is set at construction, so the caller rebuilds it on a language
    change the way ``solara_raster_app`` does: nothing re-renders a widget.
    """
    button = v.Btn(children=[label], small=True, block=True, class_="mt-2")
    button.on_event("click", lambda *args: on_click())
    return button


def build_map_chart_card(
    values: list[int], title: str, width: Optional[str] = None
) -> tuple[v.Card, EChartsWidget]:
    """A chart in a card for the map's menu control, plus the widget to nudge."""
    chart = build_chart_widget(values)
    card = v.Card(
        children=[v.CardTitle(children=[title]), v.CardText(children=[chart])],
        class_="pa-0",
        width=width,
    )
    return card, chart
