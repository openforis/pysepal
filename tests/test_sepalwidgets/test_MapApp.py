"""Test the MapApp widget."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, List, Optional

import ipyvuetify as v
import pytest
import reacton
import solara

import pysepal
from pysepal import mapping as sm
from pysepal.sepalwidgets.vue_app import MapApp, ThemeToggle
from pysepal.solara.theme import ThemeState
from pysepal.translator import Translator

#: Absolute: tests/test_sepalwidgets/test_App.py chdirs and never restores.
MESSAGE_DIR = Path(pysepal.__file__).parent / "message"


def test_mapapp_creates_toggle_bound_to_shared_theme_state() -> None:
    """MapApp should create a toggle that drives the same theme state as the map."""
    theme_state = ThemeState(mode="light", dark=False)
    sepal_map = sm.SepalMap(theme_state=theme_state, gee=False)

    app = MapApp(main_map=[sepal_map], theme_state=theme_state)
    toggle = app.theme_toggle[0]

    assert sepal_map.layers[0].name == "SEPAL Light"

    toggle.dark = True
    assert sepal_map.layers[0].name == "SEPAL Dark"

    toggle.dark = None
    toggle.resolved_dark = False
    assert sepal_map.layers[0].name == "SEPAL Light"

    toggle.resolved_dark = True
    assert sepal_map.layers[0].name == "SEPAL Dark"

    return


def test_theme_toggle_stays_unbound_without_theme_state() -> None:
    """A plain ThemeToggle should keep explicit values until bound explicitly."""
    toggle = ThemeToggle(dark=False)

    assert toggle.get_theme_state() is None
    assert toggle.dark is False

    return


def test_mapapp_no_longer_takes_a_locale_state():
    """The locale is scope state now; there is nothing to hand in."""
    import inspect

    assert "locale_state" not in inspect.signature(MapApp.__init__).parameters


def test_mapapp_rejects_the_removed_locale_state_kwarg():
    """locale_state= must fail loudly, not vanish into **kwargs like an unknown vuetify prop."""
    with pytest.raises(TypeError):
        MapApp(locale_state=object())


def test_mapapp_builds_a_selector_bound_to_the_scope_locale():
    """The default selector starts at the scope locale and writes back to it."""
    from pysepal.i18n import current_locale, set_locale

    set_locale("fr")
    app, rc = reacton.render_fixed(MapApp.element(locales=["en", "fr"]), handle_error=False)
    try:
        selector = app.language_selector[0]
        assert selector.value == "fr"
        selector.value = "en"
        assert current_locale() == "en"
        set_locale("fr")
        assert selector.value == "fr"
    finally:
        rc.close()


def test_a_supplied_widget_is_embedded_as_provided():
    from pysepal.sepalwidgets.vue_app import LocaleSelect

    selector = LocaleSelect(value="fr")
    app = MapApp(language_selector=selector)
    try:
        assert app.language_selector == [selector]
        assert selector.value == "fr"
    finally:
        app.close()
        selector.close()


def test_mapapp_offers_the_locales_it_is_given() -> None:
    """Without them the default selector can only offer English."""
    translator = Translator(MESSAGE_DIR)
    app, rc = reacton.render_fixed(
        MapApp.element(locales=translator.available_locales()), handle_error=False
    )
    try:
        offered = {record["code"] for record in app.language_selector[0].available_locales}
        assert offered == set(translator.available_locales())
    finally:
        rc.close()


def test_mapapp_pushes_panel_updates_into_the_child_panel() -> None:
    """The right panel renders from a child widget built once at construction.

    Nothing propagated parent -> child, so a re-render updated
    ``MapApp.right_panel_config`` while the panel kept rendering the strings it
    was born with -- a translated app changed its title and nothing else.
    """
    app = MapApp(
        right_panel_config={"title": "Tools", "width": 400},
        right_panel_content=[{"title": "Select AOI", "icon": "mdi-map", "content": []}],
    )
    panel = app.right_panel[0]

    app.right_panel_config = {"title": "Herramientas", "width": 400}
    app.right_panel_content = [{"title": "Seleccionar AOI", "icon": "mdi-map", "content": []}]

    assert panel.config["title"] == "Herramientas"
    assert panel.content_data[0]["title"] == "Seleccionar AOI"


def test_mapapp_panel_updates_survive_a_rerender() -> None:
    """The same thing through reacton, which is how an app actually hits it."""
    title = solara.reactive("Tools")

    @solara.component
    def Demo():
        MapApp.element(right_panel_config={"title": title.value, "width": 400})

    _, rc = reacton.render(Demo())
    try:
        panel = rc.find(MapApp).widget.right_panel[0]
        title.value = "Herramientas"
        assert rc.find(MapApp).widget.right_panel[0].config["title"] == "Herramientas"
        assert panel.config["title"] == "Herramientas"
    finally:
        rc.close()


def test_mapapp_element_carries_the_locales_through_reacton() -> None:
    """MapApp takes codes, not a Translator, because reacton flattens one.

    ``Translator`` subclasses ``dict``, so reacton hands ``__init__`` a plain
    dict and the widget cannot call ``available_locales()`` on it.
    """
    translator = Translator(MESSAGE_DIR)

    @solara.component
    def Demo():
        MapApp.element(locales=translator.available_locales())

    _, rc = reacton.render(Demo())
    try:
        selector = rc.find(MapApp).widget.language_selector[0]
        offered = {record["code"] for record in selector.available_locales}
        assert offered == set(translator.available_locales())
    finally:
        rc.close()


def test_mapapp_unmount_disposes_the_embedded_selector():
    from pysepal.i18n import current_locale, set_locale

    visible = solara.reactive(True)

    @solara.component
    def Page():
        if visible.value:
            MapApp.element(locales=["en", "fr"])
        else:
            solara.Text("Closed")

    _, rc = reacton.render(Page(), handle_error=False)
    try:
        selector = rc.find(MapApp).widget.language_selector[0]
        selector.value = "fr"
        visible.value = False
        set_locale("en")
        assert selector.value == "fr"
        selector.value = "es"
        assert current_locale() == "en"
        visible.value = True
        replacement = rc.find(MapApp).widget.language_selector[0]
        assert replacement is not selector
        assert replacement.value == "en"
    finally:
        rc.close()


def test_mapapp_component_constructs_independent_kernel_selectors(kernel_contexts):
    from pysepal.i18n import current_locale

    first, second = kernel_contexts(), kernel_contexts()
    element = MapApp.element(locales=["en", "fr", "es"])
    with first:
        _, first_render = reacton.render(element, handle_error=False)
        first_selector = first_render.find(MapApp).widget.language_selector[0]
    with second:
        _, second_render = reacton.render(element, handle_error=False)
        second_selector = second_render.find(MapApp).widget.language_selector[0]
    try:
        with first:
            first_selector.value = "fr"
            assert current_locale() == "fr"
        with second:
            assert current_locale() == second_selector.value == "en"
            second_selector.value = "es"
        with first:
            assert current_locale() == first_selector.value == "fr"
        assert current_locale() == "en"
    finally:
        with first:
            first_render.close()
        with second:
            second_render.close()


def test_raw_mapapp_has_no_automatic_locale_component():
    app = MapApp()
    try:
        assert app.language_selector == []
    finally:
        app.close()


def test_a_bare_widget_step_content_is_wrapped_in_a_list() -> None:
    """MapApp.vue iterates a step's content.

    A lone widget serializes to a model-id string, which Vue 2 iterates character
    by character -- one empty container per character instead of the widget.
    """
    card = v.Card()

    app = MapApp(
        steps_data=[
            {"id": 1, "name": "AOI", "icon": "mdi-map", "display": "dialog", "content": card}
        ]
    )

    assert app.steps_data[0]["content"] == [card]


def test_a_list_of_step_content_widgets_is_left_alone() -> None:
    """Content that already is a list must not be wrapped again."""
    card = v.Card()

    app = MapApp(
        steps_data=[
            {"id": 1, "name": "AOI", "icon": "mdi-map", "display": "dialog", "content": [card]}
        ]
    )

    assert app.steps_data[0]["content"] == [card]


def test_a_bare_widget_panel_section_content_is_wrapped_in_a_list() -> None:
    """RightPanel.vue iterates a section's content the same way."""
    card = v.Card()

    app = MapApp(right_panel_content=[{"title": "Results", "icon": "mdi-cog", "content": card}])

    assert app.right_panel_content[0]["content"] == [card]
    # the child panel is what renders, and __init__ builds it from the raw kwargs
    assert app.right_panel[0].content_data[0]["content"] == [card]


