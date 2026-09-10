"""msg() is the one lookup, and it follows the scope's locale."""

import threading

import solara

from pysepal.i18n import catalog, set_locale

LAYOUT = {
    "en": {
        "a": {
            "hello": "Hello",
            "sub": "Untranslated",
            "chips": {"models": {"one": "1 model", "other": "{count} models"}},
        }
    },
    "fr": {"a": {"hello": "Bonjour"}},
}


def test_msg_renders_in_the_scope_locale(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    set_locale("fr")
    assert messages.msg("hello") == "Bonjour"


def test_msg_falls_back_to_english_for_an_untranslated_key(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    set_locale("fr")
    assert messages.msg("sub") == "Untranslated"


def test_msg_takes_a_computed_key(build_catalog):
    """Keys held as data in a registry table are the reason msg takes a key."""
    messages = catalog(build_catalog(LAYOUT))
    entry = {"label_key": "hello"}
    assert messages.msg(entry["label_key"]) == "Hello"


def test_msg_selects_a_plural_form(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages.msg("chips.models", count=1) == "1 model"
    assert messages.msg("chips.models", count=4) == "4 models"


def test_msg_re_renders_a_component_when_the_language_changes(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    seen = []

    @solara.component
    def Greeting():
        seen.append(messages.msg("hello"))
        solara.Text("x")

    set_locale("en")
    solara.render(Greeting(), handle_error=False)
    set_locale("fr")
    assert seen == ["Hello", "Bonjour"]


def test_msg_works_in_a_plain_helper_called_from_a_component(build_catalog):
    """No hook, so a helper is not a second-class caller."""
    messages = catalog(build_catalog(LAYOUT))
    seen = []

    def greeting():
        return messages.msg("hello")

    @solara.component
    def ViaHelper():
        seen.append(greeting())
        solara.Text("x")

    set_locale("en")
    solara.render(ViaHelper(), handle_error=False)
    set_locale("fr")
    assert seen == ["Hello", "Bonjour"]


def test_msg_does_not_raise_off_the_main_thread(build_catalog):
    """A worker calling msg() must degrade, never explode."""
    messages = catalog(build_catalog(LAYOUT))
    set_locale("fr")
    out = []
    worker = threading.Thread(target=lambda: out.append(messages.msg("hello")))
    worker.start()
    worker.join()
    assert out and isinstance(out[0], str)


def test_msg_reads_english_in_a_scope_that_never_set_a_locale(monkeypatch, build_catalog):
    """This is the half of the worker story that is testable without a server.

    Do NOT rewrite the thread test above to assert ``["Hello"]``. Under pytest
    there is no Solara server, so the main thread and the worker BOTH resolve to
    ``PROCESS_SCOPE`` -- the worker sees the same locale, and the assertion fails.
    The spec's "a worker returns English" holds because a *served* connection has
    a kernel scope while a pool worker falls back to the process one; what makes
    English appear is the scope differing, which is what this test pins directly.
    """
    import pysepal._scope_registry as scope_registry

    messages = catalog(build_catalog(LAYOUT))
    set_locale("fr")
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-never-set")
    assert messages.msg("hello") == "Hello"
