"""All modules used to create a application ``Map``.

The ``SepalMap`` is inheriting from the **ipyleaflet** ``Map``. It has been customized to support additional widgets as controls based on **ipyvuetify**. It is also fully compatible with the **pysepal** framework thanks to frontend modifications.

The main object is the ``SepalMap`` that should be used in favor of ``Map`` in **pysepal** framework. The others are pre-designed controls that can be helpful to speed up developments.
``SepalMap`` is fully compatible with Google Earth Engine layers.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import mapping as sm

        sm.SepalMap(gee=False)
"""

from .geojson_utils import *
from .handle import LayerGoneError as LayerGoneError
from .handle import LayerHandle as LayerHandle
from .handle import ZoomResult as ZoomResult
from .layer import *
from .map_btn import *
from .marker_cluster import *
from .sepal_map import *
from .tiling import *
from .visualization import *

_REMOVED = {
    "AoiControl": "pysepal.solara.components.aoi.AoiView",
    "aoi_control": "pysepal.solara.components.aoi.AoiView",
    "LayersControl": "SepalMap.layer_store with the Solara LayerPanel",
    "DrawControl": "the draw tools being rebuilt on the MapLibre map",
    "GeomanDrawControl": "the draw tools being rebuilt on the MapLibre map",
    "InspectorControl": "the value inspector being rebuilt on the MapLibre map",
    "ValueInspector": "the value inspector being rebuilt on the MapLibre map",
    "ZoomControl": "the zoom, scale and fullscreen controls the map draws itself",
    "FullScreenControl": "the zoom, scale and fullscreen controls the map draws itself",
    "LayerStateControl": "the layer loading state MapView shows",
    "MenuControl": "Solara components in MapView(overlays=...)",
    "LegendControl": "the MapView legend, built from each layer's legend",
}


def __getattr__(name: str):
    if name in _REMOVED:
        raise AttributeError(
            f"{__name__}.{name} was removed in pysepal 5.0 with the ipyvuetify 1 widget layer; "
            f'use {_REMOVED[name]} or pin "pysepal<5". '
            "See docs/guides/migrating-to-pysepal-5.md"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
