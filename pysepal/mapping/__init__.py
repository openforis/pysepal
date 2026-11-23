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

from .handle import LayerGoneError as LayerGoneError
from .handle import LayerHandle as LayerHandle
from .handle import ZoomResult as ZoomResult
from .inspector import *
from .map_btn import *
from .sepal_map import *
from .tiling import *
from .visualization import *

# What replaced each removed name, by the change that removed it.
_REMOVED = {
    "the ipyvuetify 1 widget layer": {
        "AoiControl": "pysepal.solara.components.aoi.AoiView",
        "aoi_control": "pysepal.solara.components.aoi.AoiView",
        "LayersControl": "SepalMap.layer_store with the Solara LayerPanel",
    },
    "the move to MapLibre": {
        "DrawControl": "m.draw.begin(modes) and the DrawSession it returns",
        "GeomanDrawControl": "m.draw.begin(modes) and the DrawSession it returns",
        "InspectorControl": "SepalMap(inspector=True) shown in a MapView",
        "ValueInspector": "SepalMap(inspector=True) shown in a MapView",
        "ZoomControl": "the zoom, scale and fullscreen controls the map draws itself",
        "FullScreenControl": "the zoom, scale and fullscreen controls the map draws itself",
        "LayerStateControl": "the layer loading state MapView shows",
        "MenuControl": "Solara components in MapView(overlays=...)",
        "LegendControl": "the MapView legend, built from each layer's legend",
        "EELayer": "m.add_ee_layer(...) or a LayerSpec, and the LayerHandle it returns",
        "MarkerCluster": "LayerSpec.from_points(...) with VectorStyle(cluster=True)",
        "get_ipygeojson": "LayerSpec.from_geojson or LayerSpec.from_vector with a VectorStyle",
    },
}


def __getattr__(name: str):
    for cause, replacements in _REMOVED.items():
        if name in replacements:
            raise AttributeError(
                f"{__name__}.{name} was removed in pysepal 5.0 with {cause}; "
                f'use {replacements[name]} or pin "pysepal<5". '
                "See docs/guides/migrating-to-pysepal-5.md"
            )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
