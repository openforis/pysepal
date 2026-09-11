"""msg() is the one lookup, and it follows the scope's locale."""

from concurrent.futures import ThreadPoolExecutor

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
    _, rc = solara.render(Greeting(), handle_error=False)
    try:
        set_locale("fr")
        assert seen == ["Hello", "Bonjour"]
    finally:
        rc.close()


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
    _, rc = solara.render(ViaHelper(), handle_error=False)
    try:
        set_locale("fr")
        assert seen == ["Hello", "Bonjour"]
    finally:
        rc.close()


def test_worker_without_a_kernel_reads_the_process_default(build_catalog, kernel_contexts):
    messages = catalog(build_catalog(LAYOUT))
    context = kernel_contexts()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(messages.msg, "hello").result() == "Hello"
        with context:
            set_locale("fr")
            assert messages.msg("hello") == "Bonjour"
            assert pool.submit(messages.msg, "hello").result() == "Hello"
        set_locale("fr")
        assert pool.submit(messages.msg, "hello").result() == "Bonjour"
