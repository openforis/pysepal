"""One reactive locale per runtime scope, readable from anywhere."""

import solara

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


def test_two_kernels_and_the_process_default_are_isolated(kernel_contexts):
    first, second = kernel_contexts(), kernel_contexts()
    set_locale("de")
    with first:
        assert current_locale() == "en"
        set_locale("es")
    with second:
        assert current_locale() == "en"
        set_locale("fr")
    with first:
        assert current_locale() == "es"
    with second:
        assert current_locale() == "fr"
    assert current_locale() == "de"


def test_reading_during_a_render_subscribes():
    """The whole design rests on this: no hook, and a change re-renders."""
    seen = []

    @solara.component
    def Label():
        seen.append(current_locale())
        solara.Text("x")

    set_locale("en")
    _, rc = solara.render(Label(), handle_error=False)
    try:
        set_locale("fr")
        set_locale("es")
        assert seen == ["en", "fr", "es"]
    finally:
        rc.close()


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
    _, rc = solara.render(ViaHelper(), handle_error=False)
    try:
        set_locale("ru-RU")
        assert seen == ["en", "ru-RU"]
    finally:
        rc.close()


def test_kernel_renders_update_only_their_own_language(kernel_contexts):
    first, second = kernel_contexts(), kernel_contexts()
    seen = {"first": [], "second": []}

    @solara.component
    def Label(name):
        seen[name].append(current_locale())
        solara.Text(current_locale())

    with first:
        _, first_render = solara.render(Label("first"), handle_error=False)
    with second:
        _, second_render = solara.render(Label("second"), handle_error=False)
    try:
        with first:
            set_locale("fr")
            set_locale("es")
        with second:
            set_locale("pt_br")
        assert seen == {"first": ["en", "fr", "es"], "second": ["en", "pt-BR"]}
    finally:
        with first:
            first_render.close()
        with second:
            second_render.close()
