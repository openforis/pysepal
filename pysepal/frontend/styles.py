"""Helpers to customize the display of sepal-ui widgets and maps."""

from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

import ipyvuetify as v
from IPython.display import HTML, Javascript, display
from ipyvuetify._version import semver
from ipywidgets import Widget
from traitlets import Bool, HasTraits, Unicode, link

import pysepal.scripts.utils as su

################################################################################
# access the folders where style information is stored (layers, widgets)
#

# the colors are set using tables as follow.
# 1 (True): dark theme
# 0 (false): light theme
JSON_DIR: Path = Path(__file__).parent / "json"
"The path to the json style folder"

CSS_DIR: Path = Path(__file__).parent / "css"
"The path to the css style folder"

JS_DIR: Path = Path(__file__).parent / "js"
"The path to the js style folder"

################################################################################
# define all the colors that we want to use in the theme
#


TYPES: Tuple[str, ...] = (
    "info",
    "primary",
    "primary_contarst",
    "secondary",
    "secondary_contrast",
    "accent",
    "error",
    "success",
    "warning",
    "anchor",
    "main",
    "darker",
    "bg",
    "menu",
)
"The different types defined by ipyvuetify"


class ThemeColors(Widget):

    _model_name = Unicode("ThemeColorsModel").tag(sync=True)

    _model_module = Unicode("jupyter-vuetify").tag(sync=True)

    _view_module_version = Unicode(semver).tag(sync=True)

    _model_module_version = Unicode(semver).tag(sync=True)

    _theme_name = Unicode().tag(sync=True)

    primary = Unicode().tag(sync=True)
    primary_contrast = Unicode().tag(sync=True)
    secondary = Unicode().tag(sync=True)
    secondary_contrast = Unicode().tag(sync=True)
    accent = Unicode().tag(sync=True)
    error = Unicode().tag(sync=True)
    info = Unicode().tag(sync=True)
    success = Unicode().tag(sync=True)
    warning = Unicode().tag(sync=True)
    anchor = Unicode(None, allow_none=True).tag(sync=True)
    main = Unicode().tag(sync=True)
    bg = Unicode().tag(sync=True)
    menu = Unicode().tag(sync=True)
    darker = Unicode().tag(sync=True)


dark_theme_colors = ThemeColors(
    _theme_name="dark",
    primary="#76591e",
    primary_contrast="#bf8f2d",  # a bit lighter than the primary color
    secondary="#363e4f",
    secondary_contrast="#5d76ab",
    error="#a63228",
    info="#c5c6c9",
    success="#3f802a",
    warning="#b8721d",
    accent="#272727",
    anchor="#f3f3f3",
    main="#24221f",
    darker="#1a1a1a",
    bg="#121212",
    menu="#424242",
)

light_theme_colors = ThemeColors(
    _theme_name="light",
    primary="#5BB624",
    primary_contrast="#76b353",
    accent="#f3f3f3",
    anchor="#f3f3f3",
    secondary="#2199C4",
    secondary_contrast="#5d76ab",
    success=v.theme.themes.light.success,
    info=v.theme.themes.light.info,
    warning=v.theme.themes.light.warning,
    error=v.theme.themes.light.error,
    main="#2196f3",  # used by appbar and versioncard
    darker="#ffffff",  # used for the navdrawer
    bg="#FFFFFF",
    menu="#FFFFFF",
)

DARK_THEME = {k: v for k, v in dark_theme_colors.__dict__["_trait_values"].items() if k in TYPES}
"colors used for the dark theme"

LIGHT_THEME = {k: v for k, v in light_theme_colors.__dict__["_trait_values"].items() if k in TYPES}
"colors used for the light theme"

THEMES = {True: DARK_THEME, False: LIGHT_THEME}
"colors of each theme, keyed by whether it is dark"


# override the default theme with the custom ones
v.theme.themes.light = light_theme_colors
v.theme.themes.dark = dark_theme_colors

################################################################################
# define classes and method to make the application responsive
#


class SepalColor(HasTraits, SimpleNamespace):

    _dark_theme: Bool = Bool(True).tag(sync=True)
    """Whether the dark theme is active.

    A constant default on purpose: this is a class-body trait, evaluated at
    import, and it used to be seeded from ``~/.sepal-ui-config`` -- a file
    shared by every connection in a multi-user container. The value still
    tracks ``ipyvuetify``'s live theme through the link below, but
    ``pysepal.color`` remains a single process-global object: whoever toggles
    last wins for every legacy ipyvuetify widget in the process.
    """

    def __init__(self) -> None:
        """Custom simple name space to store and access to the pysepal colors and with a magic method to display theme."""
        link((self, "_dark_theme"), (v.theme, "dark"))
        v.theme.observe(lambda *x: self.set_colors(), "dark")

        self.set_colors()

    def set_colors(self) -> None:
        """Set the current hexadecimal color in the object."""
        # Get get current theme name
        self.theme_name = "dark" if self._dark_theme else "light"

        self.colors_dict = DARK_THEME if self._dark_theme else LIGHT_THEME
        SimpleNamespace.__init__(self, **self.colors_dict)

    def _repr_html_(self, *_) -> str:
        """Rich display of the color palette in an HTML frontend."""
        s = 60
        html = f"<h3>Current theme: {self.theme_name}</h3><table>"
        items = {k: v for k, v in self.colors_dict.items()}.items()

        for name, color in items:
            c = su.to_colors(color)
            html += f"""
            <th>
                <svg width='{s}' height='{s}'>
                    <rect width='{s}' height='{s}' style='fill:{c};
                    stroke-width:1;stroke:rgb(255,255,255)'/>
                </svg>
            </th>
            """

        html += "</tr><tr>"
        html += "".join([f"<td>{name}</br>{color}</td>" for name, color in items])
        html += "</tr></table>"

        return html


def get_custom_css() -> str:
    """Return pysepal's custom stylesheet for the ipyvuetify / Voila runtime.

    Concatenates the shared ``base.css`` with the Voila-only overrides in
    ``custom.css`` (base first, so the overrides win on equal specificity). The
    Solara runtime loads the same ``base.css`` via
    :mod:`pysepal.solara.asset_merger`.
    """
    base_css = (CSS_DIR / "base.css").read_text()
    voila_css = (CSS_DIR / "custom.css").read_text()
    return f"{base_css}\n{voila_css}"


# load custom styling of pysepal
sepal_ui_css = HTML(f"<style>{get_custom_css()}</style>")

# load fa-6
fa_css = HTML(
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.2.1/css/all.min.css"/>'
)

# create a small hack to remove fontawesome from the html output
clean_fa_js = Javascript((JS_DIR / "fontawesome.js").read_text())

# display all
display(sepal_ui_css, fa_css, clean_fa_js)
