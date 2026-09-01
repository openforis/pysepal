"""``Card`` object dedicated to AOI selection. It does not include maps."""

from datetime import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Union

import ipyvuetify as v
import pygadm
import pygaul
import traitlets as t
from deprecated.sphinx import versionadded
from eeclient.client import EESession
from typing_extensions import Self

import pysepal.sepalwidgets as sw
from pysepal import mapping as sm
from pysepal.aoi.aoi_model import AoiModel
from pysepal.message import msg
from pysepal.scripts import decorator as sd
from pysepal.scripts import utils as su

if TYPE_CHECKING:
    from pysepal.scripts.gee_interface import GEEInterface

CUSTOM = AoiModel.CUSTOM
ADMIN = AoiModel.ADMIN
ALL = "All"
select_methods = AoiModel.METHODS

__all__ = ["AoiView", "select_methods"]


class MethodSelect(sw.Select):
    def __init__(
        self,
        methods: Union[str, List[str]] = "ALL",
        gee: bool = True,
        map_: Optional[sm.SepalMap] = None,
    ) -> None:
        """A method selector.

        It will list the available methods for this very AoiView.
        'ALL' will select all the available methods (default)
        'ADMIN' only the admin one, 'CUSTOM' only the custom one.
        'XXX' will add the selected method to the list when '-XXX' will discard it.
        You cannot mix adding and removing behaviours.

        Args:
            methods: a list of methods from the available list (ADMIN0, ADMIN1, ADMIN2, SHAPE, DRAW, POINTS, ASSET)
            map_: link the aoi_view to a custom SepalMap to display the output, default to None
            gee: whether to bind to ee or not
        """
        # create the method list
        if methods == "ALL":
            self.methods = select_methods
        elif methods == "ADMIN":
            self.methods = {k: v for k, v in select_methods.items() if v["type"] == ADMIN}
        elif methods == "CUSTOM":
            self.methods = {k: v for k, v in select_methods.items() if v["type"] == CUSTOM}
        elif type(methods) == list:
            if any(m[0] == "-" for m in methods) != all(m[0] == "-" for m in methods):
                raise Exception("You mixed adding and removing, punk")

            if methods[0][0] == "-":
                to_remove = [method[1:] for method in methods]

                # Rewrite the methods instead of mutate the class methods
                self.methods = {k: v for k, v in select_methods.items() if k not in to_remove}

            else:
                self.methods = {k: select_methods[k] for k in methods}
        else:
            raise Exception("I don't get what you meant")

        # clean the list from things we can't use
        gee is True or self.methods.pop("ASSET", None)
        map_ is not None or self.methods.pop("DRAW", None)

        # build the item list with header
        prev_type = None
        items = []
        for k, m in self.methods.items():
            current_type = m["type"]

            if prev_type != current_type:
                items.append({"header": current_type})
            prev_type = current_type

            items.append({"text": m["name"], "value": k})

        # create the input
        super().__init__(label=msg("aoi_sel.method"), items=items, v_model="", dense=True)


class AdminField(sw.Select):
    gee: bool = True
    "whether or not to depend on earthengine"

    level: int = -1
    "The admin level of the current field"

    parent: Optional[sw.Select] = None
    "The parent adminfield object"

    def __init__(self, level: int, parent: Optional[sw.Select] = None, gee: bool = True) -> None:
        """An admin level selector.

        It is binded to ee (GAUL 2024) or not (GADM). Allows to select administrative codes taking into account the administrative parent code and displaying humanly readable administrative names.

        Args:
            level: The administrative level of the field
            parent: the adminField that deal with the parent admin level of the current selector. used to narrow down the possible options
            ee: whether to use ee or not (default to True)
        """
        # save ee state
        self.gee = gee

        # get the level info
        self.level = level
        self.parent = parent

        # init an empty widget
        super().__init__(v_model=None, items=[], clearable=True, label=msg(f"aoi_sel.adm.{level}"))

        # add js behaviour
        self.parent is None or self.parent.observe(self._update, "v_model")

    def show(self) -> Self:
        """when an admin field is shown, show its parent as well."""
        super().show()
        self.parent is None or self.parent.show()

        return self

    def get_items(self, filter_: str = "") -> Self:
        r"""Update the item list based on the given filter.

        Args:
            filter\_: The code of the parent v_model to filter the current results
        """
        AdmNames = pygaul.Names if self.gee else pygadm.Names
        df = AdmNames(admin=filter_, content_level=self.level)
        df = df.sort_values(by=[df.columns[0]])

        # formatted as a item list for a select component
        # first column will be the name, second the code
        items = []
        for _, r in df.iterrows():
            text = su.normalize_str(r.iloc[0], folder=False)
            items.append({"text": text, "value": str(r.iloc[1])})
        self.items = items

        return self

    def _update(self, change: dict) -> Self:
        """Update the item list of the admin select."""
        # reset v_model
        self.v_model = None

        # update the items list
        if change["new"]:
            self.get_items(change["new"])

        return self


