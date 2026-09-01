"""Tests for scope-keyed locale-state resolution and the offered-locale matcher."""

import pytest

import pysepal.solara.locale as locale_mod
from pysepal import _scope_registry as scope_registry
from pysepal.solara.locale import (
    LocaleState,
    describe_offered_locales,
    get_current_locale_state,
    match_offered_locale,
    resolve_locale_state,
)
from pysepal.solara.runtime_context import UnsupportedSolaraRuntimeError

CATALOG = [
    {"code": "en", "name": "English", "flag": "gb"},
    {"code": "fr", "name": "French", "flag": "fr"},
    {"code": "es-ES", "name": "Spanish", "flag": "es"},
    {"code": "es-MX", "name": "Spanish, Mexico", "flag": "mx"},
    {"code": "ru", "name": "Russian", "flag": "ru"},
]


def test_match_prefers_an_exact_code():
    assert match_offered_locale("pt-BR", ["pt", "pt-BR"]) == "pt-BR"


def test_match_falls_back_to_the_bare_primary_subtag():
    """navigator.language reports es-CL where the app only ships es."""
    assert match_offered_locale("es-CL", ["en", "es"]) == "es"


def test_match_falls_back_to_an_offered_variant_of_the_same_primary():
    """The reverse case: the browser says pt, the app only ships pt-BR."""
    assert match_offered_locale("pt", ["en", "pt-BR"]) == "pt-BR"


def test_match_takes_the_first_offered_variant():
    assert match_offered_locale("es", ["es-MX", "es-ES"]) == "es-MX"


def test_match_returns_empty_so_the_caller_can_fall_through():
    assert match_offered_locale("de", ["en", "fr"]) == ""
    assert match_offered_locale("", ["en"]) == ""


def test_describe_keeps_every_offered_code():
    """The app's catalogs are authoritative; the parquet only supplies labels.

    Filtering with ``code.isin(...)`` silently dropped any catalog the parquet
    lacked -- including pysepal's own bundled ``message/es/``, which the picker
    could therefore never offer.
    """
    described = describe_offered_locales(["en", "es", "ru-RU"], CATALOG)
    assert [record["code"] for record in described] == ["en", "ru-RU", "es"]


def test_describe_borrows_the_label_of_a_matching_variant():
    """A bare ``es`` keeps its own code but shows up as Spanish."""
    (record,) = describe_offered_locales(["es"], CATALOG)
    assert record == {"code": "es", "name": "Spanish", "flag": "es"}


def test_describe_labels_an_unknown_code_with_itself():
    """Never drop a catalog just because the parquet has never heard of it."""
    (record,) = describe_offered_locales(["xx-YY"], CATALOG)
    assert record == {"code": "xx-YY", "name": "xx-YY", "flag": ""}


def test_describe_sorts_by_display_name():
    described = describe_offered_locales(["ru", "en", "fr"], CATALOG)
    assert [record["name"] for record in described] == ["English", "French", "Russian"]


def test_locale_state_coerces_an_empty_code_to_english():
    state = LocaleState("")
    assert state.locale == "en"
    state.set_locale("")
    assert state.locale == "en"


def test_resolve_returns_explicit_locale_state():
    """An explicitly provided locale_state wins over any scope lookup."""
    state = LocaleState("fr")
    assert resolve_locale_state(state) is state


def test_resolve_uses_current_locale_state_when_available(monkeypatch):
    scoped = LocaleState("fr")
    monkeypatch.setattr(locale_mod, "get_current_locale_state", lambda: scoped)
    assert resolve_locale_state() is scoped


def test_resolve_locale_state_does_not_swallow_errors(monkeypatch):
    """A guard that only exists for monkeypatched symbols hides real failures."""

    def _boom():
        raise UnsupportedSolaraRuntimeError("no runtime")

    monkeypatch.setattr(locale_mod, "get_current_locale_state", _boom)
    with pytest.raises(UnsupportedSolaraRuntimeError):
        resolve_locale_state()


def test_current_locale_state_is_stable_per_scope(monkeypatch):
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    assert get_current_locale_state() is get_current_locale_state()


def test_current_locale_state_is_isolated_per_scope(monkeypatch):
    """Two connections must not share a language."""
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    first = get_current_locale_state()
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-b")
    assert get_current_locale_state() is not first


def test_current_locale_state_never_raises_without_a_session(monkeypatch):
    """Locale is UI state; it has no business failing on an auth condition."""
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-a")
    assert isinstance(get_current_locale_state(), LocaleState)


def test_a_fresh_scope_starts_at_english(monkeypatch):
    """The default is a constant, never a read of the machine's config file.

    This is what makes a downstream test suite deterministic: before v4 the
    language a test saw was whatever ``~/.sepal-ui-config`` happened to hold.
    """
    monkeypatch.setattr(scope_registry, "current_scope_id", lambda: "kernel-fresh")
    assert get_current_locale_state().locale == "en"
