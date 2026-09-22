"""Synthetic series and the ipecharts options built from them: data, no UI.

The options carry no prose on purpose. Every string a user reads comes from the
catalogue through ``msg()``, so the axes are numeric and the captions live in the
components around the chart.
"""

import random

from ipecharts.option import Grid, Option, Tooltip, XAxis, YAxis
from ipecharts.option.series import Bar, Line

#: Enough points that a chart drawn at the wrong width is obvious at a glance.
POINT_COUNT = 12


def sample_series(count: int = POINT_COUNT) -> list[int]:
    """Return a plausible-looking series. No network, no credentials, no files."""
    walk, value = [], random.randint(40, 60)
    for _ in range(count):
        value = max(5, min(100, value + random.randint(-12, 14)))
        walk.append(value)
    return walk


def _grid() -> Grid:
    """Tight margins, so the plot area tracks the container instead of the padding."""
    return Grid(left="8%", right="4%", top="12%", bottom="12%", containLabel=True)


def bar_option(values: list[int]) -> Option:
    """A bar chart of ``values``, indexed from one."""
    return Option(
        xAxis=XAxis(type="category", data=[str(index + 1) for index in range(len(values))]),
        yAxis=YAxis(type="value"),
        series=[Bar(data=values)],
        tooltip=Tooltip(trigger="axis"),
        grid=_grid(),
    )


def line_option(values: list[int]) -> Option:
    """The same values as a line, for the contexts that show two charts at once."""
    return Option(
        xAxis=XAxis(
            type="category",
            boundaryGap=False,
            data=[str(index + 1) for index in range(len(values))],
        ),
        yAxis=YAxis(type="value"),
        series=[Line(data=values, areaStyle={}, smooth=True)],
        tooltip=Tooltip(trigger="axis"),
        grid=_grid(),
    )
