"""The deliberately small named-placeholder language."""

import pytest

from pysepal.i18n.formatting import placeholders, target_leaf_problem


def test_positional_fields_remain_identifiable_for_english_validation():
    assert placeholders("Hi {} and {}") == frozenset({"0", "1"})
    assert placeholders("{0} and {1}") == frozenset({"0", "1"})


def test_an_escaped_brace_is_not_a_placeholder():
    assert placeholders("literal {{brace}} text") == frozenset()


@pytest.mark.parametrize(
    "template",
    [
        "{a.b}",
        "{a[0]}",
        "{name:d}",
        "{name:{width}}",
        "{:{}}",
        "{name!s}",
        "{name!r}",
        "{name!a}",
        "{name!z}",
        "Bonjour {nom",
    ],
)
def test_unsupported_syntax_is_rejected(template):
    assert placeholders(template) is None
    assert target_leaf_problem("Hi {name}", template) == "malformed_template"


def test_mismatched_placeholders_cannot_replace_english():
    assert target_leaf_problem("Hi {name}", "Salut {nom}") == "placeholder_mismatch"


def test_matching_placeholders_can_replace_english():
    assert target_leaf_problem("Hi {name}", "Salut {name}") is None
