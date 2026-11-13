"""The left drawer of the MapApp shell: title, steps, links, theme and language."""

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
    event_click: Optional[Callable[[Any], None]] = None,
):
    """Render one drawer entry: an icon, and its title unless the drawer is a rail.

    In rail mode the title moves to a tooltip on the right.

    Args:
        icon: The entry's icon.
        title: The entry's title, and the tooltip text in rail mode.
        rail: Whether the drawer is a rail.
        active: Highlight the entry as the current step.
        href: Open this URL in a new tab instead of calling ``event_click``.
        item_class: Extra classes on the list item.
        item_attributes: Extra HTML attributes on the list item.
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


@solara.component
def Drawer(
    app_title: str,
    app_icon: str,
    has_map: bool,
    steps: Sequence[Mapping],
    active_step_id: Optional[int],
    rail: bool,
    pinned: bool,
    disabled: bool,
    links: Sequence[Mapping],
    theme_state: ThemeState,
    locales: Optional[Iterable[str]],
    on_map: Callable[[], None],
    on_step: Callable[[Mapping], None],
    on_pin: Callable[[], None],
):
    """Render the left drawer, a full panel or a 60px rail."""
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
                if has_map:
                    NavItem(
                        icon="mdi-map",
                        title=msg("map_app.map"),
                        rail=rail,
                        active=active_step_id is None,
                        event_click=lambda _: on_map(),
                    )
                for step in steps:
                    NavItem(
                        icon=step.get("icon") or DEFAULT_STEP_ICON,
                        title=step.get("name", ""),
                        rail=rail,
                        active=active_step_id == step.get("id")
                        and step.get("content_enabled") is not False,
                        item_attributes={"data-step-id": str(step.get("id"))},
                        event_click=lambda _, step=step: on_step(step),
                    )

        with rv.Html(tag="div", class_="sepal-mapapp__drawer-bottom"):
            rv.Divider(class_="mb-4")
            if links:
                with rv.List(class_="pa-0 ma-0", density="compact"):
                    for link in links:
                        NavItem(
                            icon=link["icon"],
                            title=msg(f"map_app.links.{link['key']}"),
                            rail=rail,
                            href=link["url"],
                            item_class="link-item",
                        )
                rv.Divider(class_="mt-2 mb-4")
            with rv.Html(
                tag="div",
                class_="sepal-mapapp__config"
                + (" sepal-mapapp__config--rail config-icon-mini" if rail else ""),
            ):
                ThemeToggle(theme_state=theme_state)
                LocaleSelectComponent(locales=locales)

    return main
