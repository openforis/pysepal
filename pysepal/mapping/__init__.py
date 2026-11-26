"""All modules used to create a application ``Map``.

The ``SepalMap`` is a **MapLibre** map, the ``MapWidget`` of ``pysepal_map``. It draws the layers of a ``LayerStore`` (``SepalMap.layer_store``) and follows the **pysepal** theme.

The main object is the ``SepalMap``. Its layer methods return a live ``LayerHandle``.
``SepalMap`` is fully compatible with Google Earth Engine layers.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import mapping as sm

        sm.SepalMap(gee=False)
"""

from pysepal_map import Side as Side

from pysepal import _removed

from .handle import LayerGoneError as LayerGoneError
from .handle import LayerHandle as LayerHandle
from .handle import ZoomResult as ZoomResult
from .inspector import *
from .map_btn import *
from .sepal_map import *
from .tiling import *
from .visualization import *

_DRAW = "m.draw.begin(modes) and the DrawSession it returns"
_INSPECTOR = "SepalMap(inspector=True) shown in a MapView"
_CONTROLS = "the zoom, scale and fullscreen controls the map draws itself"
_EE_LAYER = "m.add_ee_layer(...) or a LayerSpec, and the LayerHandle it returns"
_GEOJSON = "LayerSpec.from_geojson or LayerSpec.from_vector with a VectorStyle"

# What replaced each removed name or module, by the change that removed it.
__getattr__ = _removed.removed(
    __name__,
    {
        "the ipyvuetify 1 widget layer": {
            "AoiControl": "pysepal.solara.components.aoi.AoiView",
            "aoi_control": "pysepal.solara.components.aoi.AoiView",
            "LayersControl": "SepalMap.layer_store with the Solara LayerPanel",
            "layers_control": "SepalMap.layer_store with the Solara LayerPanel",
        },
        "the move to MapLibre": {
            "DrawControl": _DRAW,
            "GeomanDrawControl": _DRAW,
            "draw_control": _DRAW,
            "InspectorControl": _INSPECTOR,
            "ValueInspector": _INSPECTOR,
            "inspector_control": _INSPECTOR,
            "ZoomControl": _CONTROLS,
            "zoom_control": _CONTROLS,
            "FullScreenControl": _CONTROLS,
            "fullscreen_control": _CONTROLS,
            "LayerStateControl": "the layer loading state MapView shows",
            "layer_state_control": "the layer loading state MapView shows",
            "MenuControl": "Solara components in MapView(overlays=...)",
            "menu_control": "Solara components in MapView(overlays=...)",
            "LegendControl": "the MapView legend, built from each layer's legend",
            "legend_control": "the MapView legend, built from each layer's legend",
            "EELayer": _EE_LAYER,
            "layer": _EE_LAYER,
            "MarkerCluster": "LayerSpec.from_points(...) with VectorStyle(cluster=True)",
            "marker_cluster": "LayerSpec.from_points(...) with VectorStyle(cluster=True)",
            "get_ipygeojson": _GEOJSON,
            "geojson_utils": _GEOJSON,
        },
    },
)
