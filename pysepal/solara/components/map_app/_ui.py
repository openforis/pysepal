"""Small pieces of the MapApp shell that differ between the Vuetify majors."""

from typing import Callable, Optional

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara
from ipywidgets import Widget

from pysepal._vuetify import IPYVUETIFY_V3, btn_variant, size

# Vuetify 3 renamed the typography and emphasis helper classes.
_TEXT_CLASSES = {
    "title": "text-h6",
    "headline": "text-h5",
    "subtitle-2": "text-subtitle-2",
    "body-2": "text-body-2",
    "text--secondary": "text-medium-emphasis",
}


def text_class(*names: str) -> str:
    """Return the helper classes ``names`` (Vuetify 2 spelling) for the installed major."""
    return " ".join(_TEXT_CLASSES.get(name, name) if IPYVUETIFY_V3 else name for name in names)


def as_children(content) -> list:
    """Return a section's ``content`` as a list of widgets or elements."""
    if content is None:
        return []
    if isinstance(content, (Widget, solara.Element)):
        return [content]
    return list(content)


@solara.component
def IconButton(icon: str, on_click: Callable[[], None], title: str = "", class_: str = ""):
    """Render a small icon button with a native ``title`` hint."""
    btn = rv.Btn(
        icon=True,
        class_=class_,
        attributes={"title": title} if title else {},
        children=[rv.Icon(children=[icon], **size("small"))],
        **btn_variant(text=True),
    )
    ipyvue.use_event(btn, "click", lambda *_: on_click())
    return btn


def activator(variable: str) -> dict:
    """Return the props that make a widget the activator of a ``variable`` slot."""
    return {"v_bind": f"{variable}.props"} if IPYVUETIFY_V3 else {"v_on": f"{variable}.on"}


def tooltip_end(widget, text: str, disabled: bool = False):
    """Return ``widget`` wrapped in a tooltip shown on its right side.

    ``widget`` must have been built with ``**activator("tooltip")``.
    """
    slot = [{"name": "activator", "variable": "tooltip", "children": widget}]
    placement = {"location": "end"} if IPYVUETIFY_V3 else {"right": True}
    return rv.Tooltip(v_slots=slot, children=[text], disabled=disabled, **placement)


@solara.component
def NavItem(
    icon: str,
    title: str,
    rail: bool = False,
    active: bool = False,
    on_click: Optional[Callable[[], None]] = None,
    href: str = "",
    attributes: Optional[dict] = None,
    class_: str = "",
):
    """Render one drawer entry: an icon, and its title unless the drawer is a rail.

    In rail mode the title moves to a tooltip. The tooltip is always there and only
    disabled outside the rail: changing the tree would replace the item widget, and
    ``use_event`` stays bound to the widget it first saw.
    """
    classes = " ".join(c for c in ["sepal-mapapp__item", class_, active and "active-step"] if c)
    attrs = dict(attributes or {})
    extra = {"href": href} if href else {}
    if href:
        attrs["target"] = "_blank"
    extra.update(activator("tooltip"))

    if IPYVUETIFY_V3:
        item = rv.ListItem(
            prepend_icon=icon,
            title=None if rail else title,
            class_=classes,
            attributes=attrs,
            link=bool(href or on_click),
            append_icon="mdi-open-in-new" if href and not rail else None,
            **extra,
        )
    else:
        children = [rv.ListItemIcon(children=[rv.Icon(class_="mb-1", children=[icon])])]
        if not rail:
            title_children = [title]
            if href:
                title_children += [
                    rv.Spacer(),
                    rv.Icon(class_="ml-1", small=True, children=["mdi-open-in-new"]),
                ]
            title_el = rv.ListItemTitle(
                class_="font-weight-medium d-flex align-center", children=title_children
            )
            children.append(rv.ListItemContent(children=[title_el]))
        item = rv.ListItem(
            class_=classes,
            attributes=attrs,
            link=bool(href or on_click),
            children=children,
            **extra,
        )

    ipyvue.use_event(item, "click", lambda *_: on_click and on_click())

    return tooltip_end(item, title, disabled=not rail)
