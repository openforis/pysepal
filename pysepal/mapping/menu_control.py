"""Base menu ``Control`` to display widgets to your user."""

from typing import Optional, Union

import ipyvuetify as v
from ipyleaflet import Map, WidgetControl
from traitlets import Bool, Int
from typing_extensions import Self

from pysepal import sepalwidgets as sw
from pysepal.mapping._widget_tree import close_parts
from pysepal.mapping.map_btn import MapBtn


class MenuControl(WidgetControl):

    menu: Optional[sw.Menu] = None
    "the menu displayed on the map as a widget"

    m: Optional[Map] = None
    "the map used to display the control"

    group: Int = Int().tag(sync=True)
    "The group of Menu control, tell how the Menucontrol interact with the others"

    fullscreen: Bool(False).tag(sync=True)
    "Either or not the Menu container should be displayed in fullscreen on top of the map"

    _caller_parts: tuple = ()
    "the card content and title, given by the caller and left open by close"

    def __init__(
        self,
        icon_content: str,
        card_content: Union[v.VuetifyWidget, str],
        card_title: str = "",
        m: Optional[Map] = None,
        group: int = 0,
        fullscreen: bool = False,
        **kwargs,
    ) -> None:
        """Widget control displaying a btn on the map.

        When clicked the menu expand to show the content set by the user and all the others are closed.
        It's used to display interactive tiles directly in the map. If the card_content is a Tile it will be automatically nested.

        Args:
            icon_content: the icon content as specified in the sm.MapBtn object (i.e. a 3 letter name or an icon name)
            card_content: any container from sw. The sw.Tile is specifically design to fit in this component
            card_title: the card title. THe tile title will override this parameter if existing
            m: The map associated with the Menu
            group: The group of Menu control, tell how the Menucontrol interact with the others
            fullscreen: Either or not the Menu container should be displayed in fullscreen on top of the map
        """
        # save the map in the members
        self.m = m
        self._caller_parts = (card_content, card_title)

        # set the menucontrol parameters
        self.group = group
        self.fullscreen = fullscreen

        # create a clickable btn
        btn = MapBtn(content=icon_content, v_on="menu.on")
        slot = {"name": "activator", "variable": "menu", "children": btn}

        # nest the content if it's a sw.Tile
        children = [card_content]
        if isinstance(card_content, sw.Tile):
            card_title = card_content.get_title()
            card_content.nest()
            card_content.class_list.replace("ma-5", "ma-0")
            card_content.children[0].class_list.replace("pa-5", "pa-2")
            card_content.children[0].raised = False
            card_content.children[0].elevation = 0

        # set up a title of needed
        if card_title != "":
            card_title = sw.CardTitle(children=[card_title])
            children.insert(0, card_title)

        # set up the content style
        card = sw.Card(
            tile=True,
            style_="overflow: auto",
            children=children,
        )
        not fullscreen or card.class_list.add("v-menu-fullscreen")

        # assemble everything in a menu
        self.menu = sw.Menu(
            v_model=False,
            close_on_content_click=False,
            children=[card],
            v_slots=[slot],
            offset_x=True,
        )

        # by default MenuControls will be displayed in the bottomright corner
        kwargs.setdefault("position", "bottomright")
        kwargs["widget"] = self.menu

        super().__init__(**kwargs)

        # place the menu according to the widget positioning
        self.update_position(None)
        self.set_size()

        # add some interaction
        self.observe(self.update_position, "position")
        self.menu.observe(self.close_others, "v_model")
        self.menu.observe(self.activate, "v_model")

    def close(self) -> None:
        """Close the menu this control built and release the map.

        The card content and title belong to the caller and stay open.
        """
        close_parts(self, keep=self._caller_parts)
        # a task may still call the control after its map unmounted: methods
        # of the map controls return early once m is None
        self.m = None
        super().close()

    def update_position(self, *args) -> None:
        """Update the position of the menu if the position of the widget is dynamically changed."""
        self.menu.top = "bottom" in self.position
        self.menu.bottom = "top" in self.position
        self.menu.left = "right" in self.position
        self.menu.right = "left" in self.position

        return

    def set_size(
        self,
        min_width: Optional[Union[str, int]] = "400px",
        max_width: Optional[Union[str, int]] = "400px",
        min_height: Optional[Union[str, int]] = "40vh",
        max_height: Optional[Union[str, int]] = "40vh",
    ) -> Self:
        """Set the size of the card using all the sizing parameters from a v.Card.

        Default to None for everything if the menu control is fullscreened to avoid css conflict.

        Args:
          min_width: a fully qualified css description of the wanted min_width. default to 400px.
          max_width: a fully qualified css description of the wanted max_width. default to 400px.
          min_height: a fully qualified css description of the wanted min_height. default to 40vh.
          max_height: a fully qualified css description of the wanted max_height. default to 40vh.
        """
        card = self.menu.children[0]

        # special case to None for everything if the menu is displayed in fullscree
        if self.fullscreen:
            min_width = max_width = min_height = max_height = None

        card.min_width = min_width
        card.max_width = max_width
        card.min_height = min_height
        card.max_height = max_height

        return self

    def close_others(self, *args) -> None:
        """Close all the other menus associated to the map to avoid overlapping.

        all the other Menu control from the same group will be closed if this menu is opened. Other MenuCOntrol from other groups can remain open. User will need to be careful with Widget placements on the map.
        """
        # don't do anything if no map was set to avoid deprecation
        # remove when jumping to sepal-ui 3.0
        if self.m is None:
            return

        # avoid infinite loop by exiting the method when it's closed
        if self.menu.v_model is True:
            [
                setattr(c.menu, "v_model", False)
                for c in self.m.controls
                if isinstance(c, MenuControl) and c != self and c.group == self.group
            ]

        return

    def activate(self, *args) -> None:
        """Change the background color of the btn with respect to the status."""
        # grey is contrasted enough for both light and dark theme
        # could be customized further if requested
        self.menu.v_slots[0]["children"].style_ = "background: gray;" if self.menu.v_model else ""

        return
