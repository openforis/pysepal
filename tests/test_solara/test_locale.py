"""Tests for the offered-locale matcher and presentation helper."""

import pytest

from pysepal.solara.locale import describe_offered_locales, match_offered_locale

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


@pytest.mark.parametrize(
    "name",
    ["LocaleState", "get_current_locale_state", "resolve_locale_state", "use_locale"],
)
def test_the_locale_state_api_is_gone(name):
    """Replaced by pysepal.i18n's current_locale/set_locale. See the design doc."""
    import pysepal.solara as ps
    import pysepal.solara.locale as locale_mod

    assert not hasattr(ps, name)
    assert not hasattr(locale_mod, name)
