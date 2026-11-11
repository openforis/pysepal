"""Small pieces shared by the parts of the MapApp shell."""

from typing import Callable, Optional

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara
from ipywidgets import Widget


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
        children=[rv.Icon(children=[icon], size="small")],
        variant="text",
    )
    ipyvue.use_event(btn, "click", lambda *_: on_click())
    return btn


def tooltip_end(widget, text: str, disabled: bool = False):
    """Return ``widget`` wrapped in a tooltip shown on its right side.

    ``widget`` must have been built with ``v_bind="tooltip.props"``.
    """
    slot = [{"name": "activator", "variable": "tooltip", "children": widget}]
    return rv.Tooltip(v_slots=slot, children=[text], disabled=disabled, location="end")


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

    item = rv.ListItem(
        prepend_icon=icon,
        title=None if rail else title,
        class_=classes,
        attributes=attrs,
        link=bool(href or on_click),
        append_icon="mdi-open-in-new" if href and not rail else None,
        v_bind="tooltip.props",
        **extra,
    )

    ipyvue.use_event(item, "click", lambda *_: on_click and on_click())

    return tooltip_end(item, title, disabled=not rail)
