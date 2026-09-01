"""Test the MapApp widget."""

from pathlib import Path

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
    app = MapApp(locales=["en", "fr"])
    selector = app.language_selector[0]
    assert selector.selected_locale == "fr"
    selector.selected_locale = "en"
    assert current_locale() == "en"


def test_a_supplied_selector_is_rebound_to_this_scope(monkeypatch):
    """A selector built outside a render must not keep the process scope."""
    import pysepal._scope_registry as scope_registry
    from pysepal.i18n import set_locale
    from pysepal.sepalwidgets.vue_app import LocaleSelect

    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    selector = LocaleSelect(locales=["en", "fr"])

    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-b")
    MapApp(language_selector=selector)
    set_locale("fr")
    assert selector.selected_locale == "fr"


def test_mapapp_offers_the_locales_it_is_given() -> None:
    """Without them the default selector can only offer English."""
    translator = Translator(MESSAGE_DIR)
    app = MapApp(locales=translator.available_locales())

    offered = {record["code"] for record in app.language_selector[0].available_locales}

    assert offered == set(translator.available_locales())


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
    panel = rc.find(MapApp).widget.right_panel[0]

    title.value = "Herramientas"

    assert rc.find(MapApp).widget.right_panel[0].config["title"] == "Herramientas"
    assert panel.config["title"] == "Herramientas"


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
    selector = rc.find(MapApp).widget.language_selector[0]

    offered = {record["code"] for record in selector.available_locales}

    assert offered == set(translator.available_locales())