def test_the_panel_footer_reaches_the_child_that_renders_it() -> None:
    """``RightPanel``, not ``MapApp``, renders it, as with config and content."""
    card = v.Card(children=["Next"])
    app = MapApp(
        right_panel_config={"title": "Tools", "width": 400},
        right_panel_content=[{"title": "Select AOI", "icon": "mdi-map", "content": []}],
        right_panel_footer=[card],
    )

    assert app.right_panel[0].footer_content == [card]


def test_panel_footer_updates_survive_a_rerender() -> None:
    """Without the parent -> child push the panel keeps the footer it was born with."""
    app = MapApp(
        right_panel_content=[{"title": "Select AOI", "icon": "mdi-map", "content": []}],
        right_panel_footer=[v.Card(children=["Next"])],
    )
    panel = app.right_panel[0]

    replacement = v.Card(children=["Siguiente"])
    app.right_panel_footer = [replacement]

    assert panel.footer_content == [replacement]


def test_a_panel_with_no_footer_carries_an_empty_one() -> None:
    """The footer is opt-in: an app that passes none gets an empty one."""
    app = MapApp(right_panel_content=[{"title": "Select AOI", "icon": "mdi-map", "content": []}])

    assert app.right_panel[0].footer_content == []


#: A non-zero Vuetify padding helper: pa-4, px-2, pt-md-3...
_PADDING_CLASS = re.compile(r"^p[atblrsexy]-(?:(?:sm|md|lg|xl)-)?[1-9]")


