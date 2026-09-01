"""Custom Card widget to create Tiles in application.

Gather the customized ``ipyvuetifyWidgets`` used to create Tiles in the application panel framework.
All the content of this modules is included in the parent ``pysepal.sepalwidgets`` package. So it can be imported directly from there.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.TileDisclaimer()
"""

from pathlib import Path
from typing import List, Optional, Union

import ipyvuetify as v
from typing_extensions import Self

from pysepal.message import msg
from pysepal.scripts import utils as su
from pysepal.sepalwidgets.sepalwidget import SepalWidget
from pysepal.sepalwidgets.vue_app import ThemeToggle
from pysepal.sepalwidgets.widget import Markdown

__all__ = ["Tile", "TileAbout", "TileDisclaimer"]


class Tile(v.Layout, SepalWidget):

    btn: Optional[v.Btn] = None
    "the process btn"

    alert: Optional[v.Alert] = None
    "the alert to display process information to the end user"

    title: Optional[v.Html] = None
    "the title of the Tile"

    def __init__(
        self,
        id_: str,
        title: str,
        inputs: list = [""],
        btn: Optional[v.Btn] = None,
        alert: Optional[v.Alert] = None,
        **kwargs,
    ) -> None:
        """Custom Layout widget for the sepal UI framework.

        It is an helper to build a consistent tiling system. Tile objects are indeed compatible with the other classes from pysepal.

        Args:
            id_: the tile id that will be written in its mount_id _metadata attribute
            title: the title of the Tile
            inputs: the list of widget to display inside the tile
            btn: the process btn
            alert: the alert to display process information to the end user
            kwargs: any parameter from a v.Layout. if set, 'children' and '_metadata' will be overwritten.
        """
        self.btn = btn
        inputs += [btn] if btn else []

        self.alert = alert
        inputs += [alert] if alert else []

        self.title = v.Html(xs12=True, tag="h2", children=[title])

        content = [v.Flex(xs12=True, children=[widget]) for widget in inputs]

        card = v.Card(class_="pa-5", raised=True, xs12=True, children=[self.title] + content)

        # set some default parameters
        kwargs["_metadata"] = {"mount_id": id_}
        kwargs.setdefault("row", True)
        kwargs.setdefault("align_center", True)
        kwargs.setdefault("class_", "ma-5 d-inline")
        kwargs["children"] = [card]

        # call the constructor
        super().__init__(**kwargs)

    def nest(self) -> Self:
        """Prepare the tile to be used as a nested component in a tile.

        the elevation will be set to 0 and the title remove from children.
        The mount_id will also be changed to nested.
        """
        # remove id
        self._metadata["mount_id"] = "nested_tile"

        # remove elevation
        self.children[0].elevation = False

        # remove title
        self.set_title()

        return self

    def set_content(self, inputs: list) -> Self:
        """Replace the current content of the tile with the provided inputs.

        It will keep the output and btn widget if existing.

        Args:
            the list of widget to display inside the tile
        """
        # create the widgets
        content = [v.Flex(xs12=True, children=[widget]) for widget in inputs]

        # add the output (if existing)
        if self.title:
            content = [self.title] + content

        if self.alert:
            content = content + [self.alert]

        if self.btn:
            content = content + [self.btn]

        self.children[0].children = content

        return self

    def set_title(self, title: str = "") -> Self:
        """Replace the current title and activate it.

        If no title is provided, the title is removed from the tile content.

        Args:
            title: the new title of the object
        """
        # set the title text
        self.title.children = [title]

        # add the title if it's deactivated
        if title and self.title not in self.children[0].children:
            self.children[0].children = [self.title] + self.children[0].children.copy()

        # remove it if it's deactivated
        elif self.title in self.children[0].children and not title:
            # it's the first one
            self.children[0].children = self.children[0].children.copy()[1:]

        return self

    def get_title(self) -> str:
        """Return the current title of the tile.

        Returns:
            the title
        """
        return self.title.children[0]

    def toggle_inputs(
        self, fields_2_show: List[v.VuetifyWidget], fields: List[v.VuetifyWidget]
    ) -> Self:
        """Display only the widgets that are part of the input_list.

        The widget_list is the list of all the widgets of the tile.

        Args:
            fields_2_show: the list of input to be display
            fields: the list of the tile widget
        """
        for field in fields:
            if field in fields_2_show:
                su.show_component(field)
            else:
                su.hide_component(field)

        return self

    def get_id(self) -> str:
        """Get the mount_id value.

        Returns:
            the moun_id value from _metadata dict
        """
        return self._metadata["mount_id"]


class TileAbout(Tile):
    def __init__(self, pathname: Union[str, Path], **kwargs) -> None:
        """Create an about tile using a .md file.

        This tile will have the "about_widget" id and "About" title.

        Args:
            pathname: the path to the .md file
        """
        content = Markdown(Path(pathname).read_text())
        super().__init__("about_tile", "About", inputs=[content])


class TileDisclaimer(Tile):
    def __init__(self, theme_toggle: ThemeToggle = None) -> None:
        """Create an about tile.

        This tile will have the "about_widget" id and "Disclaimer" title.
        """
        super().__init__("about_tile", "Disclaimer")

        self.card = v.Card(class_="pa-5", raised=True, xs12=True, children=[])

        if theme_toggle:
            theme_toggle.observe(self.set_disclaimer, "dark")
        else:
            theme = "dark" if v.theme.dark is True else "light"
            self.set_disclaimer({"new": theme})

        self.children = [self.card]

    def set_disclaimer(self, change) -> List[Markdown]:
        """Rebuild the disclaimer element when the theme changes."""
        # create the tile content on the fly
        # disclaimer.p is a three-paragraph block in every shipped locale
        disclaimer = "  \n".join(msg(f"disclaimer.p.{i}") for i in range(3))
        disclaimer += "  \n"
        disclaimer += '<div style="inline-block">'

        # add the logo (href, src, alt)
        logo_list = [
            ("http://www.openforis.org", "open-foris.png", "openforis_logo"),
            ("https://sepal.io", "sepal.png", "sepal_logo"),
        ]
        theme = "dark" if change["new"] == "dark" else "light"
        url = f"https://raw.githubusercontent.com/openforis/pysepal/main/pysepal/frontend/images/{theme}"
        for href, src, alt in logo_list:
            disclaimer += f'<a href="{href}"><img src="{url}/{src}" alt="{alt}" height="100" class="ma-3"/></a>'

        # close the file
        disclaimer += "</div>"

        self.card.children = [self.title] + [Markdown(disclaimer)]
