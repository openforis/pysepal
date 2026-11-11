"""All modules used to create an Planet interface.

Package to access all the widget, model and tiles to create an Planet interface in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import planetapi

        planetapi.PlanetView()
"""

import importlib

from .planet_model import *

# The widgets need the deprecated sepalwidgets package (ipyvuetify 1 only), so
# they load on first use and the model imports on both ipyvuetify majors.
_WIDGETS = {
    "PlanetView": ".planet_view",
    "InfoView": ".planet_widgets",
    "InfoCard": ".planet_widgets",
}


def __getattr__(name: str):
    if name in _WIDGETS:
        return getattr(importlib.import_module(_WIDGETS[name], __name__), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted([*globals(), *_WIDGETS])
