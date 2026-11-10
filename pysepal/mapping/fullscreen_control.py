"""Customized control to toggle the fullscreen state of the map."""

from typing import List, Optional

import ipyvuetify as v
from ipyleaflet import Map, WidgetControl

from pysepal.frontend.resize_trigger import rt
from pysepal.mapping._widget_tree import close_parts
from pysepal.mapping.map_btn import MapBtn


class FullScreenControl(WidgetControl):

    ICONS: List[str] = ["fa-solid fa-expand", "fa-solid fa-compress"]
    "list: The icons that will be used to toggle between expand and compressed mode"

    METHODS: List[str] = ["embed", "fullscreen"]
    "list: The javascript methods name to be used to switch from expand to compress mode"

    zoomed: bool = False
    "bool: the current zoomed level: ``True`` for expanded and ``False`` for compressed"

    w_btn: Optional[v.Btn] = None
    "the btn to display on the map"

    template: Optional[v.VuetifyTemplate] = None
    "Embeds the 2 javascripts methods to change the rendering of the map"

    def __init__(self, m: Map, fullscreen: bool = False, fullapp: bool = False, **kwargs) -> None:
        """A custom Fullscreen Button ready to be embed in a map object.

        This button will force the display of the map in fullscreen mode. It should be used instead of the built-in ipyleaflet FullscreenControl if your map is embedding ipyvuetify widgets. I tends to solve the issue raised here: https://github.com/widgetti/ipyvuetify/issues/141. The idea is to fake the fullscreen display by forcing the map container to extend to the full extend of the screen without using a z-index superior to the ipyvuetify overlay.
        simply click on it and the map will automatically expand

        .. versionadded:: 2.7.0

        Args:
            m: the map on which the mutated CSS will be applied (Only work with SepalMap as we are querying the _id)
            fullscreen: either the map should be displayed in fullscreen by default. default to false.
            fullapp: either or not the map will be used as the sole widget/tile of an application
            kwargs: any available arguments from a ipyleaflet WidgetControl
        """
        # register the required zoom value
        self.zoomed = fullscreen
        self.m = m

        # create a btn
        self.w_btn = MapBtn(self.ICONS[self.zoomed])

        # overwrite the widget set in the kwargs (if any)
        kwargs["widget"] = self.w_btn
        kwargs.setdefault("position", "topleft")
        kwargs["transparent_bg"] = True

        # create the widget
        super().__init__(**kwargs)

        # add javascrip behaviour
        self.w_btn.on_event("click", self.toggle_fullscreen)

        if fullapp:
            self.m.add_class("full-screen-map")
        else:
            self.m.remove_class("full-screen-map")

    def toggle_fullscreen(self, *args) -> None:
        """Toggle fullscreen state.

        Toggle the fullscreen state of the map by sending the required javascript method,
        changing the w_btn icons and the zoomed state of the control.
        """
        # change the zoom state
        self.zoomed = not self.zoomed

        # change button icon
        self.w_btn.children[0].children = [self.ICONS[self.zoomed]]

        if self.zoomed:
            self.m.add_class("full-screen-map")
        else:
            self.m.remove_class("full-screen-map")

        rt.resize()

        return

    def close(self) -> None:
        """Close the button and release the map."""
        close_parts(self)
        self.m = None
        super().close()
