"""sepal-ui ``Tile`` object tuned for AOI selection."""

from pathlib import Path
from typing import List, Optional, Union

import ipyvuetify as v
from eeclient.client import EESession

from pysepal import mapping as sm
from pysepal import sepalwidgets as sw
from pysepal.aoi.aoi_view import AoiView
from pysepal.message import msg

__all__ = ["AoiTile"]


class AoiTile(sw.Tile):

    map: Optional[sm.SepalMap] = None
    "pysepal.mapping.SepalMap: a SepalMap object to display the selected aoi"

    view: Optional[AoiView] = None
    "widget: an AoiView object to handle the aoi method selection"

    def __init__(
        self,
        methods: Union[str, List[str]] = "ALL",
        gee: bool = True,
        vector: Union[str, Path] = "",
        admin: Union[int, str] = "",
        asset: Union[str, Path] = "",
        folder: Union[str, Path] = "",
        map_style: Optional[dict] = None,
        gee_session: Optional[EESession] = None,
        **kwargs,
    ) -> None:
        """sw.Tile tailored for the selection of an aoi. it is meant to be used with the aoi. it can be bound to EarthEngine (GAUl 2015 administrative definition) or stay with the GADM Python implementation.

        Args:
            methods: the methods to select the aoi (more information in AoiView), default to 'ALL'. Available: {`ADMIN0`, `ADMIN1`, `ADMIN2`, `SHAPE`, `DRAW`, `POINTS`, `ASSET`, `ALL`}
            gee: whether or not to use the python EartEngine API. default to True
            vector: the path to the default vector object
            admin: the administrative code of the default selection. Need to be GADM if ee==False and GAUL 2015 if ee==True.
            asset: the default asset. Can only work if :code:`ee==True`.
            map_style: the predefined style of the aoi. It's by default using a "success" ``pysepal.color`` with 0.5 transparent fill color. It can be completely replace by a fully qualified `style dictionary <https://ipyleaflet.readthedocs.io/en/latest/layers/geo_json.html>`__. Use the ``pysepal.color`` object to define any color to remain compatible with light and dark theme.
        """
        # create the map
        self.map = sm.SepalMap(dc=True, gee=gee, gee_session=gee_session)
        self.map.dc.hide()

        # create the view
        # the view include the model
        self.view = AoiView(
            methods=methods,
            map_=self.map,
            gee=gee,
            vector=vector,
            admin=admin,
            asset=asset,
            folder=folder,
            map_style=map_style,
            gee_session=gee_session,
            **kwargs,
        )
        self.view.elevation = 0

        # organise them in a layout
        layout = v.Layout(
            row=True,
            xs12=True,
            children=[
                v.Flex(xs12=True, md6=True, class_="pa-5", children=[self.view]),
                v.Flex(xs12=True, md6=True, class_="pa-1", children=[self.map]),
            ],
        )

        # create the tile
        super().__init__("aoi_tile", msg("aoi_sel.title"), inputs=[layout], **kwargs)
