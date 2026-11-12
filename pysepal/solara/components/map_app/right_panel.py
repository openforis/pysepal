"""The right panel of the MapApp shell: titled sections of tools beside the map."""

from typing import Callable, Mapping, Optional, Sequence

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg

from ._ui import IconButton, as_children

DEFAULT_CONFIG = {
    "title": "Extra Content",
    "icon": "mdi-widgets",
    "width": 300,
    "description": "",
    "toggle_icon": "mdi-chevron-left",
}


@solara.component
def Section(section: Mapping, last: bool):
    """Render one panel section: header, description, content and divider."""
    title, icon = section.get("title"), section.get("icon")
    with rv.Html(tag="div", class_="mb-4") as main:
        if title or icon:
            with rv.Html(tag="div", class_="section-header mb-3"):
                with rv.Html(tag="div", class_="d-flex align-center"):
                    if icon:
                        rv.Icon(class_="mr-2", small=True, children=[icon])
                    if title:
                        rv.Html(
                            tag="span",
                            class_="subtitle-2 font-weight-medium",
                            children=[title],
                        )
        if section.get("description"):
            with rv.Html(tag="div", class_="section-description mb-3"):
                rv.Html(
                    tag="p",
                    class_="body-2 ma-0 text--secondary",
                    children=[section["description"]],
                )
        for child in as_children(section.get("content")):
            rv.Html(tag="div", class_="mb-3", children=[child])
        if section.get("divider") and not last:
            rv.Divider(class_="mt-4")
    return main


@solara.component
def RightPanel(
    config: Optional[Mapping] = None,
    sections: Sequence[Mapping] = (),
    footer: Sequence = (),
    open: bool = False,
    on_open: Optional[Callable[[bool], None]] = None,
    narrow: bool = False,
    disabled: bool = False,
):
    """Render the right panel, or a bottom sheet on a narrow window.

    The sections stay mounted while the panel is closed, so their state
    survives closing and reopening it.

    Args:
        config: ``title``, ``icon``, ``width``, ``description`` and
            ``toggle_icon`` of the panel.
        sections: The panel sections: ``title``, ``icon``, ``description``,
            ``content`` (an element, a widget, or a list of them) and ``divider``.
        footer: Widgets or elements pinned below the scrolling sections.
        open: Whether the panel is open.
        on_open: Called with the new state when the user opens or closes it.
        narrow: Dock the panel at the bottom of the window.
        disabled: Hide the tab that opens a closed panel.
    """
    config = {**DEFAULT_CONFIG, **(config or {})}
    set_open = on_open or (lambda value: None)

    classes = ["right-panel", "sepal-right-panel"]
    classes.append("sepal-right-panel--open" if open else "sepal-right-panel--closed")
    if narrow:
        classes.append("sepal-right-panel--narrow")
    style = "" if narrow else f"width: {int(config['width'] or 300)}px"

    with rv.Html(tag="div", class_="sepal-right-panel-host") as main:
        with rv.Sheet(
            color="darker", tile=True, elevation=0, class_=" ".join(classes), style_=style
        ):
            with rv.Html(tag="div", class_="sepal-mapapp__drawer-header"):
                with rv.Html(tag="div", class_="sepal-mapapp__app-title"):
                    rv.Icon(class_="mr-2", children=[config["icon"] or "mdi-widgets"])
                    rv.Html(
                        tag="span",
                        class_="title font-weight-medium",
                        children=[config["title"] or ""],
                    )
                rv.Spacer()
                IconButton(
                    icon="mdi-close",
                    title=msg("map_app.close_panel"),
                    on_click=lambda: set_open(False),
                )

            if config["description"]:
                with rv.Html(tag="div", class_="panel-description pa-3"):
                    rv.Html(
                        tag="p",
                        class_="body-2 ma-0 text--secondary",
                        children=[config["description"]],
                    )

            rv.Divider(class_="ma-0 pa-0")

            with rv.Html(tag="div", class_="drawer-top sepal-right-panel__body"):
                with rv.Html(tag="div", class_="pa-4"):
                    for i, section in enumerate(sections):
                        Section(section, last=i == len(sections) - 1).key(f"section-{i}")

            if footer:
                with rv.Html(tag="div", class_="drawer-footer"):
                    rv.Divider(class_="ma-0 pa-0")
                    for child in as_children(footer):
                        rv.Html(tag="div", children=[child])

        if not open and not disabled:
            PanelTab(icon=config["toggle_icon"] or "mdi-menu-left", on_click=lambda: set_open(True))

    return main


@solara.component
def PanelTab(icon: str, on_click: Callable[[], None]):
    """Render the tab that opens a closed panel."""
    with rv.Html(tag="div", class_="right-panel-tab sepal-right-panel__tab") as main:
        tab = rv.Btn(
            tile=True,
            color="secondary",
            class_="control-btn",
            attributes={"title": msg("map_app.show_panel")},
            children=[rv.Icon(children=[icon])],
        )
    ipyvue.use_event(tab, "click", lambda *_: on_click())
    return main