@dataclass(eq=False)
class _Node:
    tag: str
    classes: List[str]
    style: str
    parent: Optional["_Node"]

    def ancestors(self) -> Iterator["_Node"]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class _Template(HTMLParser):
    """A pysepal ``.vue`` file parsed enough to ask what encloses what."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self.text = (Path(pysepal.__file__).parent / "sepalwidgets/vue" / name).read_text()
        self.nodes: List[_Node] = []
        self._open: Optional[_Node] = None
        self.feed(self.text[: self.text.index("<script>")])

    def handle_starttag(self, tag, attrs) -> None:
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()
        self._open = _Node(tag, classes, attrs.get("style") or "", self._open)
        self.nodes.append(self._open)

    def handle_endtag(self, tag) -> None:
        self._open = self._open.parent

    def first(self, css_class: str) -> _Node:
        return next(node for node in self.nodes if css_class in node.classes)

    def css_rule(self, selector: str) -> str:
        start = self.text.index(selector + " {", self.text.index("<style"))
        return self.text[start : self.text.index("}", start)]


def test_the_footer_renders_outside_the_scrolling_section_area() -> None:
    """Inside ``.drawer-top`` it would scroll away with the sections."""
    footer = _Template("RightPanel.vue").first("drawer-footer")

    assert "v-navigation-drawer" in [node.tag for node in footer.ancestors()]
    assert not [node for node in footer.ancestors() if "drawer-top" in node.classes]


def test_the_drawer_click_rule_leaves_disabled_controls_alone() -> None:
    """A disabled control in a drawer must keep Vuetify's ``pointer-events: none``.

    Checked on the stylesheet: each guard must name the class Vuetify actually
    sets on that control, or the rule only looks narrower.
    """
    template = (Path(pysepal.__file__).parent / "sepalwidgets/vue/MapApp.vue").read_text()
    rule = template.index(".v-navigation-drawer .v-list-item")
    selectors = [s.strip() for s in template[rule : template.index("{", rule)].split(",")]

    assert ".v-navigation-drawer .v-btn:not(.v-btn--disabled)" in selectors
    assert ".v-navigation-drawer .v-list-item:not(.v-list-item--disabled)" in selectors
    assert ".v-navigation-drawer .v-select:not(.v-input--is-disabled)" in selectors
    # An unguarded selector anywhere in the group puts the bug back.
    assert all(":not(" in selector for selector in selectors)
    assert "pointer-events: auto" in template[rule : template.index("}", rule)]


def test_the_footer_adds_no_padding_of_its_own() -> None:
    """A full-bleed action bar could not remove padding added by the slot."""
    template = _Template("RightPanel.vue")
    footer = template.first("drawer-footer")
    slot = [footer] + [node for node in template.nodes if footer in node.ancestors()]

    assert not [c for node in slot for c in node.classes if _PADDING_CLASS.match(c)]
    assert not [node for node in slot if "padding" in node.style]
    assert "padding" not in template.css_rule(".drawer-footer")
