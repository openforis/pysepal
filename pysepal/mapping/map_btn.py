"""Base ``SepalMap`` Btn."""

import ipyvuetify as v

from pysepal._sepal_widget import SepalWidget
from pysepal._vuetify import IPYVUETIFY_V3, btn_variant, size


def _icon_name(name: str) -> str:
    """Return an icon name as the ``v.Icon`` of the installed major reads it.

    Vuetify 3 gives an unprefixed icon the ``mdi`` class and font, so a Font Awesome
    name needs the ``class:`` prefix to render as is.
    """
    if IPYVUETIFY_V3 and name.startswith("fa"):
        return f"class:{name}"
    return name


class MapBtn(v.Btn, SepalWidget):
    def __init__(self, content: str, **kwargs) -> None:
        """Btn specifically design to be displayed on a map.

        It matches all the characteristics of
        the classic leaflet btn but as they are from ipyvuetify we can use them in combination with Menu to produce on-the-map tiles.
        The MapBtn is responsive to theme changes. It only accept icon or 3 letters as children as the space is very limited.

        Args:
            content: a fa-solid/mdi fully qualified name or a string name. If a string name is used, only the 3 first letters will be displayed.
        """
        # create the icon
        if content.startswith("mdi-") or content.startswith("fa"):
            content = v.Icon(**size("small"), children=[_icon_name(content)])
        else:
            content = content[: min(3, len(content))].upper()

        # some parameters are overloaded to match the map requirements
        kwargs.update(btn_variant(outlined=True))
        kwargs["children"] = [content]
        kwargs["icon"] = False
        kwargs.setdefault("class_", "v-map-btn")

        super().__init__(**kwargs)
