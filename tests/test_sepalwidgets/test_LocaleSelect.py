"""Test both LocaleSelect widgets: the legacy v.Menu and the Vue template."""

from pathlib import Path

import pytest

import pysepal
from pysepal import sepalwidgets as sw
from pysepal.i18n import current_locale, set_locale
from pysepal.i18n.locale_store import _locale_ref
from pysepal.sepalwidgets.vue_app import LocaleSelect
from pysepal.translator import Translator

#: Absolute: tests/test_sepalwidgets/test_App.py chdirs and never restores.
MESSAGE_DIR = Path(pysepal.__file__).parent / "message"

#: pysepal ships a bare ``es`` and an ``ru-RU``; ``locale.parquet`` has neither
#: (only ``es-ES``/``es-AR``/... and ``ru``). Both widgets used to intersect the
#: two sets, so these two languages could never be picked.
BUNDLED = Translator(MESSAGE_DIR)


def test_init() -> None:
    """Check widget init."""
    locale_select = sw.LocaleSelect()

    # minimal btn
    assert isinstance(locale_select, sw.LocaleSelect)
    assert len(locale_select.language_list.children[0].children) == 1

    return


def test_change_language() -> None:
    """Selecting a locale updates the button, and persists nothing."""
    locale_select = sw.LocaleSelect()
    locale_select._on_locale_select({"new": "fr"})
    assert locale_select.btn.children[-1] == "fr"


def test_menu_offers_every_bundled_catalog() -> None:
    locale_select = sw.LocaleSelect(translator=BUNDLED)
    offered = {item.value for item in locale_select.language_list.children[0].children}
    assert offered == set(BUNDLED.available_locales())


def test_menu_value_is_the_locale_code() -> None:
    """A target the parquet lacks used to leave ``value`` an empty DataFrame column."""
    locale_select = sw.LocaleSelect(translator=Translator(MESSAGE_DIR, "es"))
    assert locale_select.value == "es"


def test_vue_offers_every_bundled_catalog() -> None:
    locale_select = LocaleSelect(translator=BUNDLED)
    offered = {record["code"] for record in locale_select.available_locales}
    assert offered == set(BUNDLED.available_locales())


def test_vue_accepts_bare_locale_codes() -> None:
    """MapApp forwards codes rather than a Translator; see test_MapApp."""
    locale_select = LocaleSelect(locales=["en", "es"])
    assert [record["code"] for record in locale_select.available_locales] == ["en", "es"]


def test_vue_borrows_a_display_name_for_a_bare_code() -> None:
    locale_select = LocaleSelect(translator=BUNDLED)
    spanish = next(r for r in locale_select.available_locales if r["code"] == "es")
    assert spanish["name"] == "Spanish"


def test_the_widget_starts_at_the_scope_locale():
    """A newly built selector reads its initial value from the scope locale."""
    set_locale("fr")
    assert LocaleSelect(locales=["en", "fr"]).selected_locale == "fr"


def test_constructing_the_widget_does_not_write_back():
    """Constructing a selector must not change the locale it reads."""
    set_locale("fr")
    LocaleSelect(locales=["en", "fr"])
    assert current_locale() == "fr"


def test_constructing_a_selector_does_not_subscribe_the_enclosing_component():
    """peek(), not .value -- otherwise every locale change re-renders the parent."""
    import solara

    renders = []

    @solara.component
    def Host():
        renders.append(1)
        LocaleSelect(locales=["en", "fr"])
        solara.Text("x")

    solara.render(Host(), handle_error=False)
    set_locale("fr")
    assert len(renders) == 1


def test_the_browser_picking_a_language_sets_the_scope_locale():
    widget = LocaleSelect(locales=["en", "fr"])
    widget.selected_locale = "fr"
    assert current_locale() == "fr"


def test_a_trait_change_is_normalised_before_it_is_stored():
    widget = LocaleSelect(locales=["en", "pt-BR"])
    widget.selected_locale = "pt_br"
    assert current_locale() == "pt-BR"


def test_an_empty_trait_change_is_ignored():
    """The Vue side clears the trait briefly while it resolves."""
    set_locale("fr")
    widget = LocaleSelect(locales=["en", "fr"])
    widget.selected_locale = ""
    assert current_locale() == "fr"


def test_setting_the_locale_updates_the_widget():
    widget = LocaleSelect(locales=["en", "fr"])
    set_locale("fr")
    assert widget.selected_locale == "fr"


def test_the_two_directions_do_not_loop():
    """A change must settle, not ping-pong between trait and Reactive."""
    widget = LocaleSelect(locales=["en", "fr", "es"])
    seen = []
    unsubscribe = _locale_ref().subscribe(seen.append)
    try:
        widget.selected_locale = "fr"
    finally:
        unsubscribe()
    assert seen == ["fr"]

    # "pt_br" -> "pt-BR" is the one input where the trait and the Reactive
    # genuinely disagree, so the mirror has to correct the trait and then
    # settle rather than keep bouncing.
    widget = LocaleSelect(locales=["en", "pt-BR"])
    seen = []
    unsubscribe = _locale_ref().subscribe(seen.append)
    try:
        widget.selected_locale = "pt_br"
    finally:
        unsubscribe()
    assert seen == ["pt-BR"]
    assert widget.selected_locale == "pt-BR"


def test_close_unsubscribes_so_a_dead_widget_is_not_updated():
    widget = LocaleSelect(locales=["en", "fr"])
    widget.close()
    set_locale("fr")
    assert widget.selected_locale == "en"


def test_close_is_idempotent():
    widget = LocaleSelect(locales=["en", "fr"])
    widget.close()
    widget.close()


def test_close_also_stops_the_widget_writing():
    """Unsubscribing covers the read direction; nulling _ref covers the write."""
    widget = LocaleSelect(locales=["en", "fr"])
    widget.close()
    widget.selected_locale = "fr"
    assert current_locale() == "en"


def test_rebinding_detaches_the_old_reactive(monkeypatch):
    """A widget built outside a render must not stay on the process scope."""
    import pysepal._scope_registry as scope_registry

    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    widget = LocaleSelect(locales=["en", "fr"])
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-b")
    widget._rebind()
    set_locale("fr")
    assert widget.selected_locale == "fr"

    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    set_locale("es")
    assert widget.selected_locale == "fr", "the old scope must no longer reach it"


def test_there_is_no_public_bind_method():
    """The binder is transport, not an alternate locale API."""
    assert not hasattr(LocaleSelect, "bind_locale_state")
    assert not hasattr(LocaleSelect, "get_locale_state")


def test_vue_rejects_the_removed_locale_state_kwarg():
    """locale_state= must fail loudly, not vanish into **kwargs like an unknown vuetify prop."""
    with pytest.raises(TypeError):
        LocaleSelect(locale_state=object())


def test_selecting_a_locale_writes_no_config(tmp_path, monkeypatch):
    """Adapted from the removed locale_state version, and still worth having.

    pysepal 4 stopped writing ~/.sepal-ui-config, because a process-global file
    made one machine's language decide what every connection rendered in.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    widget = LocaleSelect(translator=BUNDLED)
    widget.selected_locale = "fr"
    assert list(tmp_path.iterdir()) == []
