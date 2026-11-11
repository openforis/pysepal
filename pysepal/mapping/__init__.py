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

from .draw_control import *
from .fullscreen_control import *
from .geojson_utils import *
from .inspector_control import *
from .layer import *
from .layer_state_control import *
from .layers_control import *
from .legend_control import *
from .map_btn import *
from .marker_cluster import *
from .menu_control import *
from .sepal_map import *
from .tiling import *
from .visualization import *
from .zoom_control import *


def __getattr__(name: str):
    # AoiControl is built on the deprecated pysepal.sepalwidgets, imported on first use only
    if name in ("AoiControl", "aoi_control"):
        from importlib import import_module

        module = import_module(".aoi_control", __name__)
        return module if name == "aoi_control" else module.AoiControl
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
