"""Custom widgets relative to user application framework.

Gather the customized ``ipyvuetifyWidgets`` used to create the application framework.
All the content of this modules is included in the parent ``pysepal.sepalwidgets`` package. So it can be imported directly from there.

Example:
    .. jupyter-execute::

        from pysepal import sepalwidgets as sw

        sw.LocaleSelect()
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import ipyvuetify as v
import pandas as pd
from deprecated.sphinx import deprecated, versionadded, versionchanged
from ipywidgets import DOMWidget, jsdlink
from ipywidgets.widgets.widget import widget_serialization
from traitlets import (
    Any,
    Bool,
    Dict,
    Instance,
    Int,
    List,
    Unicode,
    Union,
    link,
    observe,
)
from typing_extensions import Self

from pysepal.message import ms
from pysepal.model import Model
from pysepal.scripts import utils as su
from pysepal.sepalwidgets.alert import Banner
from pysepal.sepalwidgets.sepalwidget import SepalWidget
from pysepal.sepalwidgets.vue_app import ThemeToggle
from pysepal.sepalwidgets.widget import Markdown
from pysepal.solara.locale import describe_offered_locales
from pysepal.translator import Translator

logger = logging.getLogger("sepalui.app")

__all__ = [
    "AppBar",
    "DrawerItem",
    "NavDrawer",
    "Footer",
    "App",
    "LocaleSelect",
    "ThemeSelect",
]


class LocaleSelect(v.Menu, SepalWidget):
    COUNTRIES: pd.DataFrame = pd.read_parquet(Path(__file__).parents[1] / "data" / "locale.parquet")
    "the country list as a df. columns [code, name, flag]"

    FLAG: str = "https://flagcdn.com/{}.svg"
    "the url of the svg flag images"

    btn: Optional[v.Btn] = None
    "the btn to click when changing language"

    language_list: Optional[v.List] = None
    "the list of countries with their flag,name in english, and ISO code"

    def __init__(self, translator: Optional[Translator] = None, **kwargs) -> None:
        """A language selector for sepal-ui based application.

        It displays the currently requested language (not the one used by the translator).
        When value is changed, the sepal-ui config file is updated. It is designed to be used in a AppBar component.

        .. warning:: as the component is a v.Menu to get the selected value you need to lisen to "value" instead of "v_model".

        .. versionadded:: 2.7.0

        Args:
            translator: the translator of the app, to match the used language
            kwargs (optional): any arguments for a Btn object, children will be override
        """
        # extract the available language from the translator
        # default to only en-US if no translator is set
        available_locales = ["en"] if translator is None else translator.available_locales()

        # extract the language information from the translator
        # if not set default to english
        code = "en" if translator is None else translator._target

        self.locale_icon = v.Icon(class_="mr-2", children=["mdi-translate"])

        kwargs.setdefault("small", True)
        kwargs["v_model"] = False
        kwargs["v_on"] = "x.on"
        kwargs["children"] = [self.locale_icon, code]
        kwargs["min_width"] = 95

        self.btn = v.Btn(**kwargs)

        self.language_list = v.List(
            dense=True,
            flat=True,
            color="menu",
            v_model=True,
            max_height="300px",
            style_="overflow: auto; border-radius: 0 0 0 0;",
            children=[
                v.ListItemGroup(children=self._get_country_items(available_locales), v_model="")
            ],
        )

        super().__init__(
            children=[self.language_list],
            v_model=False,
            close_on_content_click=True,
            v_slots=[{"name": "activator", "variable": "x", "children": self.btn}],
            value=code,
        )

        # add js behaviour
        jsdlink((self.language_list.children[0], "v_model"), (self, "value"))
        self.language_list.children[0].observe(self._on_locale_select, "v_model")

    def _get_country_items(self, locales: list) -> List[str]:
        """Get the list of countries as a list of listItem.

        Reduce the list to the available language of the module.

        Args:
            locales: list of the locales to display

        Returns:
            the list of country widget to display in the app
        """
        country_list = []
        catalog = json.loads(self.COUNTRIES.to_json(orient="records"))
        for record in describe_offered_locales(locales, catalog):
            children = [
                v.ListItemContent(
                    class_="mr-2", children=[v.ListItemTitle(children=[record["name"]])]
                ),
                v.ListItemActionText(children=[record["code"]]),
            ]

            country_list.append(v.ListItem(value=record["code"], children=children))

        return country_list

    def _on_locale_select(self, change: dict) -> None:
        """adapt the application to the newly selected language.

        Display the new flag and country code on the widget btn.
        """
        if not change["new"]:
            return

        self.btn.children = [self.locale_icon, change["new"]]
        # self.btn.color = "info"

        return


@deprecated(
    version="3.0.0", reason="This class will be renamed to ThemeToggle in v3.2.0 for better clarity"
)
class ThemeSelect(v.VuetifyTemplate):
    template_file = Unicode(str(Path(__file__).parents[1] / "sepalwidgets/vue/Theming.vue")).tag(
        sync=True
    )

    dark = Bool(None, allow_none=True).tag(sync=True)
    enable_auto = Bool(True).tag(sync=True)
    on_icon = Unicode("mdi-weather-night").tag(sync=True)
    off_icon = Unicode("mdi-weather-sunny").tag(sync=True)
    auto_icon = Unicode("mdi-auto-fix").tag(sync=True)

    def __init__(self):
        """Initialize the ThemeSelect widget."""
        super().__init__()

    @observe("dark")
    def _on_dark_change(self, change):
        """Observer for dark trait changes.

        This is called when the Vue component syncs the dark value back to Python.
        """
        logger.info(f"OBSERVER TRIGGERED: dark changed from {change['old']} to {change['new']}")

    def toggle_theme(self) -> None:
        """Toggle between dark and light theme.

        This method can be used for testing or programmatic theme switching
        without relying on the Vue frontend.
        """
        self.dark = not self.dark


class AppBar(v.AppBar, SepalWidget):
    toogle_button: Optional[v.Btn]
    "The btn to display or hide the drawer to the user"

    title: Optional[v.ToolbarTitle]
    "The widget containing the app title"

    locale: Optional[LocaleSelect]
    "The locale selector of all apps"

    theme = Optional[ThemeSelect]
    "The theme selector of all apps"

    def __init__(
        self,
        title: str = "SEPAL module",
        translator: Optional[Translator] = None,
        theme_toggle: ThemeToggle = None,
        **kwargs,
    ) -> None:
        """Custom AppBar widget with the provided title using the sepal color framework.

        Args:
            title: the title of the app
            translator: the app translator to pass to the locale selector object
            kwargs (optional): any parameters from a v.AppBar. If set, 'children' and 'app' will be overwritten.
        """
        self.toggle_button = v.Btn(
            icon=True,
            children=[v.Icon(class_="white--text", children=["fa-solid fa-bars"])],
        )

        self.title = v.ToolbarTitle(children=[title])

        self.locale = LocaleSelect(translator=translator)
        self.theme = theme_toggle or ThemeToggle()

        # set the default parameters
        kwargs.setdefault("class_", "white--text")
        kwargs.setdefault("color", "main")
        kwargs.setdefault("dense", True)
        kwargs["app"] = True
        kwargs["children"] = [
            self.toggle_button,
            self.title,
            v.Spacer(),
            self.locale,
            self.theme,
        ]

        super().__init__(**kwargs)

    def set_title(self, title: str) -> Self:
        """Set the title of the appBar.

        Args:
            title: the new app title
        """
        self.title.children = [title]

        return self


class DrawerItem(v.VuetifyTemplate):

    href = Union([Unicode(), Dict()], default_value=None, allow_none=True).tag(sync=True)
    input_value = Any(None, allow_none=True).tag(sync=True)
    link = Bool(None, allow_none=True).tag(sync=True)
    target = Unicode(None, allow_none=True).tag(sync=True)
    resize = Int().tag(sync=True)
    _metadata = Dict(default_value=None, allow_none=True).tag(sync=True)

    alert = Bool().tag(sync=True)
    "Trait to control visibility of an alert in the drawer item"

    alert_badge: Optional[v.ListItemAction] = None
    "red circle to display in the drawer"

    tiles: Optional[List[v.Card]] = None
    "the cards of the application"

    children = List(Union([Instance(DOMWidget), Unicode()])).tag(sync=True, **widget_serialization)
    template_file = Unicode(str(Path(__file__).parent / "vue/DrawerItem.vue")).tag(sync=True)

    def __init__(
        self,
        title: str,
        icon: str = "",
        card: str = "",
        href: str = "",
        model: Optional[Model] = None,
        bind_var: str = "",
        **kwargs,
    ) -> None:
        """Custom DrawerItem using the user input.

        If a card is set the drawerItem will trigger the display of all the Tiles in the app that have the same mount_id.
        If an href is set, the drawer will open the link in a new tab.

        Args:
            title: the title of the drawer item
            icon: the full name of a mdi/fa icon
            card: the mount_id of tiles in the app
            href: the absolute link to an external web page
            model: sepalwidget model where is defined the bin_var trait
            bind_var: required when model is selected. Trait to link with 'alert' self trait parameter
            kwargs (optional): any parameter from a v.ListItem. If set, '_metadata', 'target', 'link' and 'children' will be overwritten.
        """
        icon = icon if icon else "fa-regular fa-folder"

        children = [
            v.ListItemAction(children=[v.Icon(children=[icon])]),
            v.ListItemContent(children=[v.ListItemTitle(children=[title])]),
        ]

        # set default parameters
        kwargs["link"] = True
        kwargs["children"] = children
        kwargs.setdefault("input_value", False)
        if href:
            kwargs["href"] = href  # cannot be set twice anyway
            kwargs["target"] = "_blank"
            kwargs.setdefault("_metadata", None)
        elif card:
            kwargs["_metadata"] = {"card_id": card}
            kwargs.setdefault("href", None)
            kwargs.setdefault("target", None)

        # call the constructor
        super().__init__(**kwargs)

        # cannot be set as a class member because it will be shared with all
        # the other draweritems.
        self.alert_badge = v.ListItemAction(
            children=[v.Icon(children=["fa-solid fa-circle"], x_small=True, color="error")]
        )

        if model:
            if not bind_var:
                raise Exception("You have selected a model, you need a trait to bind with drawer.")

            link((model, bind_var), (self, "alert"))

    @observe("alert")
    def add_notif(self, change: dict) -> None:
        """Add a notification alert to drawer."""
        if change["new"]:
            if self.alert_badge not in self.children:
                new_children = self.children[:]
                new_children.append(self.alert_badge)
                self.children = new_children
        else:
            self.remove_notif()

        return

    def remove_notif(self) -> None:
        """Remove notification alert."""
        if self.alert_badge in self.children:
            new_children = self.children[:]
            new_children.remove(self.alert_badge)

            self.children = new_children

        return

    def display_tile(self, tiles: List[v.Card]) -> Self:
        """Display the appropriate tiles when the item is clicked.

        The tile to display will be all tile in the list with the mount_id as the current object.

        Args:
            tiles: the list of all the available tiles in the app
        """
        self.tiles = tiles

        return self

    def vue_on_click_python(self, data=None) -> Self:
        """Display the appropriate tiles when the item is clicked."""
        self.resize += 1

        for tile in self.tiles:
            show = self._metadata["card_id"] == tile._metadata["mount_id"]
            tile.viz = show

        # change the current item status
        self.input_value = True

        # Remove notification
        self.remove_notif()

        return self

    def _on_click(self, *args) -> Self:
        """Display the appropriate tiles when the item is clicked."""
        self.vue_on_click_python()
        return self


class NavDrawer(v.NavigationDrawer, SepalWidget):
    items: List[DrawerItem] = []
    "the list of all the drawerItem to display in the drawer"

    def __init__(
        self,
        items: List[DrawerItem] = [],
        code: str = "",
        wiki: str = "",
        issue: str = "",
        repo_folder: su.Pathlike = "",
        **kwargs,
    ) -> None:
        """Custom NavDrawer using the different DrawerItems of the user.

        The drawer can include links to the github page of the project for wiki, bugs and repository.

        Args:
            items: the list of all the drawerItem to display in the drawer. This items should pilote the different tile visibility
            code: the absolute link to the source code
            wiki: the absolute link the the wiki page
            issue: the absolute link to the issue tracker
            repo_folder: the path to the github repository folder where the changelog and version are stored. Default to the current working directory.
            kwargs (optional) any parameter from a v.NavigationDrawer. If set, 'app' and 'children' will be overwritten.
        """
        self.items = items

        repo_folder = Path(repo_folder) if repo_folder else Path.cwd()

        v_slots = []

        code_link = []
        if code:
            item_code = DrawerItem(
                ms.widgets.navdrawer.code, icon="fa-regular fa-file-code", href=code
            )
            code_link.append(item_code)

        if wiki:
            item_wiki = DrawerItem(
                ms.widgets.navdrawer.wiki, icon="fa-solid fa-book-open", href=wiki
            )
            code_link.append(item_wiki)
        if issue:
            item_bug = DrawerItem(ms.widgets.navdrawer.bug, icon="fa-solid fa-bug", href=issue)
            code_link.append(item_bug)

        version_card = VersionCard(repo_folder=repo_folder)
        if version_card:
            v_slots = [{"name": "append", "children": [version_card]}]

        children = [
            v.List(dense=True, class_="pa-0", children=self.items),
            v.Divider(),
            v.List(dense=True, children=code_link),
        ]

        # set default parameters
        kwargs.setdefault("v_model", True)
        kwargs["app"] = True
        kwargs.setdefault("color", "darker")
        kwargs["children"] = children
        kwargs.setdefault("v_slots", v_slots)

        # call the constructor
        super().__init__(**kwargs)

        # bind the javascripts behavior
        for i in self.items:
            i.observe(self._on_item_click, "input_value")

    def display_drawer(self, toggleButton: v.Btn) -> Self:
        """Bind the drawer to the app toggleButton.

        Args:
            toggleButton: the button that activate the drawer
        """
        toggleButton.on_event("click", self._on_drawer_click)

        return self

    def _on_drawer_click(self, *args) -> Self:
        """Toggle the drawer visibility."""
        self.v_model = not self.v_model

        return self

    def _on_item_click(self, change: dict) -> Self:
        """Deactivate all the other items when on of the is activated."""
        if change["new"] is False:
            return self

        # reset all others states
        [setattr(i, "input_value", False) for i in self.items if i != change["owner"]]

        return self


class Footer(v.Footer, SepalWidget):
    def __init__(self, text: str = "", **kwargs) -> None:
        """Custom Footer with cuzomizable text.

        Not yet capable of displaying logos.

        Args:
            text: the text to display in the future
            kwargs (optional): any parameter from a v.Footer. If set ['app', 'children'] will be overwritten.
        """
        text = text if text != "" else "SEPAL \u00a9 {}".format(datetime.today().year)

        # set default parameters
        kwargs.setdefault("color", "main")
        kwargs["app"] = True
        kwargs["children"] = [text]

        # call the constructor
        super().__init__(**kwargs)


class App(v.App, SepalWidget):
    tiles: List[v.Card] = []
    "the tiles of the app"

    appBar: Optional[AppBar] = None
    "the AppBar of the application"

    footer: Optional[Footer] = None
    "the footer of the application"

    navDrawer: Optional[NavDrawer] = None
    "the navdrawer of the application"

    content: Optional[v.Content] = None
    "the tiles organized in a fluid container"

    def __init__(
        self,
        tiles: List[v.Card] = [],
        appBar: Optional[AppBar] = None,
        footer: Optional[Footer] = None,
        navDrawer: Optional[NavDrawer] = None,
        translator: Optional[Translator] = None,
        **kwargs,
    ) -> None:
        """Custom App display with the tiles created by the user using the sepal color framework.

        Display false appBar if not filled. Navdrawer is fully optional.
        The drawerItem will be linked to the app tile and they will be able to control their display
        If the navdrawer exist, it will be linked to the appbar togglebtn.

        Args:
            tiles: the tiles of the app
            appBar: the appBar of the application
            footer: the footer of the application
            navDrawer: the navdrawer of the application
            translator: the translator of the app to display language information
            kwargs (optional) any parameter from a v.App. If set, 'children' will be overwritten.
        """
        self.tiles = tiles

        app_children = []

        # create a false appBar if necessary
        if appBar is None:
            appBar = AppBar(translator=translator)
        self.appBar = appBar
        app_children.append(self.appBar)

        # add the navDrawer if existing
        if navDrawer is not None:
            # bind app tile list to the navdrawer
            [di.display_tile(tiles) for di in navDrawer.items]

            # link it with the appbar
            navDrawer.display_drawer(self.appBar.toggle_button)

            # add the drawers to the children
            self.navDrawer = navDrawer
            app_children.append(self.navDrawer)
        else:
            # remove the toggle button from the navbar
            self.appBar.toggle_button.hide()

        # add the content of the app
        self.content = v.Content(children=[v.Container(fluid=True, children=tiles)])
        app_children.append(self.content)

        # add the footer if existing
        if footer is not None:
            self.footer = footer
            app_children.append(self.footer)

        # create a negative overlay to force the background color
        bg = v.Overlay(color="bg", opacity=1, style_="transition:unset", z_index=-1)

        # set default parameters
        kwargs.setdefault("_metadata", {"mount_id": "content"})
        kwargs.setdefault("v_model", None)
        kwargs["children"] = [bg, *app_children]

        # call the constructor
        super().__init__(**kwargs)

        # display a warning if the set language cannot be reached
        if translator is not None:
            if translator._match is False:
                msg = ms.locale.fallback.format(
                    requested=translator._targeted, used=translator._target
                )
                self.add_banner(msg, type_="error")

        # add js event
        self.appBar.locale.observe(self._locale_info, "value")

    def show_tile(self, name: str) -> Self:
        """Select the tile to display when the app is launched.

        Args:
            name: the mount-id of the tile(s) to display
        """
        # show the tile
        for tile in self.tiles:
            tile.viz = name == tile._metadata["mount_id"]

        # activate the drawerItem
        if self.navDrawer:
            items = (i for i in self.navDrawer.items if i._metadata is not None)
            for i in items:
                if name == i._metadata["card_id"]:
                    i.input_value = True

        return self

    @versionadded(version="2.4.1", reason="New end user interaction method")
    @versionchanged(version="2.7.1", reason="new id\\_ and persistent parameters")
    def add_banner(
        self,
        msg: str = "",
        type_: str = "info",
        id_=None,
        persistent: bool = True,
        **kwargs,
    ) -> Self:
        r"""Display a snackbar object on top of the app.

        Used to communicate development information to end user (release date, known issues, beta version). The alert is dissmisable and prominent.

        Args:
            msg: Message to display in application banner. default to nothing
            type\_: Used to display an appropriate banner color. fallback to "info".
            id\_: unique banner identificator.
            persistent: Whether to close automatically based on the length of message (False) or make it indefinitely open (True). Overridden if timeout duration is set.
            \*\*kwargs: any arguments of the sw.Banner constructor. if set, 'children' will be overwritten.
        """
        # the Banner was previously an Alert. for compatibility we accept the type parameter
        type_ = kwargs.pop("type", type_)

        # the banner will be piled up from the first to the latest.
        # only the first one is shown
        # dismissed banner are remove from the children

        # extract the banner from the app children
        children, banner_list = [], []
        for e in self.content.children.copy():
            dst = banner_list if isinstance(e, Banner) else children
            dst.append(e)

        # only set viz to true if it's the first one
        viz = False if len(banner_list) > 0 else True

        # create the baner and interactions
        w_bnr = Banner(msg, type_, id_, persistent, viz=viz, **kwargs)
        banner_list += [w_bnr]

        # display the number of banner in queue
        banner_list[0].set_btn(len(banner_list) - 1)

        # place everything back in the app chldren list
        self.content.children = banner_list + children

        # add interaction at the end
        w_bnr.observe(self._remove_banner, "v_model")

        return self

    def _locale_info(self, change: dict) -> None:
        """Display information about the locale change."""
        if change["new"] != "":
            msg = ms.locale.change.format(locale=change["new"])
            self.add_banner(msg)

        return

    def _remove_banner(self, change: dict) -> None:
        """Remove banner and adapt display of the others.

        Adapt the banner display so that the first one is the only one shown displaying the number of other banner in the queue
        """
        if change["new"] is False:
            # extract the banner from the app children
            children, banner_list = [], []
            for e in self.content.children.copy():
                dst = banner_list if isinstance(e, Banner) else children
                dst.append(e)

            # remove the banner from the list
            banner_list.remove(change["owner"])

            # change the visibility of the widgets
            [setattr(b, "viz", i == 0) for i, b in enumerate(banner_list)]

            # set the btn of the the first element if possible
            len(banner_list) == 0 or banner_list[0].set_btn(len(banner_list) - 1)

            # place everything back in the app chldren list
            self.content.children = banner_list + children

        return


def VersionCard(repo_folder: str = Path.cwd()) -> Optional[v.Card]:
    """Returns a card with the current version of the app and a changelog dialog.

    Args:
        github_url: the url of the github repository of the app
    """
    app_version = su.get_app_version(repo_folder)
    if not app_version:
        return None

    release_text, changelog_text = su.get_changelog(repo_folder)

    content = []

    if release_text:
        content.append(Markdown(release_text))

    if changelog_text:
        content.append(v.Divider())
        content.append(Markdown(changelog_text))

    btn_close = v.Btn(
        color="primary",
        children=[ms.widgets.navdrawer.changelog.close_btn],
        on_event=[
            (
                "click",
                lambda *_: setattr(w_changelog, "v_model", False),
            )
        ],
    )

    w_changelog = v.Dialog(
        v_model=False,
        max_width=750,
        children=[
            v.Card(
                children=[
                    v.CardTitle(
                        class_="headline",
                        children=[ms.widgets.navdrawer.changelog.title],
                    ),
                    v.CardText(children=content),
                    v.CardActions(children=[v.Spacer(), btn_close]),
                ]
            )
        ],
    )

    w_version = v.Card(
        class_="text-center",
        height="48px",
        tile=True,
        color="accent",
        children=[
            v.CardText(
                children=[
                    ms.widgets.navdrawer.changelog.version.format(version=app_version),
                    w_changelog,
                ],
            ),
        ],
    )

    w_version.on_event("click", lambda *_: setattr(w_changelog, "v_model", True))
    btn_close.on_event("click", lambda *_: setattr(w_changelog, "v_model", False))

    return w_version
