"""All modules used to create AOI selection interface.

Package to access all the widget, model and tiles to create an AOI selection interface available in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import aoi

        aoi.AoiTile(gee=False)
"""

import importlib

from .aoi_model import *

# The widgets need the deprecated sepalwidgets package (ipyvuetify 1 only), so
# they load on first use and the model imports on both ipyvuetify majors.
_WIDGETS = {"AoiTile": ".aoi_tile", "AoiView": ".aoi_view", "select_methods": ".aoi_view"}


def __getattr__(name: str):
    if name in _WIDGETS:
        return getattr(importlib.import_module(_WIDGETS[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted([*globals(), *_WIDGETS])
