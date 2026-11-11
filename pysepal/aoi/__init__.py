"""All modules used to create AOI selection interface.

Package to access all the widget, model and tiles to create an AOI selection interface available in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import aoi

        aoi.AoiModel(gee=False)
"""

from .aoi_model import *

# Widgets removed in 5.0 with sepalwidgets, and what replaces them.
_REMOVED = {
    "AoiTile": "pysepal.solara.components.aoi.AoiView",
    "AoiView": "pysepal.solara.components.aoi.AoiView",
    "select_methods": "the methods argument of pysepal.solara.components.aoi.AoiView",
}


def __getattr__(name: str):
    if name in _REMOVED:
        raise AttributeError(
            f"{__name__}.{name} was removed in pysepal 5.0 with the ipyvuetify 1 widget layer; "
            f'use {_REMOVED[name]} or pin "pysepal<5". '
            "See docs/guides/migrating-to-pysepal-5.md"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
