"""All modules used to create an Planet interface.

Package to access all the widget, model and tiles to create an Planet interface in pysepal.

Every module content can be called directly from the package.

Example:
    .. jupyter-execute::

        from pysepal import planetapi

        planetapi.PlanetModel()
"""

from .planet_model import *

# Widgets removed in 5.0 with sepalwidgets, and what replaces them.
_REMOVED = {
    "PlanetView": "pysepal.planetapi.PlanetModel with your own Solara form",
    "InfoView": "pysepal.planetapi.PlanetModel with your own Solara form",
    "InfoCard": "pysepal.planetapi.PlanetModel with your own Solara form",
}


def __getattr__(name: str):
    if name in _REMOVED:
        raise AttributeError(
            f"{__name__}.{name} was removed in pysepal 5.0 with the ipyvuetify 1 widget layer; "
            f'use {_REMOVED[name]} or pin "pysepal<5". '
            "See docs/guides/migrating-to-pysepal-5.md"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
