"""Customized ``Control`` to display the value of all available layers on a specific pixel."""

from pathlib import Path
from typing import Optional, Sequence, Union

import ee
import geopandas as gpd
import ipyvuetify as v
from deprecated.sphinx import deprecated
from ipyleaflet import GeoJSON, Map, Marker
from shapely import geometry as sg
from traitlets import Bool

from pysepal import sepalwidgets as sw
from pysepal.mapping.layer import EELayer
from pysepal.mapping.menu_control import MenuControl
from pysepal.message import ms
from pysepal.scripts import decorator as sd
from pysepal.scripts.gee_interface import GEEInterface


class InspectorControl(MenuControl):

    m: Optional[Map] = None
    "the map on which he vinspector is displayed to interact with it's layers"

    w_loading: Optional[v.ProgressLinear] = None
    "The progress bar on top of the Card"

    menu: Optional[v.Menu] = None
    "The menu displayed when the map btn is clicked"

    text: Optional[v.CardText] = None
    "The text element from the card that is edited when the user click on the map"

    open_tree: Bool = Bool(True).tag(sync=True)
    "Either or not the tree should be opened automatically"

    marker: Optional[Marker] = None
    "The marker of the last visited point"

    def __init__(self, m: Map, open_tree: bool = True, **kwargs) -> None:
        """Widget control displaying a btn on the map.

        When clicked the menu expand to show the values of each layer available on the map. The menu values will be change when the user click on a location on the map. It can digest any Layer added on a SepalMap.

        Args:
            m: the map on which he vinspector is displayed to interact with it's layers
        """
        # set traits
        self.open_tree = open_tree

        # set some default parameters
        kwargs.setdefault("position", "topleft")
        kwargs["m"] = m

        # create a loading to place it on top of the card. It will always be visible
        # even when the card is scrolled
        self.w_loading = sw.ProgressLinear(
            indeterminate=False,
            background_color="menu",
        )

        # set up the content
        title = sw.CardTitle(children=[ms.inspector_control.title])
        self.text = sw.CardText(children=[ms.inspector_control.landing])

        # create the menu widget
        super().__init__("fa-solid fa-crosshairs", self.text, title, **kwargs)

        # avoid closing the inspector when clicking on the map
        self.menu.close_on_click = False

        # create a marker outside of the map [91, 181] and hide it
        self.marker = Marker(location=[91, 181], draggable=False, visible=False)
        self.m.add_layer(self.marker)

        # adapt the size
        self.set_size(min_height=0)

        # add js behaviour
        self.menu.observe(self.toggle_cursor, "v_model")
        self.m.on_interaction(self.read_data)

    def toggle_cursor(self, *args) -> None:
        """Toggle the cursor and marker display.

        Toggle the cursor on the map to notify to the user that the inspector
        mode is activated. also activate previous marker if the inspector already include data.
        """
        cursors = [{"cursor": "grab"}, {"cursor": "crosshair"}]
        self.m.default_style = cursors[self.menu.v_model]
        self.marker.visible = self.menu.v_model

        return

    def read_data(self, **kwargs) -> None:
        """Read the data when the map is clicked with the vinspector activated.

        Args:
            kwargs: any arguments from the map interaction
        """
        # check if the v_inspector is active
        is_click = kwargs.get("type") == "click"
        is_active = self.menu.v_model is True
        if not (is_click and is_active):
            return

        # set the loading mode. Cannot be done as a decorator to avoid
        # flickering while moving the cursor on the map
        self.w_loading.indeterminate = True
        self.m.default_style = {"cursor": "wait"}

        # init the text children
        children = []

        # get the coordinates as (x, y)
        lng, lat = coords = [c for c in reversed(kwargs.get("coordinates"))]

        # write the coordinates and the scale
        txt = ms.inspector_control.coords.format(scale=round(self.m.get_scale()))
        children.append(sw.Html(tag="h4", children=[txt]))
        children.append(sw.Html(tag="p", children=[f"[{lng:.3f}, {lat:.3f}]"]))

        # wrap layer data in a treeview widget
        tree_view = sw.Treeview(hoverable=True, dense=True, open_on_click=True)
        children.append(sw.Html(tag="h4", children=[ms.inspector_control.layers]))
        children.append(tree_view)

        # write the layers data
        items, layers = [], [lyr for lyr in self.m.layers if not lyr.base]
        for i, lyr in enumerate(layers):

            if isinstance(lyr, EELayer):
                data = self._from_eelayer(lyr.ee_object, coords)
            elif isinstance(lyr, GeoJSON):
                data = self._from_geojson(lyr.data, coords)
            elif type(lyr).__name__ == "BoundTileLayer":
                data = self._from_raster(lyr.raster, coords)
            elif isinstance(lyr, Marker):
                continue
            else:
                data = {ms.inspector_control.info.header: ms.inspector_control.info.text}

            items.append(
                {
                    "id": str(i),
                    "name": lyr.name,
                    "children": [{"name": f"{k}: {v}"} for k, v in data.items()],
                }
            )
        tree_view.items = items
        tree_view.open_ = "0" if self.open_tree else ""

        # set them in the card
        self.text.children = children

        # place a marker on the right coordinates
        self.marker.location = [lat, lng]

        # set back the cursor to crosshair
        self.w_loading.indeterminate = False
        self.m.default_style = {"cursor": "crosshair"}

        # one last flicker to replace the menu next to the btn
        # if not it goes below the map
        # I've try playing with the styles but it didn't worked out well
        # lost hours on this issue : 2h
        self.menu.v_model = False
        self.menu.v_model = True

        return

    @sd.need_ee
    def _from_eelayer(self, ee_obj: ee.ComputedObject, coords: Sequence[float]) -> dict:
        """Extract the values of the ee_object for the considered point.

        Args:
            ee_obj: the ee object to reduce to a single point
            coords: the coordinates of the point (lng, lat).

        Returns:
            tke value associated to the image/feature names
        """
        # create a gee point
        ee_point = ee.Geometry.Point(*coords)

        gee_interface: GEEInterface = self.m.gee_interface

        if isinstance(ee_obj, ee.FeatureCollection):

            # filter all the value to the point
            features = ee_obj.filterBounds(ee_point)

            # if there is none, print non for every property
            if gee_interface.get_info(features.size()) == 0:
                cols = gee_interface.get_info(ee_obj.first().propertyNames())
                pixel_values = {c: None for c in cols if c not in ["system:index"]}

            # else simply return all the values of the first element
            else:
                pixel_values = gee_interface.get_info(features.first().toDictionary())

        elif isinstance(ee_obj, ee.Image):

            # reduce the layer region using mean
            pixel_values = ee_obj.reduceRegion(
                geometry=ee_point,
                scale=self.m.get_scale(),
                reducer=ee.Reducer.mean(),
            )
            pixel_values = gee_interface.get_info(pixel_values)

        else:
            raise ValueError(f'the layer object is a "{type(ee_obj)}" which is not accepted.')

        return pixel_values

    def _from_geojson(self, data: dict, coords: Sequence[float]) -> dict:
        """Extract the values of the data for the considered point.

        Args:
            data: the shape to reduce to a single point
            coords: the coordinates of the point (lng, lat).

        Returns:
            The value associated to the feature names
        """
        # extract the coordinates as a poin
        point = sg.Point(*coords)

        # filter the data to 1 point
        gdf = gpd.GeoDataFrame.from_features(data)
        gdf_filtered = gdf[gdf.contains(point)]
        skip_cols = ["geometry", "style"]

        # only display the columns name if empty
        if len(gdf_filtered) == 0:
            cols = gdf.columns.to_list()
            return {c: None for c in cols if c not in skip_cols}

        # else print the values of the first element
        else:
            return gdf_filtered.iloc[0, ~gdf.columns.isin(skip_cols)].to_dict()

    def _from_raster(self, raster: Union[str, Path], coords: Sequence[float]) -> dict:
        """Extract the values of the data-array for the considered point.

        Args:
            raster: the path to the image to reduce to a single point
            coords: the coordinates of the point (lng, lat).

        Returns:
            The value associated to the feature names
        """
        import rasterio as rio
        import rioxarray
        from rasterio.crs import CRS

        # extract the coordinates as a point
        point = sg.Point(*coords)

        # extract the pixel size in degrees (equatorial approximation)
        scale = self.m.get_scale() * 0.00001

        # open the image and unproject it
        da = rioxarray.open_rasterio(raster, masked=True)
        da = da.chunk({"x": 1000, "y": 1000})
        if da.rio.crs != CRS.from_string("EPSG:4326"):
            da = da.rio.reproject("EPSG:4326")

        # sample is not available for da so I do as in GEE a mean reducer around 1px
        # is it an overkill ? yes
        if sg.box(*da.rio.bounds()).contains(point):
            bounds = point.buffer(scale).bounds
            window = rio.windows.from_bounds(*bounds, transform=da.rio.transform())
            da_filtered = da.rio.isel_window(window)
            means = da_filtered.mean(axis=(1, 2)).to_numpy()
            pixel_values = {
                ms.inspector_control.band.format(index=i + 1): v for i, v in enumerate(means)
            }

        # if the point is out of the image display None
        else:
            pixel_values = {
                ms.inspector_control.band.format(index=i + 1): None for i in range(da.rio.count)
            }

        return pixel_values


@deprecated(version="2.15.1", reason="ValueInspector class is now renamed InspectorControl")
class ValueInspector(InspectorControl):
    pass
