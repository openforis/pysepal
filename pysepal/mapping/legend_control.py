"""Customized control to display a legend on the map."""

from typing import Optional, Union

import traitlets as t
from ipyleaflet import WidgetControl
from ipywidgets import HTML
from traitlets import observe

import pysepal.sepalwidgets as sw
from pysepal.message import msg
from pysepal.scripts import utils as su


class LegendControl(WidgetControl):

    title: t.Unicode = t.Unicode(None).tag(sync=True)
    "Title of the legend."

    legend_dict: t.Dict = t.Dict(None).tag(sync=True)
    "Dictionary with key as label name and value as color"

    vertical: t.Bool = t.Bool(None).tag(sync=True)
    "Whether to display the legend in a vertical or horizontal way"

    _html_table: Optional[sw.Html] = None
    "The table containing the legend display"

    _html_title: Optional[sw.Html] = None
    "The tilte of the legend"

    def __init__(
        self,
        legend_dict: dict = {},
        title: Optional[str] = None,
        vertical: bool = True,
        **kwargs,
    ) -> None:
        """A custom Legend widget ready to be embed in a map.

        This Legend can be control though it's different attributes, changing it's position of course but also the orientation ,the keys and their colors.

        .. versionadded:: 2.10.4

        Args:
            legend_dict: the dictionary to fill the legend values. cannot be empty.
            title: title of the legend, if not set a default value in the current language will be used
            vertical: the orientation of the legend. default to True
        """
        title = msg("mapping.legend") if title is None else title

        # init traits
        self.title = title
        self.legend_dict = legend_dict
        self.vertical = vertical

        # generate the content based on the init options
        self._html_title = sw.Html(tag="h4", children=[f"{self.title}"])
        self._html_table = sw.Html(tag="table", children=[])

        # create a card inside the widget
        # Be sure that the scroll bar will be shown up when legend horizontal
        self.legend_card = sw.Card(
            attributes={"id": "legend_card"},
            style_="overflow-x:auto; white-space: nowrap;",
            max_width=450,
            max_height=350,
            children=[self._html_title, self._html_table],
        ).hide()

        # set some parameters for the actual widget
        kwargs["widget"] = self.legend_card
        kwargs.setdefault("position", "bottomright")

        super().__init__(**kwargs)

        self._set_legend(legend_dict)

    def __len__(self) -> int:
        """Returns the number of elements in the legend."""
        return len(self.legend_dict)

    def hide(self) -> None:
        """Hide control by hiding its content."""
        self.legend_card.hide()

        return

    def show(self) -> None:
        """Show control by displaying its content."""
        self.legend_card.show()

        return

    @observe("legend_dict", "vertical")
    def _set_legend(self, *args) -> None:
        """Creates/update a legend based on the class legend_dict member."""
        # Do this to avoid crash when called by trait for the first time
        if self._html_table is None:
            return

        if not self.legend_dict:
            self.hide()
            return

        self.show()

        if self.vertical:
            elements = [
                sw.Html(
                    tag="tr" if self.vertical else "td",
                    children=[
                        sw.Html(tag="td", children=self.color_box(color)),
                        label.capitalize(),
                    ],
                )
                for label, color in self.legend_dict.items()
            ]
        else:
            elements = [
                (
                    sw.Html(
                        tag="td",
                        children=[label.capitalize()],
                    ),
                    sw.Html(
                        tag="td",
                        children=self.color_box(color),
                    ),
                )
                for label, color in self.legend_dict.items()
            ]
            # Flat nested list
            elements = [e for row in elements for e in row]

        self._html_table.children = elements

        return

    @observe("title")
    def _update_title(self, change: dict) -> None:
        """Trait method to update the title of the legend."""
        # Do this to avoid crash when called by trait
        if self._html_title is None:
            return

        self._html_title.children = change["new"]

        return

    @staticmethod
    def color_box(color: Union[str, tuple], size: int = 35) -> HTML:
        """Returns an rectangular SVG html element with the provided color.

        Args:
            color: It can be a string (e.g., 'red', '#ffff00', 'ffff00') or RGB tuple (e.g., (255, 127, 0))
            size: the size of the legend square

        Returns:
            The HTML rendered color box
        """
        # Define height and width based on the size
        w = size
        h = size / 2

        return [
            HTML(
                f"""
                    <th>
                        <svg width='{w}' height='{h}'>
                        <rect width='{w}' height='{h}' style='fill:{su.to_colors(color)};
                        stroke-width:1;stroke:rgb(255,255,255)'/>
                        </svg>
                    </th>
                """
            )
        ]
