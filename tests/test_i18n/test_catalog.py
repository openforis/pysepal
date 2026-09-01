"""Binding a catalogue: locale fallback, plurals, formatting and strictness."""

import json
import logging

import pytest

from pysepal.i18n import catalog
from pysepal.i18n.errors import CatalogError, MessageFormatError, MissingMessageError

LAYOUT = {
    "en": {
        "app": {
            "app": {"title": "Spatial Risk", "sub": "Untranslated"},
            "hello": "Hi {name}",
            "literal": "The key is {key}",
            "chips": {"models": {"one": "1 model", "other": "{count} models"}},
            "plain": "seen {count} times",
        }
    },
    "fr": {"app": {"app": {"title": "Risque spatial"}}},
    "pt-BR": {"app": {"app": {"title": "Risco espacial"}}},
}


def test_english_resolves(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("en", "app.title") == "Spatial Risk"


def test_a_target_locale_resolves(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("fr", "app.title") == "Risque spatial"


def test_an_untranslated_key_falls_back_to_english(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("fr", "app.sub") == "Untranslated"


def test_an_unshipped_locale_falls_back_to_english(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("de", "app.title") == "Spatial Risk"


def test_a_bare_primary_subtag_matches_a_shipped_variant(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("pt", "app.title") == "Risco espacial"


def test_placeholders_are_formatted(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("en", "hello", name="Ana") == "Hi Ana"


def test_key_is_positional_only_so_a_message_may_carry_a_key_placeholder(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("en", "literal", key="AOI") == "The key is AOI"


@pytest.mark.parametrize(("count", "expected"), [(1, "1 model"), (0, "0 models"), (7, "7 models")])
def test_count_selects_a_plural_form(build_catalog, count, expected):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("en", "chips.models", count=count) == expected


def test_count_on_an_ordinary_key_is_just_a_placeholder(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    assert messages._resolve("en", "plain", count=3) == "seen 3 times"


def test_plural_identity_comes_from_english_only(build_catalog):
    """A target translating one form must not change whether a key is plural."""
    folder = build_catalog(
        {
            "en": {"a": {"chips": {"models": {"one": "1 model", "other": "{count} models"}}}},
            "fr": {"a": {"chips": {"models": {"other": "{count} modeles"}}}},
        }
    )
    messages = catalog(folder)
    assert messages._resolve("fr", "chips.models", count=1) == "1 model"
    assert messages._resolve("fr", "chips.models", count=4) == "4 modeles"


def test_a_missing_key_raises_by_default(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    with pytest.raises(MissingMessageError, match=r"app\.nothing"):
        messages._resolve("en", "app.nothing")


def test_english_is_authoritative_even_when_the_target_has_the_key(build_catalog):
    folder = build_catalog({"en": {"a": {"t": "T"}}, "fr": {"a": {"t": "F", "ghost": "G"}}})
    with pytest.raises(MissingMessageError, match="ghost"):
        catalog(folder)._resolve("fr", "ghost")


def test_a_non_strict_catalogue_renders_a_marker_and_warns_once(build_catalog, caplog):
    messages = catalog(build_catalog(LAYOUT), strict=False)
    with caplog.at_level(logging.WARNING, logger="sepalui.i18n"):
        assert messages._resolve("en", "app.nothing") == "⟦app.nothing⟧"
        assert messages._resolve("en", "app.nothing") == "⟦app.nothing⟧"
    assert len(caplog.records) == 1


def test_a_non_strict_catalogue_still_raises_on_a_formatting_error(build_catalog):
    messages = catalog(build_catalog(LAYOUT), strict=False)
    with pytest.raises(MessageFormatError, match="hello"):
        messages._resolve("en", "hello")


def test_strict_and_non_strict_facades_are_isolated(build_catalog):
    folder = build_catalog(LAYOUT)
    lenient = catalog(folder, strict=False)
    strict = catalog(folder)
    assert lenient._resolve("en", "app.nothing").startswith("⟦")
    with pytest.raises(MissingMessageError):
        strict._resolve("en", "app.nothing")


def test_isolation_holds_in_the_other_construction_order(build_catalog):
    folder = build_catalog(LAYOUT)
    strict = catalog(folder)
    lenient = catalog(folder, strict=False)
    with pytest.raises(MissingMessageError):
        strict._resolve("en", "app.nothing")
    assert lenient._resolve("en", "app.nothing").startswith("⟦")


def test_one_facade_per_path_and_strictness(build_catalog):
    folder = build_catalog(LAYOUT)
    assert catalog(folder) is catalog(folder)
    assert catalog(folder) is not catalog(folder, strict=False)


def test_both_facades_share_the_parsed_data(build_catalog):
    import pysepal.i18n.binding as binding

    folder = build_catalog(LAYOUT)
    catalog(folder)._resolve("fr", "app.title")
    parsed_after_strict = dict(binding._PARSED)
    catalog(folder, strict=False)._resolve("fr", "app.title")
    assert dict(binding._PARSED) == parsed_after_strict


def test_resolving_english_does_not_populate_the_composite_cache(build_catalog):
    """English laid over itself is always English; the merge and its cache entry are redundant."""
    import pysepal.i18n.binding as binding

    folder = build_catalog(LAYOUT)
    messages = catalog(folder)
    assert messages._resolve("en", "app.title") == "Spatial Risk"
    assert (folder.resolve(), "en") not in binding._COMPOSITE


def test_available_locales_puts_english_first(build_catalog):
    assert catalog(build_catalog(LAYOUT)).available_locales() == ("en", "fr", "pt-BR")


def test_check_aggregates_every_shipped_locale_in_deterministic_order(build_catalog):
    problems = catalog(build_catalog(LAYOUT)).check()
    assert tuple((problem.code, problem.locale, problem.key) for problem in problems) == (
        ("missing_key", "fr", "app.sub"),
        ("missing_key", "fr", "chips.models.one"),
        ("missing_key", "fr", "chips.models.other"),
        ("missing_key", "fr", "hello"),
        ("missing_key", "fr", "literal"),
        ("missing_key", "fr", "plain"),
        ("missing_key", "pt-BR", "app.sub"),
        ("missing_key", "pt-BR", "chips.models.one"),
        ("missing_key", "pt-BR", "chips.models.other"),
        ("missing_key", "pt-BR", "hello"),
        ("missing_key", "pt-BR", "literal"),
        ("missing_key", "pt-BR", "plain"),
    )


def test_check_sorts_across_locales_not_just_within_them(build_catalog):
    """A fixture where sort order and discovery order agree would prove nothing.

    Every code here is already ``missing_key`` and locales are pre-sorted by
    discovery in a case like that, so deleting ``check()``'s ``sorted()`` call
    would not fail it. ``extra_key`` sorting before ``missing_key`` here, against
    ``ar-SA`` (discovered first) losing to ``fr`` (discovered second), is what a
    naive per-locale concatenation gets wrong instead.
    """
    folder = build_catalog(
        {
            "en": {"a": {"a": "A", "b": "B"}},
            "ar-SA": {"a": {"a": "A-ar"}},
            "fr": {"a": {"a": "A-fr", "b": "B-fr", "z": "Z"}},
        }
    )
    problems = catalog(folder).check()
    assert tuple((problem.code, problem.locale, problem.key) for problem in problems) == (
        ("extra_key", "fr", "z"),
        ("missing_key", "ar-SA", "b"),
    )


def test_check_reports_an_unreadable_locale_and_still_reports_the_others(build_catalog):
    """A broken 'fr' file must not swallow 'pt-BR's own, unrelated problem."""
    folder = build_catalog(
        {
            "en": {"a": {"t": "T", "sub": "S"}},
            "fr": {},
            "pt-BR": {"a": {"t": "PT"}},
        }
    )
    (folder / "fr" / "broken.json").write_text("{not json")
    problems = catalog(folder).check()
    assert tuple((problem.code, problem.locale, problem.key) for problem in problems) == (
        ("missing_key", "pt-BR", "sub"),
        ("unreadable_locale", "fr", ""),
    )
    detail = next(problem.detail for problem in problems if problem.code == "unreadable_locale")
    assert "broken.json" in detail


def test_a_render_in_an_unreadable_locale_falls_back_to_english(build_catalog):
    folder = build_catalog({"en": {"a": {"t": "Hello"}}, "fr": {}})
    (folder / "fr" / "broken.json").write_text("{not json")
    assert catalog(folder)._resolve("fr", "t") == "Hello"


def test_an_unreadable_locale_warns_once(build_catalog, caplog):
    folder = build_catalog({"en": {"a": {"t": "Hello"}}, "fr": {}})
    (folder / "fr" / "broken.json").write_text("{not json")
    messages = catalog(folder)
    with caplog.at_level(logging.WARNING, logger="sepalui.i18n"):
        assert messages._resolve("fr", "t") == "Hello"
        assert messages._resolve("fr", "t") == "Hello"
    assert len(caplog.records) == 1
    assert "'fr'" in caplog.records[0].getMessage()


def test_a_non_utf8_locale_file_is_reported_and_falls_back_to_english(build_catalog):
    """UnicodeDecodeError must be caught exactly like a JSON syntax error already is.

    JSON is UTF-8 by specification, so a file saved in another encoding is a
    load failure like any other -- not a crash that bypasses check() and
    _messages_for()'s CatalogError handling.
    """
    folder = build_catalog({"en": {"a": {"t": "Hello"}}, "fr": {}})
    (folder / "fr" / "cafe.json").write_bytes(
        json.dumps({"t": "Café"}, ensure_ascii=False).encode("latin-1")
    )
    messages = catalog(folder)
    problems = messages.check()
    assert tuple((problem.code, problem.locale, problem.key) for problem in problems) == (
        ("unreadable_locale", "fr", ""),
    )
    assert messages._resolve("fr", "t") == "Hello"


def test_a_malformed_english_leaf_does_not_block_a_working_translation(build_catalog):
    """``overlay`` and ``check`` must agree on which leaf wins; they used not to.

    A malformed English template used to make ``overlay`` drop a perfectly
    good French translation while ``check`` reported nothing about it -- a
    working string silently inert, and a clean bill of health that was
    wrong. Both now derive from the one rule: French renders, and ``check``
    still says nothing, because French did nothing wrong.
    """
    folder = build_catalog(
        {"en": {"a": {"hello": "Hi {name"}}, "fr": {"a": {"hello": "Salut {nom}"}}}
    )
    messages = catalog(folder)
    assert messages._resolve("fr", "hello", nom="Ana") == "Salut Ana"
    assert messages.check() == ()
    with pytest.raises(MessageFormatError, match="hello"):
        messages._resolve("en", "hello", name="Ana")


def test_a_structural_error_is_raised_at_bind_time_not_at_first_lookup(build_catalog):
    folder = build_catalog({"en": {"a": {"app": {"retries": 3}}}})
    with pytest.raises(CatalogError, match="every leaf must be a string"):
        catalog(folder)


def test_a_malformed_catalogue_raises_again_on_a_second_bind(build_catalog):
    """A failed __init__ must never populate the facade cache."""
    folder = build_catalog({"en": {"a": {"app": {"retries": 3}}}})
    with pytest.raises(CatalogError):
        catalog(folder)
    with pytest.raises(CatalogError):
        catalog(folder)


def test_an_attribute_placeholder_against_the_wrong_value_type_raises_a_format_error(
    build_catalog,
):
    messages = catalog(build_catalog({"en": {"a": {"greet": "Hi {who.name}"}}}))
    with pytest.raises(MessageFormatError, match="greet"):
        messages._resolve("en", "greet", who=5)


def test_an_index_placeholder_against_the_wrong_value_type_raises_a_format_error(build_catalog):
    messages = catalog(build_catalog({"en": {"a": {"greet": "Hi {who[0]}"}}}))
    with pytest.raises(MessageFormatError, match="greet"):
        messages._resolve("en", "greet", who=5)


def test_a_plural_key_without_count_raises_a_format_error_in_strict_mode(build_catalog):
    messages = catalog(build_catalog(LAYOUT))
    with pytest.raises(MessageFormatError, match="needs a count"):
        messages._resolve("en", "chips.models")


def test_a_plural_key_without_count_raises_a_format_error_in_non_strict_mode(build_catalog):
    messages = catalog(build_catalog(LAYOUT), strict=False)
    with pytest.raises(MessageFormatError, match="needs a count"):
        messages._resolve("en", "chips.models")


def test_the_dedup_warning_names_the_locale_it_is_about(build_catalog, caplog):
    messages = catalog(build_catalog(LAYOUT), strict=False)
    with caplog.at_level(logging.WARNING, logger="sepalui.i18n"):
        messages._resolve("en", "app.nothing")
        messages._resolve("fr", "app.nothing")
    texts = [record.getMessage() for record in caplog.records]
    assert len(texts) == 2
    assert texts[0] != texts[1]
    assert "'en'" in texts[0]
    assert "'fr'" in texts[1]


@pytest.mark.parametrize(
    ("count", "expected"),
    [(1, "one"), (1.0, "one"), (True, "one"), (0, "other"), (2, "other"), ("1", "other")],
)
def test_select_plural_category_pins_the_boundary(count, expected):
    """``True == 1`` in Python, so a boolean count is a real gotcha worth pinning."""
    import pysepal.i18n.binding as binding

    assert binding.select_plural_category(count) == expected
