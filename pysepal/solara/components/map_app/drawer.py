"""The MapApp navigation: the left drawer, or the top belt on a narrow window."""

from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg
from pysepal.solara.components.locale_select import LocaleSelectComponent
from pysepal.solara.theme import ThemeState

from .theme_toggle import ThemeToggle

DEFAULT_STEP_ICON = "mdi-checkbox-blank-circle-outline"


@solara.component_vue("NavItem.vue")
def NavItem(
    icon: str,
    title: str,
    rail: bool = False,
    active: bool = False,
    href: str = "",
    item_class: str = "",
    item_attributes: Optional[dict] = None,
    tooltip: str = "right",
    event_click: Optional[Callable[[Any], None]] = None,
):
    """Render one drawer entry: an icon, and its title unless the drawer is a rail.

    In rail mode the title moves to a tooltip.

    Args:
        icon: The entry's icon.
        title: The entry's title, and the tooltip text in rail mode.
        rail: Whether the drawer is a rail.
        active: Highlight the entry as the current step.
        href: Open this URL in a new tab instead of calling ``event_click``.
        item_class: Extra classes on the list item.
        item_attributes: Extra HTML attributes on the list item.
        tooltip: Side of the rail tooltip, ``"right"`` or ``"bottom"``.
        event_click: Called when the user clicks the entry.
    """


def external_links(repo_url: str, docs_url: str) -> list:
    """Return the drawer's link entries: no source or bug link without ``repo_url``."""
    links = []
    if repo_url:
        links.append({"key": "code", "icon": "mdi-code-braces", "url": repo_url})
    if docs_url:
        links.append({"key": "docs", "icon": "mdi-book-open-page-variant", "url": docs_url})
    if repo_url:
        links.append({"key": "bug", "icon": "mdi-bug", "url": f"{repo_url}/issues/new"})
    return links


def _step_entries(has_map, steps, active_index, on_map, on_step) -> list:
    """Return the NavItem arguments of the map entry and of each step."""
    entries = []
    if has_map:
        entries.append(
            {
                "icon": "mdi-map",
                "title": msg("map_app.map"),
                "active": active_index is None,
                "event_click": lambda _: on_map(),
            }
        )
    for i, step in enumerate(steps):
        entries.append(
            {
                "icon": step.get("icon") or DEFAULT_STEP_ICON,
                "title": step.get("name", ""),
                "active": i == active_index and step.get("content_enabled") is not False,
                "item_attributes": {"data-step-id": str(step.get("id"))},
                "event_click": lambda _, i=i: on_step(i),
            }
        )
    return entries


def _link_entries(links) -> list:
    """Return the NavItem arguments of each link."""
    return [
        {
            "icon": link["icon"],
            "title": msg(f"map_app.links.{link['key']}"),
            "href": link["url"],
            "item_class": "link-item",
        }
        for link in links
    ]


@solara.component
def Drawer(
    app_title: str,
    app_icon: str,
    has_map: bool,
    steps: Sequence[Mapping],
    active_index: Optional[int],
    rail: bool,
    pinned: bool,
    disabled: bool,
    links: Sequence[Mapping],
    theme_state: ThemeState,
    locales: Optional[Iterable[str]],
    on_map: Callable[[], None],
    on_step: Callable[[int], None],
    on_pin: Callable[[], None],
):
    """Render the left drawer, a full panel or a 60px rail.

    ``active_index`` and the index ``on_step`` gets point into ``steps``: ids
    may repeat or be missing.
    """
    classes = ["sepal-mapapp__drawer"]
    if rail:
        classes.append("sepal-mapapp__drawer--rail")
    if disabled:
        classes.append("sepal-mapapp__drawer--disabled")

    with rv.Sheet(color="darker", tile=True, elevation=0, class_=" ".join(classes)) as main:
        with rv.Html(tag="div", class_="sepal-mapapp__drawer-header"):
            with rv.Html(tag="div", class_="sepal-mapapp__app-title"):
                rv.Icon(class_="mr-2", children=[app_icon or "mdi-earth"])
                if not rail:
                    rv.Html(
                        tag="span",
                        class_="text-h6 font-weight-medium",
                        children=[app_title],
                    )
            if not rail:
                rv.Spacer()
                solara.Button(
                    icon=True,
                    text=True,
                    children=[
                        rv.Icon(children=["mdi-pin" if pinned else "mdi-pin-outline"], size="small")
                    ],
                    attributes={"title": msg("map_app.unpin" if pinned else "map_app.pin")},
                    on_click=on_pin,
                )

        rv.Divider(class_="ma-0 pa-0")

        with rv.Html(tag="div", class_="sepal-mapapp__drawer-top"):
            with rv.List(class_="pa-0 ma-0", density="compact"):
                for entry in _step_entries(has_map, steps, active_index, on_map, on_step):
                    NavItem(rail=rail, **entry)

        with rv.Html(tag="div", class_="sepal-mapapp__drawer-bottom"):
            rv.Divider(class_="mb-4")
            if links:
                with rv.List(class_="pa-0 ma-0", density="compact"):
                    for entry in _link_entries(links):
                        NavItem(rail=rail, **entry)
                rv.Divider(class_="mt-2 mb-4")
            with rv.Html(
                tag="div",
                class_="sepal-mapapp__config"
                + (
                    " sepal-mapapp__config--compact sepal-mapapp__config--rail config-icon-mini"
                    if rail
                    else ""
                ),
            ):
                ThemeToggle(theme_state=theme_state)
                LocaleSelectComponent(locales=locales)

    return main


