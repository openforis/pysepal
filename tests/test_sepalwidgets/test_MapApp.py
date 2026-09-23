"""Test the MapApp widget."""

from pathlib import Path

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


def test_the_drawer_click_rule_leaves_disabled_controls_alone() -> None:
    """A disabled control in a drawer must keep Vuetify's ``pointer-events: none``.

    ``.v-navigation-drawer .v-btn`` is specificity 0,2,0 and Vuetify's own
    ``.v-btn--disabled`` is 0,1,0, so without the ``:not()`` guards the
    drawer rule wins and hands every disabled button its pointer events back.
    It stays unclickable -- the ``disabled`` attribute still applies -- but it
    lights up on hover like a live control, which is how the bug was found.

    Asserted against the stylesheet text because the cascade is the whole
    bug: a version of this rule that merely LOOKS narrower (matching on the
    wrong disabled class, say) would leave the symptom in place, so each
    guard is named explicitly.
    """
    template = (Path(pysepal.__file__).parent / "sepalwidgets/vue/MapApp.vue").read_text()
    rule = template.index(".v-navigation-drawer .v-list-item")
    end = template.index("}", rule)
    selectors = template[rule:end]

    assert ".v-btn:not(.v-btn--disabled)" in selectors
    assert ".v-list-item:not(.v-list-item--disabled)" in selectors
    assert ".v-select:not(.v-input--is-disabled)" in selectors
    # An unguarded selector anywhere in the group puts the bug back.
    assert "pointer-events: auto" in template[rule : end + 80]
