"""Model object dedicated to AOI selection."""

import json
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple, Union

import ee
import geopandas as gpd
import pandas as pd
import pygadm
import pygaul
import traitlets as t
from eeclient.client import EESession
from ipyleaflet import GeoJSON
from typing_extensions import Self

from pysepal import color
from pysepal.frontend import styles as ss
from pysepal.message import msg
from pysepal.model import Model
from pysepal.scripts import utils as su
from pysepal.scripts.gee_interface import GEEInterface

__all__ = ["AoiModel"]


class AoiModel(Model):

    # ###########################################################################
    # ###                      dataset const                                  ###
    # ###########################################################################

    MAPPING: Path = Path(__file__).parents[1] / "data" / "gaul_iso.json"
    "GAUL -> ISO-3 mapping of country code"

    ASSET_SUFFIX: str = "aoi_"
    "The suffix to identify the asset in GEE"

    # ###########################################################################
    # ###                             const methods                           ###
    # ###########################################################################

    CUSTOM: str = "custom"
    "Identifier of the custom-geometry method group"

    ADMIN: str = "admin"
    "Identifier of the administrative method group"

    METHODS: Dict[str, Dict[str, str]] = {
        "ADMIN0": {"label_key": "aoi_sel.adm.0", "type": ADMIN},
        "ADMIN1": {"label_key": "aoi_sel.adm.1", "type": ADMIN},
        "ADMIN2": {"label_key": "aoi_sel.adm.2", "type": ADMIN},
        "SHAPE": {"label_key": "aoi_sel.vector", "type": CUSTOM},
        "DRAW": {"label_key": "aoi_sel.draw", "type": CUSTOM},
        "POINTS": {"label_key": "aoi_sel.points", "type": CUSTOM},
        "ASSET": {"label_key": "aoi_sel.asset", "type": CUSTOM},
    }
    """Every selection method, as stable identifiers.

    ``label_key`` is a catalogue key, not a label: the caller renders it with
    ``msg()`` so the text follows the locale. ``type`` groups the methods and
    is compared in code, which is why it is a code and not a translated word.
    """

    TYPE_LABEL_KEYS: Dict[str, str] = {ADMIN: "aoi_sel.administrative", CUSTOM: "aoi_sel.custom"}
    "Catalogue key for each group heading"

    # ###########################################################################
    # ###                      widget related traitlets                       ###
    # ###########################################################################

    method: t.Unicode = t.Unicode(None, allow_none=True).tag(sync=True)
    "str: the currently selected method"

    point_json: t.Dict = t.Dict(None, allow_none=True).tag(sync=True)
    "dict: information that will be use to transform the csv into a gdf"

    vector_json: t.Dict = t.Dict(None, allow_none=True).tag(sync=True)
    "dict: information that will be use to transform the vector file into a gdf"

    geo_json: t.Dict = t.Dict(None, allow_none=True).tag(sync=True)
    "dict: the drawn geojson shape"

    admin: t.Unicode = t.Unicode(None, allow_none=True).tag(sync=True)
    "The admin number selected"

    asset_name: t.Unicode = t.Unicode(None, allow_none=True).tag(sync=True)
    "The asset name (only for GEE model)"

    asset_json: t.Dict = t.Dict(None, allow_none=True).tag(sync=True)
    "The asset json description (only for GEE model)"

    name: t.Unicode = t.Unicode(None, allow_none=True).tag(sync=True)
    "The name of the file to create (used only in drawn shaped)"

    object_set: t.Int = t.Int(0).tag(sync=True)
    "An integer that is incremented each time the object is set.."

    # ###########################################################################
    # ###                           model parameters                          ###
    # ###########################################################################

    gee: bool = True
    "either or not the model is bound to gee"

    folder: Union[str, Path] = ""
    "The folder name used in GEE related component, mainly used for debugging"

    default_vector: Optional[Union[str, Path]] = None
    "The default vector file that will be used to produce the gdf. need to be readable by fiona and/or GDAL/OGR"

    default_admin: Optional[str] = None
    "The default administrative area in GADM or GAUL norm"

    default_asset: Optional[str] = None
    "The default asset name, need to point to a readable FeatureCollection"

    # ###########################################################################
    # ###                           model outputs                             ###
    # ###########################################################################

    dst_asset_id: str = ""
    "The exported asset id"

    selected_feature: Optional[Union[ee.Feature, gpd.GeoDataFrame]] = None
    "The Feature associated with a query"

    gdf: Optional[gpd.GeoDataFrame] = None
    "The geodataframe corresponding to the selected AOI"

    feature_collection: Optional[ee.FeatureCollection] = None
    "The feature Collection generated by the parameters (only for GEE models)"

    ipygeojson: Optional[GeoJSON] = None
    "The representation of the AOI as a ipyleaflet layer"

    def __init__(
        self,
        gee: bool = True,
        vector: Optional[Union[str, Path]] = None,
        asset: Optional[Union[str, Path]] = None,
        admin: Optional[str] = None,
        folder: Union[str, Path] = "",
        gee_session: Optional[EESession] = None,
        gee_interface: Optional[GEEInterface] = None,
    ) -> None:
        """An Model object dedicated to the sorage and the manipulation of aoi.

        It is meant to be used with the AoiView object (embedded in the AoiTile).
        By using this you will be able to provide your application with aoi as an ee_object
        or a gdf, depending if you activated the ee binding or not.
        The class also provide insight on your aoi geometry.

        Args:
            gee: whether or not the aoi selector should be using the EarthEngine binding
            vector: the path to the default vector object
            admin: the administrative code of the default selection. Need to be GADM if ee==False and GAUL 2015 if ee==True.
            asset: the default asset. Can only work if ee==True
            folder: the init GEE asset folder where the asset selector should start looking (debugging purpose)
            gee_session: the Earth Engine session to use for the GEE binding (deprecated in favor of gee_interface)
            gee_interface: a shared GEEInterface instance. If provided, takes precedence over gee_session

        Raises:
            ValueError: if both gee_session and gee_interface are provided

        .. deprecated:: 2.3.2
            'asset_name' will be used as variable to store 'ASSET' method info. To get the destination saved asset id, please use 'dst_asset_id' variable.

        .. versionadded:: 3.0.0
            Added gee_interface parameter for sharing GEEInterface instances across components.
        """
        super().__init__()

        if gee_session and gee_interface:
            raise ValueError(
                "Cannot provide both gee_session and gee_interface. "
                "Use gee_interface for shared instances or gee_session for component-specific sessions."
            )

        # the ee retated information
        self.gee = gee
        if gee:
            # Resolve the interface first: it refuses a session-less one in a
            # per-connection runtime, and init_ee() would already have bound the
            # global ee to the container's credentials by the time it raised.
            if gee_interface:
                self.gee_interface = gee_interface
            else:
                self.gee_interface = GEEInterface(gee_session)
            su.init_ee()
            self.folder = str(folder) if folder else self.gee_interface.get_folder()

        # set default values
        self.set_default(vector, admin, asset)

    def set_default(
        self,
        vector: Optional[Union[str, Path]] = None,
        admin: Optional[str] = None,
        asset: Optional[Union[str, Path]] = None,
    ) -> Self:
        """Set the default value of the object and create a gdf/feature_collection out of it.

        Args:
            vector: the default vector file that will be used to produce the gdf. need to be readable by fiona and/or GDAL/OGR
            admin: the default administrative area in GADM or GAUL norm
            asset: the default asset name, need to point to a readable FeatureCollection
        """
        # save the default values
        self.default_vector = vector
        self.default_asset = self.asset_name = str(asset) if asset else None
        self.asset_json = {"pathname": asset, "column": "ALL", "value": None} if asset else None
        self.default_admin = self.admin = admin

        # cast the vector to json
        self.vector_json = (
            {"pathname": str(vector), "column": "ALL", "value": None} if vector else None
        )

        # cast the asset to json
        self.asset_json = {"pathname": asset, "column": "ALL", "value": None} if asset else None

        # set the default gdf if possible
        if self.vector_json is not None:
            self.set_object("SHAPE")
        elif self.admin:
            self.set_object("ADMIN0")  # any level will work
        elif self.asset_json is not None:
            self.set_object("ASSET")

        return self

    def set_object(self, method: str = "") -> Self:
        """Set the object (gdf/featurecollection) based on the model inputs.

        The method can be manually overwritten by setting the ``method`` parameter.

        Args:
            method: a model loading method
        """
        # clear the model output if existing
        self.clear_output()

        # overwrite self.method
        self.method = method or self.method

        if self.method in ["ADMIN0", "ADMIN1", "ADMIN2"]:
            self._from_admin(self.admin)
        elif self.method == "POINTS":
            self._from_points(self.point_json)
        elif self.method == "SHAPE":
            self._from_vector(self.vector_json)
        elif self.method == "DRAW":
            self._from_geo_json(self.geo_json)
        elif self.method == "ASSET":
            self._from_asset(self.asset_json)
        else:
            raise Exception(msg("aoi_sel.exception.no_inputs"))

        self.object_set += 1

        return self

    def _from_asset(self, asset_json: dict) -> Self:
        """Set the ee.FeatureCollection output from an existing asset."""
        if not (asset_json["pathname"]):
            raise Exception(msg("aoi_sel.exception.no_asset"))

        if asset_json["column"] != "ALL":
            if asset_json["value"] is None:
                raise Exception(msg("aoi_sel.exception.no_value"))

        # set the name
        self.name = Path(asset_json["pathname"]).stem.replace(self.ASSET_SUFFIX, "")
        self.asset_name = asset_json["pathname"]
        ee_col = ee.FeatureCollection(asset_json["pathname"])

        if asset_json["column"] != "ALL":

            column = asset_json["column"]
            value = asset_json["value"]
            ee_col = ee_col.filterMetadata(column, "equals", value)
            self.name = f"{self.name}_{column}_{value}"

        # set the feature collection
        self.feature_collection = ee_col

        return self

    def _from_points(self, point_json: dict) -> Self:
        """Set the object output from a csv json.

        Args:
            point_json: the geo_interface description of the points
        """
        if not all(point_json.values()):
            raise Exception(msg("aoi_sel.exception.incomplete"))

        # cast the pathname to pathlib Path
        point_file = Path(point_json["pathname"])

        # check that the columns are well set
        values = [v for v in point_json.values()]
        if not len(values) == len(set(values)):
            raise Exception(msg("aoi_sel.exception.duplicate_key"))

        # create the gdf
        df = pd.read_csv(point_file, sep=None, engine="python")
        self.gdf = gpd.GeoDataFrame(
            df,
            crs="EPSG:4326",
            geometry=gpd.points_from_xy(df[point_json["lng_column"]], df[point_json["lat_column"]]),
        )

        # set the name
        self.name = point_file.stem

        if self.gee:
            # transform the gdf to ee.FeatureCollection
            self.feature_collection = ee.FeatureCollection(self.gdf.__geo_interface__)

            # export as a GEE asset
            self.export_to_asset()

        return self

    def _from_vector(self, vector_json: dict) -> Self:
        """Set the object output from a vector json.

        Args:
            vector_json: the dict describing the vector file, and column filter
        """
        if not (vector_json["pathname"]):
            raise Exception(msg("aoi_sel.exception.no_file"))

        if vector_json["column"] != "ALL":
            if vector_json["value"] is None:
                raise Exception(msg("aoi_sel.exception.no_value"))

        # cast the pathname to pathlib Path
        vector_file = Path(vector_json["pathname"])

        # create the gdf
        self.gdf = gpd.read_file(vector_file).to_crs("EPSG:4326")

        # set the name using the file stem
        self.name = vector_file.stem

        # filter it if necessary
        if vector_json["value"] is not None:
            self.gdf = self.gdf[self.gdf[vector_json["column"]] == vector_json["value"]]
            self.name = f"{self.name}_{vector_json['column']}_{vector_json['value']}"

        if self.gee:
            # transform the gdf to ee.FeatureCollection
            self.feature_collection = su.geojson_to_ee(self.gdf.__geo_interface__)

            # export as a GEE asset
            self.export_to_asset()

        return self

    def _from_geo_json(self, geo_json: dict) -> Self:
        """Set the gdf output from a geo_json.

        Args:
            geo_json: the __geo_interface__ dict of a geometry drawn on the map
        """
        if not geo_json:
            raise Exception(msg("aoi_sel.exception.no_draw"))

        # remove the style property from geojson as it's not recognize by geopandas and gee
        for feat in geo_json["features"]:
            if "style" in feat["properties"]:
                del feat["properties"]["style"]

        # create the gdf
        self.gdf = gpd.GeoDataFrame.from_features(geo_json).set_crs(epsg=4326)

        # normalize the name
        self.name = su.normalize_str(self.name)

        if self.gee:
            # transform the gdf to ee.FeatureCollection
            self.feature_collection = su.geojson_to_ee(self.gdf.__geo_interface__)

            # export as a GEE asset
            self.export_to_asset()
        else:
            # save the geojson in downloads
            path = Path("~", "downloads", "aoi").expanduser()
            path.mkdir(
                exist_ok=True, parents=True
            )  # if nothing have been run the downloads folder doesn't exist
            self.gdf.to_file(path / f"{self.name}.geojson", driver="GeoJSON")

        return self

    def _from_admin(self, admin: str) -> Self:
        """Set the object according to the given an administrative code in the GADM/GAUL codes.

        Args:
            admin: the admin code corresponding to FAO GAUL (if gee) or GADM
        """
        if not admin:
            raise Exception(msg("aoi_sel.exception.no_admlyr"))

        # get the data from either the pygaul or the pygadm libs
        if self.gee:
            self.feature_collection = pygaul.Items(admin=admin)

            # get the iso3_code directly from GAUL 2024 dataset
            feature = self.feature_collection.first()
            properties = self.gee_interface.get_info(feature.toDictionary(feature.propertyNames()))

            # GAUL 2024 includes iso3_code directly, fallback to mapping for disputed areas
            iso = properties.get("iso3_code", "")
            if not iso or (
                isinstance(iso, str) and iso.startswith("x")
            ):  # 'x' prefix means disputed/unknown
                gaul0_code = str(properties.get("gaul0_code", ""))
                iso = json.loads(self.MAPPING.read_text()).get(gaul0_code, "UNK")

            # GAUL 2024 uses lowercase column names: gaul0_name, gaul1_name, gaul2_name
            names = [value for prop, value in properties.items() if "_name" in prop]

            # generate the name from the columns
            names = [su.normalize_str(name) for name in names]
            names[0] = iso

            self.name = "_".join(names)

        else:
            self.gdf = pygadm.Items(admin=admin)

            # generate the name from the columns
            r = self.gdf.iloc[0]
            names = [su.normalize_str(r[c]) for c in self.gdf.columns if "NAME" in c]
            names[0] = r.GID_0[:3]
            self.name = "_".join(names)
        return self

    def clear_output(self) -> Self:
        """Clear the output of the aoi selector without changing the traits and/or the parameters."""
        # reset the outputs
        self.gdf = None
        self.feature_collection = None
        self.ipygeojson = None
        self.selected_feature = None
        self.dst_asset_id = None

        return self

    def clear_attributes(self) -> Self:
        """Return all attributes to their default state.

        Note:
            Set the default setting as current object.
        """
        # keep the default
        admin = self.default_admin
        vector = self.default_vector
        asset = self.default_asset

        # delete all the traits
        [setattr(self, attr, None) for attr in self.trait_names() if attr not in ["object_set"]]

        # reset the outputs
        self.clear_output()

        # reset the default
        self.set_default(vector, admin, asset)

        return self

    def get_columns(self) -> List[str]:
        """Retrieve the columns or variables from self excluding geometries and gee index.

        Returns:
            sorted list of column names
        """
        if self._gdf is None and not self.feature_collection:
            raise Exception(msg("aoi_sel.exception.no_gdf"))

        if self.gee:
            aoi_ee = ee.Feature(self.feature_collection.first())
            columns = self.gee_interface.get_info(aoi_ee.propertyNames())
            list_ = [col for col in columns if col not in ["system:index", "Shape_Area"]]
        else:
            list_ = list(set(["geometry"]) ^ set(self.gdf.columns.to_list()))

        return sorted(list_)

    def get_fields(self, column: str) -> List[str]:
        """Retrieve the fields from a column.

        Args:
            A column name to query over the asset

        Returns:
            sorted list of fields value

        """
        if self._gdf is None and not self.feature_collection:
            raise Exception(msg("aoi_sel.exception.no_gdf"))

        if self.gee:
            fields = self.feature_collection.distinct(column).aggregate_array(column)
            list_ = self.gee_interface.get_info(fields)
        else:
            list_ = self.gdf[column].to_list()

        return sorted(list_)

    def get_selected(self, column: str, field: str) -> Union[ee.Feature, gpd.GeoDataFrame]:
        """Select an ee object based on selected column and field.

        Args:
            column: the selected column in the dataset
            field: the value to search in the selected column

        Returns:
            The Feature associated with the query
        """
        if self._gdf is None and not self.feature_collection:
            raise Exception(msg("aoi_sel.exception.no_gdf"))

        if self.gee:
            selected_feature = self.feature_collection.filterMetadata(column, "equals", field)
        else:
            selected_feature = self.gdf[self.gdf[column] == field]

        return selected_feature

    def total_bounds(self) -> Tuple[float, float, float, float]:
        """Reproduce the behaviour of the total_bounds method from geopandas.

        Returns:
            minxx, miny, maxx, maxy
        """
        # use _gdf to evaluate the condition to avoid accessing the gdf property
        if self._gdf is None and not self.feature_collection:
            raise ValueError(msg("aoi_sel.exception.no_gdf"))

        if self.gee:
            bounds = list(self.gee_interface.get_bounds(self.feature_collection))
        else:
            bounds = self.gdf.total_bounds.tolist()

        return [round(bound, 4) for bound in bounds]

    def export_to_asset(self) -> Self:
        """Export the feature_collection as an asset (only for ee model)."""
        asset_name = self.ASSET_SUFFIX + self.name
        asset_id = str(PurePosixPath(self.folder, asset_name))

        self.dst_asset_id = asset_id

        # check if the table already exist
        if self.gee_interface.get_asset(asset_id, not_exists_ok=True):
            return self

        # check if the task is running
        if self.gee_interface.is_running(asset_name):
            return self

        # run the task
        task_config = {
            "collection": self.feature_collection,
            "description": asset_name,
            "asset_id": asset_id,
        }

        self.gee_interface.export_table_to_asset(**task_config)

        return self

    async def export_to_asset_async(self) -> Self:
        """Export the feature_collection as an asset (only for ee model)."""
        asset_name = self.ASSET_SUFFIX + self.name
        asset_id = str(PurePosixPath(self.folder, asset_name))

        self.dst_asset_id = asset_id

        # check if the table already exist
        if self.gee_interface.get_asset(asset_id, not_exists_ok=True):
            return self

        # check if the task is running
        if self.gee_interface.is_running(asset_name):
            return self

        # run the task
        task_config = {
            "collection": self.feature_collection,
            "description": asset_name,
            "asset_id": asset_id,
        }

        await self.gee_interface.export_table_to_asset_async(**task_config)

    def get_ipygeojson(self, style: Optional[dict] = None) -> GeoJSON:
        """Converts current geopandas object into ipyleaflet GeoJSON.

        Args:
            style: the predefined style of the aoi. It's by default using a "success" ``pysepal.color`` with 0.5 transparent fill color. It can be completely replace by a fully qualified `style dictionary <https://ipyleaflet.readthedocs.io/en/latest/layers/geo_json.html>`__. Use the ``pysepal.color`` object to define any color to remain compatible with light and dark theme.

        Returns:
            The geojson layer of the aoi gdf, ready to use in a Map
        """
        # This function aims to work in the same way in both gee and non-gee mode
        # It's why we use the gdf property to evaluate the condition
        if self.gdf is None:
            raise Exception(msg("aoi_sel.exception.no_gdf"))

        # read the data from geojson and add the name as a property of the shape
        # useful when handler are added from ipyleaflet
        # Convert to regular GeoDataFrame to avoid issues with pygadm subclasses
        # This is necessary because pygadm 0.5.3 has a bug with pandas 2.3+ where
        # the __init__ method contains a DataFrame comparison that fails during
        # geopandas' internal to_json() process. Converting to plain GeoDataFrame
        # first avoids triggering the buggy pygadm constructor.
        # See: https://github.com/12rambau/pygadm/issues/81
        gdf = gpd.GeoDataFrame(self.gdf)
        data = json.loads(gdf.to_json())
        for f in data["features"]:
            f["properties"]["name"] = self.name

        # adapt the style to the theme
        if style is None:
            style = json.loads((ss.JSON_DIR / "aoi.json").read_text())
            style.update(color=color.primary, fillColor=color.primary)

        # create a GeoJSON object
        # attribution="SEPAL(c)" is not recognized yet
        # https://github.com/jupyter-widgets/ipyleaflet/issues/847
        self.ipygeojson = GeoJSON(data=data, style=style, name="aoi")

        return self.ipygeojson

    @property
    def gdf(self):
        """Get the geodataframe associated with the AOI."""
        if self.gee:
            if self._gdf is not None:
                # This happens when it comes from vector or geojson
                return self._gdf

            if not self.feature_collection:
                return None

            self._load_gdf()

        return self._gdf

    @gdf.setter
    def gdf(self, value):
        """Set the gdf value. Used mainly to reset the gdf value."""
        self._gdf = value

    def _load_gdf(self):
        """Return a geodataframe from a feature collection."""
        features = self.gee_interface.get_info(self.feature_collection)["features"]
        self._gdf = gpd.GeoDataFrame.from_features(features).set_crs(epsg=4326)

        if self.method in ["ADMIN0", "ADMIN1", "ADMIN2"]:
            # GAUL 2024 includes iso3_code directly, fallback to mapping for disputed areas
            iso = self._gdf.iso3_code.unique()[0] if "iso3_code" in self._gdf.columns else None
            if not iso or (isinstance(iso, str) and iso.startswith("x")):
                gaul_country = str(self._gdf.gaul0_code.unique()[0])
                iso = json.loads(self.MAPPING.read_text()).get(gaul_country, "UNK")
            self._gdf["ISO"] = iso