class AoiView(sw.Card):
    # ##########################################################################
    # ###                             widget parameters                      ###
    # ##########################################################################

    updated: t.Int = t.Int(0).tag(sync=True)
    "Traitlets triggered every time a AOI is selected"

    gee: bool = True
    "Either or not he aoi_view is connected to gee"

    folder: Union[str, Path] = ""
    "The folder name used in GEE related component, mainly used for debugging"

    model: Optional[AoiModel] = None
    "The model to create the AOI from the selected parameters"

    map_style: Optional[dict] = None
    "The predefined style of the aoi on the map"

    # ##########################################################################
    # ###                           the embedded widgets                     ###
    # ##########################################################################

    map_: Optional[sm.SepalMap] = None
    "The map to draw the AOI"

    aoi_dc: Optional[sm.DrawControl] = None
    "the drawing control associated with DRAW method"

    w_method: Optional[MethodSelect] = None
    "The widget to select the method"

    components: Dict[str, v.VuetifyWidget] = {}
    "The followingwidgets used to define AOI"

    w_admin_0: Optional[AdminField] = None
    "The widget used to select admin level 0"

    w_admin_1: Optional[AdminField] = None
    "The widget used to select admin level 1"

    w_admin_2: Optional[AdminField] = None
    "The widget used to select admin level 2"

    w_vector: Optional[sw.VectorField] = None
    "The widget used to select vector shapes"

    w_points: Optional[sw.LoadTableField] = None
    "The widget used to select points files"

    w_draw: Optional[sw.TextField] = None
    "The widget used to select the name of a drawn shape (only if :code:`map_ != None`)"

    w_asset: Optional[sw.AssetSelect] = None
    "The widget used to select asset name of a featureCollection (only if :code:`gee == True`)"

    btn: Optional[sw.Btn] = None
    "A default btn"

    alert: Optional[sw.Alert] = None
    "A alert to display message to the end user"

    @versionadded(
        version="2.11.3",
        reason="Model is now an optional parameter to AoiView, it can be created from outside and passed to the initialization function.",
    )
    def __init__(
        self,
        methods: Union[str, List[str]] = "ALL",
        map_: Optional[sm.SepalMap] = None,
        gee: bool = True,
        folder: Union[str, Path] = "",
        model: Optional[AoiModel] = None,
        map_style: Optional[dict] = None,
        gee_session: Optional[EESession] = None,
        gee_interface: Optional["GEEInterface"] = None,
        **kwargs,
    ) -> None:
        r"""Versatile card object to deal with the aoi selection.

        multiple selection method are available (see the MethodSelector object) and the widget can be fully customizable. Can also be bound to ee (ee==True) or not (ee==False).

        Args:
            methods: the methods to use in the widget, default to 'ALL'. Available: {'ADMIN0', 'ADMIN1', 'ADMIN2', 'SHAPE', 'DRAW', 'POINTS', 'ASSET', 'ALL'}
            map\_: link the aoi_view to a custom SepalMap to display the output, default to None
            gee: whether to bind to ee or not
            vector: the path to the default vector object
            admin: the administrative code of the default selection. Need to be GADM if :code:`ee==False` and GAUL 2015 if :code:`ee==True`.
            asset: the default asset. Can only work if :code:`ee==True`
            map_style: the predefined style of the aoi. It's by default using a "success" ``pysepal.color`` with 0.5 transparent fill color. It can be completely replace by a fully qualified `style dictionary <https://ipyleaflet.readthedocs.io/en/latest/layers/geo_json.html>`__. Use the ``pysepal.color`` object to define any color to remain compatible with light and dark theme.
            gee_session: the Earth Engine session to use (deprecated in favor of gee_interface)
            gee_interface: a shared GEEInterface instance. If provided, takes precedence over gee_session

        Raises:
            ValueError: if both gee_session and gee_interface are provided

        .. versionadded:: 3.0.0
            Added gee_interface parameter for sharing GEEInterface instances across components.
        """
        # Validate input parameters
        if gee_session and gee_interface:
            raise ValueError(
                "Cannot provide both gee_session and gee_interface. "
                "Use gee_interface for shared instances or gee_session for component-specific sessions."
            )

        # set ee dependency
        self.gee = gee
        self.folder = folder
        if gee is True:
            su.init_ee()

        # get the model
        self.model = model or AoiModel(
            gee=gee, folder=folder, gee_session=gee_session, gee_interface=gee_interface, **kwargs
        )

        # get the map if filled
        self.map_ = map_

        # get the aoi geoJSON style
        self.map_style = map_style

        # create the method widget
        self.w_method = MethodSelect(methods, gee=gee, map_=map_)

        # add the methods blocks
        self.w_admin_0 = AdminField(0, gee=gee).get_items()
        self.w_admin_1 = AdminField(1, self.w_admin_0, gee=gee)
        self.w_admin_2 = AdminField(2, self.w_admin_1, gee=gee)
        self.w_vector = sw.VectorField(
            label=msg("aoi_sel.vector"), gee_session=gee_session, gee_interface=gee_interface
        )
        self.w_points = sw.LoadTableField(label=msg("aoi_sel.points"))

        # group them together with the same key as the select_method object
        self.components = {
            "ADMIN0": self.w_admin_0,
            "ADMIN1": self.w_admin_1,
            "ADMIN2": self.w_admin_2,
            "SHAPE": self.w_vector,
            "POINTS": self.w_points,
        }

        # hide them all
        [c.hide() for c in self.components.values()]

        # use the same alert as in the model
        self.alert = sw.Alert()

        # bind the widgets to the model
        (
            self.model.bind(self.w_admin_0, "admin")
            .bind(self.w_admin_1, "admin")
            .bind(self.w_admin_2, "admin")
            .bind(self.w_vector, "vector_json")
            .bind(self.w_points, "point_json")
            .bind(self.w_method, "method")
        )

        # define the asset select separately. If no gee is set up we don't want any
        # gee based widget to be requested. If it's the case, application that does not support GEE
        # will crash if the user didn't authenticate
        if self.gee:
            self.w_asset = sw.VectorField(
                label=msg("aoi_sel.asset"),
                gee=True,
                folder=self.folder,
                types=["TABLE"],
                gee_session=gee_session,
                gee_interface=gee_interface,
            )
            self.w_asset.hide()
            self.components["ASSET"] = self.w_asset
            self.model.bind(self.w_asset, "asset_json")

        # define DRAW option separately as it will only work if the map is set
        if self.map_:
            self.w_draw = sw.TextField(label=msg("aoi_sel.aoi_name")).hide()
            self.components["DRAW"] = self.w_draw
            self.model.bind(self.w_draw, "name")
            self.aoi_dc = sm.DrawControl(self.map_)
            self.aoi_dc.hide()

        # add a validation btn
        self.btn = sw.Btn(msg=msg("aoi_sel.btn"))

        # create the widget
        self.children = [self.w_method] + [*self.components.values()] + [self.btn, self.alert]

        super().__init__(**kwargs)

        # js events
        self.w_method.observe(self._activate, "v_model")  # activate widgets
        self.btn.on_event("click", self._update_aoi)  # load the information

        # reset the aoi_model
        self.model.clear_attributes()

    @sd.loading_button()
    def _update_aoi(self, *args) -> Self:
        """Load the object in the model & update the map (if possible)."""
        # read the information from the geojson data
        if self.map_:
            self.model.geo_json = self.aoi_dc.to_json()

        # update the model
        self.model.set_object()
        self.alert.add_msg(msg("aoi_sel.complete"), "success")

        # update the map
        if self.map_:
            self.map_.remove_layer("aoi", none_ok=True)
            self.map_.zoom_bounds(self.model.total_bounds())

            if self.gee:
                self.map_.add_ee_layer(self.model.feature_collection, {}, "aoi")
            else:
                self.map_.add_layer(self.model.get_ipygeojson(self.map_style), "aoi")

            self.aoi_dc.hide()

        # tell the rest of the apps that the aoi have been updated
        self.updated += 1

        return self

    def reset(self) -> Self:
        """Clear the aoi_model from input and remove the layer from the map (if existing)."""
        # reset the view of the widgets
        self.w_method.v_model = None

        # clear the map
        if self.map_ is not None:
            self.map_.remove_layer("aoi", none_ok=True)

        return self

    @sd.switch("loading", on_widgets=["w_method"])
    def _activate(self, change: dict) -> None:
        """Activate the adapted widgets."""
        # clear and hide the alert
        self.alert.reset()

        # hide the widget so that the user doesn't see status changes
        [w.hide() for w in self.components.values()]

        # clear the inputs in a second step as resetting a FileInput can be long
        [w.reset() for w in self.components.values()]

        # deactivate or activate the dc
        # clear the geo_json saved features to start from scratch
        if self.map_:
            if change["new"] == "DRAW":
                self.aoi_dc.show()
            else:
                self.aoi_dc.hide()

            # init the name to the current value
            now = dt.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.w_draw.v_model = None if change["new"] is None else f"Manual_aoi_{now}"

        # activate the correct widget
        w = next((w for k, w in self.components.items() if k == change["new"]), None)
        w is None or w.show()

        return
