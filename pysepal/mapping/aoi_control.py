"""Widget control providing zoom options for the end user."""

from typing import Optional, Union

import ee
import ipyvuetify as v
from ipyleaflet import Map
from shapely import geometry as sg

from pysepal import sepalwidgets as sw
from pysepal.mapping._widget_tree import close_tree
from pysepal.mapping.menu_control import MenuControl
from pysepal.scripts import decorator as sd


class AoiControl(MenuControl):

    m: Optional[Map] = None
    "the map on which he AoiControl is displayed to interact with itszoom and center"

    aoi_list: Optional[sw.ListItemGroup] = None
    "the list of ListItem used in the menu. each one as the name provided by the user and the value of the bounds"

    aoi_bounds: dict = {}
    "the list of bounds to fit on. using the aoi names as keys"

    def __init__(self, m: Map, **kwargs) -> None:
        """Widget control providing zoom options for the end user.

        The developer can add as many gemetries to the widget and the user will simply have to click on them to move to the appropriate AOI.

        Args:
            m: the map on which he AoiControl is displayed to interact with itszoom and center
        """
        # init the aoi data list
        self.aoi_bounds = {}

        # set some default parameters
        kwargs.setdefault("position", "topright")
        kwargs["m"] = m
        self.map_ = m

        # create a list
        self.aoi_list = sw.ListItemGroup(children=[], v_model="")

        # create the widget
        super().__init__("fa-solid fa-search-location", self.aoi_list, **kwargs)

        # change a bit the behavior of the control
        self.menu.open_on_hover = True
        self.menu.open_on_click = False
        self.menu.cole_on_content_click = True

        # set the size of the card to 0 so that the list controls the widget display
        self.set_size(min_width="200px", max_width="200px", min_height=None, max_height="300px")

        # add js behaviours
        self.menu.v_slots[0]["children"].on_event("click", self.click_btn)

    def close(self) -> None:
        """Close the list of AOIs and release the map."""
        close_tree(self.aoi_list)
        self.map_ = None
        super().close()

    def click_btn(self, *args) -> None:
        """Zoom to the total area of all AOIs in :code:`self.aoi_bounds`. Use the whole world if empty."""
        if self.m is None:
            return
        # set the bounds to the world if the list is empty
        if len(self.aoi_bounds) == 0:
            self.m.center = [0, 0]
            self.m.zoom = 2.0
        else:
            minx = min([i[0] for i in self.aoi_bounds.values()])
            miny = min([i[1] for i in self.aoi_bounds.values()])
            maxx = max([i[2] for i in self.aoi_bounds.values()])
            maxy = max([i[3] for i in self.aoi_bounds.values()])
            bounds = (minx, miny, maxx, maxy)
            self.m.zoom_bounds(bounds)

        return

    @sd.need_ee
    def add_aoi(self, name: str, item: Union[sg.base.BaseGeometry, ee.ComputedObject]) -> None:
        """Add an AOI to the list and refresh the list displayed. the AOI will be composed of a name and the bounds of the provided item.

        Args:
            name: the name of the AOI
            item: the item to use to compute the bounds. It need to be a shapely geometry or an ee object.
        """
        if isinstance(item, ee.ComputedObject):
            if self.map_ is None:
                return
            bounds = self.map_.gee_interface.get_bounds(item)

        elif isinstance(item, sg.base.BaseGeometry):
            bounds = item.bounds

        else:
            raise ValueError("Cannot extract bounds from the input")

        self.aoi_bounds[name] = bounds

        # update the list
        self.update_list()

        return

    def remove_aoi(self, name: str) -> None:
        """Remove an item from the :code:`self.aoi_bounds` dict and from the ListItem. It will raise a KeyError if the name cannot be found.

        Args:
            name: the name of the aoi to remove
        """
        # remove the value from the list
        self.aoi_bounds.pop(name)

        # update the list
        self.update_list()

        return

    def zoom(self, widget: v.VuetifyWidget, *args) -> None:
        """Zoom on the specified bounds.

        Args:
            widget: the clicked widget containing the bounds
        """
        if self.m is None:
            return
        # the widget store the bounding box in value
        # a tuple of the bounds of the geometry (minx, miny, maxx, maxy)
        self.m.zoom_bounds(widget.value)

        return

    def update_list(self) -> None:
        """Update the ListItem children of the object based on the content of :code:`self.aoi_bounds`."""
        children = []

        for name, bounds in self.aoi_bounds.items():

            text = sw.ListItemContent(children=[sw.ListItemTitle(children=[name])])
            item = sw.ListItem(dense=True, value=bounds, children=[text])
            children.append(item)
            item.on_event("click", self.zoom)

        previous = self.aoi_list.children
        self.aoi_list.children = children
        close_tree(*previous)

        return