BELT_ITEM_PX = 48
"Width of an entry of the belt: a 24px icon and 12px either side."

BELT_START_PX = 56
"Width of the app icon at the start of the belt, with its margins."

BELT_END_PX = 96
"Width of the theme and language buttons at the end of the belt."

BELT_TITLE_CHAR_PX = 11
BELT_TITLE_MAX_PX = 140
"The title gets about 11px a character, up to 140px; the rest goes behind an ellipsis."


def belt_slots(width: int, title: str) -> int:
    """Return how many entries fit in the belt of a ``width`` px window, one at least."""
    title_px = min(len(title) * BELT_TITLE_CHAR_PX, BELT_TITLE_MAX_PX)
    room = width - BELT_START_PX - title_px - BELT_END_PX
    return max(room // BELT_ITEM_PX, 1)


def split_belt(entries: Sequence, slots: int) -> tuple:
    """Split ``entries`` into those the belt shows and those its menu holds.

    When they do not all fit, the last slot goes to the menu button.
    """
    if len(entries) <= slots:
        return list(entries), []
    shown = max(slots - 1, 0)
    return list(entries[:shown]), list(entries[shown:])


@solara.component
def BeltMenu(entries: Sequence[Mapping]):
    """Render the belt's menu button and the entries that did not fit."""
    activator = rv.ListItem(
        v_bind="menu.props",
        link=True,
        prepend_icon="mdi-dots-horizontal",
        class_="sepal-mapapp__item"
        + (" active-step" if any(e.get("active") for e in entries) else ""),
        attributes={"title": msg("map_app.more"), "aria-label": msg("map_app.more")},
    )
    with rv.Menu(
        location="bottom end",
        content_class="sepal-mapapp__belt-menu",
        v_slots=[{"name": "activator", "variable": "menu", "children": activator}],
    ) as main:
        with rv.List(class_="pa-0 ma-0", density="compact"):
            for entry in entries:
                NavItem(**entry)
    return main


@solara.component
def Belt(
    app_title: str,
    app_icon: str,
    width: int,
    has_map: bool,
    steps: Sequence[Mapping],
    active_index: Optional[int],
    disabled: bool,
    links: Sequence[Mapping],
    theme_state: ThemeState,
    locales: Optional[Iterable[str]],
    on_map: Callable[[], None],
    on_step: Callable[[int], None],
):
    """Render the drawer as a bar across the top of a narrow window.

    The app icon and title come first, then the map, the steps and the links as
    icons, then the theme and language buttons at the right end. The entries
    that do not fit in ``width`` go, from the last one, into a menu.
    """
    classes = ["sepal-mapapp__belt"]
    if disabled:
        classes.append("sepal-mapapp__belt--disabled")

    entries = _step_entries(has_map, steps, active_index, on_map, on_step)
    entries += _link_entries(links)
    shown, more = split_belt(entries, belt_slots(width, app_title))

    with rv.Sheet(color="darker", tile=True, elevation=0, class_=" ".join(classes)) as main:
        rv.Icon(class_="sepal-mapapp__belt-icon", children=[app_icon or "mdi-earth"])
        rv.Html(
            tag="span",
            class_="text-h6 font-weight-medium sepal-mapapp__belt-title",
            children=[app_title],
        )
        with rv.List(class_="pa-0 ma-0 sepal-mapapp__belt-items", density="compact"):
            for entry in shown:
                NavItem(rail=True, tooltip="bottom", **entry)
            if more:
                BeltMenu(entries=more)
        rv.Spacer()
        rv.Divider(vertical=True)
        with rv.Html(tag="div", class_="sepal-mapapp__config sepal-mapapp__config--compact px-2"):
            ThemeToggle(theme_state=theme_state)
            LocaleSelectComponent(locales=locales)

    return main
