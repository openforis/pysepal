"""UI toolkit for building ipyvuetify and Solara dashboards, with first-class SEPAL integration.

``pysepal`` provides ipyvuetify and Solara components for building geospatial dashboards — mapping (ipyleaflet), AOI selection, GEE session helpers, notifications, exports, i18n, and theme state — usable in any Jupyter / Solara context and tightly integrated with the SEPAL platform.
"""

from pysepal.frontend.styles import SepalColor

__author__ = """Pierrick Rambaud"""
__email__ = "pierrick.rambaud49@gmail.com"
__version__ = "4.1.0"

color = SepalColor()
'color: the colors of sepal. members are in the following list: "main, darker, bg, primary, accent, secondary, success, info, warning, error, menu". They will render according to the selected theme.'
