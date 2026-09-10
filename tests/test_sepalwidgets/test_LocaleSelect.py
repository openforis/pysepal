"""Test both LocaleSelect widgets: the legacy v.Menu and the Vue template."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import solara

import pysepal
from pysepal import sepalwidgets as sw
from pysepal.i18n import current_locale, set_locale
from pysepal.sepalwidgets.vue_app import LocaleSelect
from pysepal.solara.components.locale_select import LocaleSelectComponent
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


@pytest.fixture
def render_selector():
    contexts = []

    def render(locales=None):
        widget, rc = solara.render_fixed(LocaleSelectComponent(locales=locales), handle_error=False)
        contexts.append(rc)
        return widget, rc

    yield render
    for context in reversed(contexts):
        context.close()


def test_vue_offers_every_bundled_catalog(render_selector):
    widget, _ = render_selector(BUNDLED.available_locales())
    assert {record["code"] for record in widget.available_locales} == set(
        BUNDLED.available_locales()
    )


def test_vue_accepts_bare_locale_codes(render_selector):
    widget, _ = render_selector(["en", "es"])
    assert [record["code"] for record in widget.available_locales] == ["en", "es"]
    assert (
        next(record for record in widget.available_locales if record["code"] == "es")["name"]
        == "Spanish"
    )


def test_mount_reads_the_locale_without_changing_it(render_selector):
    set_locale("fr")
    widget, _ = render_selector(["en", "fr"])
    assert widget.value == current_locale() == "fr"


def test_browser_and_python_switch_languages_repeatedly(render_selector):
    widget, _ = render_selector(["en", "fr", "pt-BR"])
    for browser_code, expected in [("fr", "fr"), ("pt_br", "pt-BR"), ("en", "en")]:
        widget.value = browser_code
        assert current_locale() == widget.value == expected
    for code in ["pt-BR", "en", "fr"]:
        set_locale(code)
        assert widget.value == code


def test_offered_locale_iterator_survives_language_changes(render_selector):
    widget, _ = render_selector(iter(["en", "fr"]))
    widget.value = "fr"
    assert [record["code"] for record in widget.available_locales] == ["en", "fr"]


def test_locale_changes_do_not_rerender_the_enclosing_component():
    renders = []

    @solara.component
    def Host():
        renders.append(1)
        LocaleSelectComponent(locales=["en", "fr"])

    _, rc = solara.render(Host(), handle_error=False)
    try:
        set_locale("fr")
        assert renders == [1]
        assert rc.find(LocaleSelect).widget.value == "fr"
    finally:
        rc.close()


def test_unmount_stops_both_directions_and_remount_keeps_the_locale(render_selector):
    widget, rc = render_selector(["en", "fr"])
    widget.value = "fr"
    rc.close()
    set_locale("en")
    assert widget.value == "fr"
    widget.value = "es"
    assert current_locale() == "en"
    replacement, _ = render_selector(["en", "fr"])
    assert replacement.value == "en"


def test_each_kernel_selector_updates_its_own_render(kernel_contexts):
    first, second = kernel_contexts(), kernel_contexts()
    seen = {"first": [], "second": []}

    @solara.component
    def Page(name):
        seen[name].append(current_locale())
        LocaleSelectComponent(locales=["en", "fr", "es"])

    with first:
        _, first_render = solara.render(Page("first"), handle_error=False)
        first_widget = first_render.find(LocaleSelect).widget
    with second:
        _, second_render = solara.render(Page("second"), handle_error=False)
        second_widget = second_render.find(LocaleSelect).widget
    try:
        with first:
            first_widget.value = "fr"
            assert current_locale() == "fr"
        with second:
            assert current_locale() == second_widget.value == "en"
            second_widget.value = "es"
        with first:
            assert current_locale() == first_widget.value == "fr"
        assert seen == {"first": ["en", "fr"], "second": ["en", "es"]}
        assert current_locale() == "en"
    finally:
        with first:
            first_render.close()
        with second:
            second_render.close()


def test_component_rejects_removed_constructor_arguments():
    for argument in ["translator", "locale_state"]:
        with pytest.raises(TypeError):
            solara.render_fixed(LocaleSelectComponent(**{argument: object()}), handle_error=False)


def test_selecting_a_locale_writes_no_config(tmp_path, monkeypatch, render_selector):
    monkeypatch.setenv("HOME", str(tmp_path))
    widget, _ = render_selector(["en", "fr"])
    widget.value = "fr"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_resolution_persistence_and_remounts():
    harness = Path(__file__).parents[1] / "js" / "locale_lifecycle.mjs"
    vue = MESSAGE_DIR.parent / "sepalwidgets" / "vue" / "LocaleSelect.vue"
    subprocess.run(["node", str(harness), str(vue)], check=True, capture_output=True, text=True)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_noncanonical_catalogue_locale_stays_selected_after_remount(tmp_path, render_selector):
    from pysepal.i18n import catalog

    for code, greeting in [("en", "Hello"), ("pt_br", "Olá")]:
        folder = tmp_path / code
        folder.mkdir()
        (folder / "app.json").write_text(json.dumps({"greeting": greeting}))
    messages = catalog(tmp_path)
    widget, _ = render_selector(messages.available_locales())
    set_locale("pt_br")
    assert widget.value == "pt-BR"
    assert messages.msg("greeting") == "Olá"
    assert set(messages.available_locales()) == {"en", "pt_br"}

    props = {"value": widget.value, "offered": [row["code"] for row in widget.available_locales]}
    harness = Path(__file__).parents[1] / "js" / "locale_lifecycle.mjs"
    vue = MESSAGE_DIR.parent / "sepalwidgets" / "vue" / "LocaleSelect.vue"
    subprocess.run(
        ["node", str(harness), str(vue), json.dumps(props)],
        check=True,
        capture_output=True,
        text=True,
    )
