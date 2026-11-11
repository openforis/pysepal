"""UI toolkit for building ipyvuetify and Solara dashboards, with first-class SEPAL integration.

``pysepal`` provides ipyvuetify and Solara components for building geospatial dashboards — mapping (ipyleaflet), AOI selection, GEE session helpers, notifications, exports, i18n, and theme state — usable in any Jupyter / Solara context and tightly integrated with the SEPAL platform.
"""

from pysepal.conf import config as config
from pysepal.conf import config_file as config_file
from pysepal.frontend.styles import SepalColor
from pysepal.frontend.styles import get_theme as get_theme

__author__ = """Pierrick Rambaud"""
__email__ = "pierrick.rambaud49@gmail.com"
__version__ = "3.8.4"

color = SepalColor()
'color: the colors of sepal. members are in the following list: "main, darker, bg, primary, accent, secondary, success, info, warning, error, menu". They will render according to the selected theme.'
