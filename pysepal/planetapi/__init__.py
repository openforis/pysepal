"""All modules used to create an Planet interface.

Package to access all the widget, model and tiles to create an Planet interface in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import planetapi

        planetapi.PlanetModel()
"""

from pysepal import _removed

from .planet_model import *

_FORM = "pysepal.planetapi.PlanetModel with your own Solara form"

# Widgets removed in 5.0 with sepalwidgets, and what replaces them.
__getattr__ = _removed.removed(
    __name__,
    {"the ipyvuetify 1 widget layer": {"PlanetView": _FORM, "InfoView": _FORM, "InfoCard": _FORM}},
)
