"""One reactive locale per runtime scope, readable from anywhere."""

import solara

import pysepal._scope_registry as scope_registry
from pysepal.i18n import current_locale, set_locale


def test_the_default_locale_is_english():
    assert current_locale() == "en"


def test_a_plain_read_outside_a_render_does_not_raise():
    """Helpers, event handlers and worker threads all read this way."""
    set_locale("fr")
    assert current_locale() == "fr"


def test_set_locale_normalises_the_code():
    set_locale("pt_br")
    assert current_locale() == "pt-BR"


def test_an_empty_code_falls_back_to_english():
    set_locale("fr")
    set_locale("")
    assert current_locale() == "en"


def test_two_scopes_do_not_disturb_each_other(monkeypatch):
    """A Solara server serves many connections from one process."""
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    set_locale("es")
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-b")
    assert current_locale() == "en"
    set_locale("fr")
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    assert current_locale() == "es"


def test_reading_during_a_render_subscribes():
    """The whole design rests on this: no hook, and a change re-renders."""
    seen = []

    @solara.component
    def Label():
        seen.append(current_locale())
        solara.Text("x")

    set_locale("en")
    solara.render(Label(), handle_error=False)
    set_locale("fr")
    set_locale("es")
    assert seen == ["en", "fr", "es"]


def test_a_plain_helper_called_from_a_render_also_subscribes():
    """This is why msg() needs no hook and no second lookup function."""
    seen = []

    def helper():
        return current_locale()

    @solara.component
    def ViaHelper():
        seen.append(helper())
        solara.Text("x")

    set_locale("en")
    solara.render(ViaHelper(), handle_error=False)
    set_locale("ru-RU")
    assert seen == ["en", "ru-RU"]
