"""What `check()` tells a translator, without raising at them."""

from pysepal.i18n.loading import load_locale, overlay
from pysepal.i18n.problems import compare_locale


def compare(build_catalog, layout, target="fr"):
    folder = build_catalog(layout)
    return compare_locale(load_locale(folder, "en"), load_locale(folder, target))


def codes(problems):
    return [(problem.code, problem.key) for problem in problems]


def test_an_untranslated_key_is_reported_not_raised(build_catalog):
    problems = compare(
        build_catalog,
        {"en": {"a": {"app": {"title": "T", "sub": "S"}}}, "fr": {"a": {"app": {"title": "T"}}}},
    )
    assert codes(problems) == [("missing_key", "app.sub")]
    assert problems[0].locale == "fr"


def test_a_target_only_key_is_reported(build_catalog):
    problems = compare(
        build_catalog,
        {"en": {"a": {"app": {"title": "T"}}}, "fr": {"a": {"app": {"title": "T", "ghost": "G"}}}},
    )
    assert codes(problems) == [("extra_key", "app.ghost")]


def test_placeholder_drift_is_reported(build_catalog):
    problems = compare(
        build_catalog,
        {"en": {"a": {"hello": "Hi {name}"}}, "fr": {"a": {"hello": "Salut {nom}"}}},
    )
    assert codes(problems) == [("placeholder_mismatch", "hello")]
    assert "name" in problems[0].detail and "nom" in problems[0].detail


def test_an_unsupported_plural_category_is_named_as_such(build_catalog):
    problems = compare(
        build_catalog,
        {
            "en": {"c": {"models": {"one": "1", "other": "{count}"}}},
            "ru-RU": {"c": {"models": {"one": "1", "few": "2", "other": "{count}"}}},
        },
        target="ru-RU",
    )
    assert codes(problems) == [("unsupported_plural_category", "models.few")]
    assert "never used" in problems[0].detail


def test_a_plural_node_flattened_to_a_plain_message_is_one_shape_problem(build_catalog):
    problems = compare(
        build_catalog,
        {
            "en": {"c": {"models": {"one": "1", "other": "{count}"}}},
            "fr": {"c": {"models": "modeles"}},
        },
    )
    assert codes(problems) == [("shape_mismatch", "models")]


def test_a_plain_message_turned_into_a_plural_node_is_one_shape_problem(build_catalog):
    problems = compare(
        build_catalog,
        {
            "en": {"c": {"models": "models"}},
            "fr": {"c": {"models": {"one": "1", "other": "{count}"}}},
        },
    )
    assert codes(problems) == [("shape_mismatch", "models")]


def test_problems_are_sorted_deterministically(build_catalog):
    problems = compare(
        build_catalog,
        {
            "en": {"a": {"b": "B", "c": "C", "d": "D {x}"}},
            "fr": {"a": {"d": "D {y}", "z": "Z"}},
        },
    )
    assert codes(problems) == [
        ("extra_key", "z"),
        ("missing_key", "b"),
        ("missing_key", "c"),
        ("placeholder_mismatch", "d"),
    ]


def test_a_malformed_target_template_is_reported_not_raised(build_catalog):
    problems = compare(
        build_catalog,
        {"en": {"a": {"hello": "Hi {name}"}}, "fr": {"a": {"hello": "Bonjour {nom"}}},
    )
    assert codes(problems) == [("malformed_template", "hello")]


def test_a_malformed_english_template_is_not_reported_here(build_catalog):
    """The module author's own mistake; Task 7 surfaces it loudly at render instead."""
    problems = compare(
        build_catalog,
        {"en": {"a": {"hello": "Hi {name"}}, "fr": {"a": {"hello": "Salut {nom}"}}},
    )
    assert codes(problems) == []


def test_a_clean_translation_reports_nothing(build_catalog):
    assert compare(build_catalog, {"en": {"a": {"t": "T"}}, "fr": {"a": {"t": "F"}}}) == ()


def test_english_compared_with_itself_is_clean(build_catalog):
    folder = build_catalog({"en": {"a": {"t": "T {x}"}}})
    english = load_locale(folder, "en")
    assert compare_locale(english, english) == ()
    assert overlay(english, english)["t"] == "T {x}"
