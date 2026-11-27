"""All modules used to create AOI selection interface.

Package to access all the widget, model and tiles to create an AOI selection interface available in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import aoi

        aoi.AoiModel(gee=False)
"""

from pysepal import _removed

from .aoi_model import *

# Widgets removed in 5.0 with sepalwidgets, and what replaces them.
__getattr__ = _removed.removed(
    __name__,
    {
        "the ipyvuetify 1 widget layer": {
            "AoiTile": "pysepal.solara.components.aoi.AoiView",
            "AoiView": "pysepal.solara.components.aoi.AoiView",
            "select_methods": "the methods argument of pysepal.solara.components.aoi.AoiView",
        },
    },
)
