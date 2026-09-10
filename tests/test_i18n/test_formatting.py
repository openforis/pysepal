"""Reading the placeholder names a message template needs."""

from pysepal.i18n.formatting import placeholders, target_leaf_problem


def test_dropping_a_bare_placeholder_changes_the_result():
    """Auto-numbering, not set collapse, is what makes a lost slot visible."""
    assert placeholders("Hi {} and {}") != placeholders("Hi {}")


def test_an_explicit_positional_field_is_read():
    assert placeholders("{0} and {1}") == frozenset({"0", "1"})


def test_attribute_access_contributes_the_root_name():
    assert placeholders("{a.b}") == frozenset({"a"})


def test_index_access_contributes_the_root_name():
    assert placeholders("{a[0]}") == frozenset({"a"})


def test_an_escaped_brace_is_not_a_placeholder():
    assert placeholders("literal {{brace}} text") == frozenset()


def test_an_unbalanced_brace_returns_none_instead_of_raising():
    assert placeholders("Bonjour {nom") is None


def test_a_malformed_target_cannot_replace_english():
    assert target_leaf_problem("Hi {name}", "Bonjour {nom") == "malformed_template"


def test_mismatched_placeholders_cannot_replace_english():
    assert target_leaf_problem("Hi {name}", "Salut {nom}") == "placeholder_mismatch"


def test_matching_placeholders_can_replace_english():
    assert target_leaf_problem("Hi {name}", "Salut {name}") is None


def test_a_malformed_english_template_imposes_no_constraint():
    """English cannot demand agreement with placeholders it does not itself have."""
    assert target_leaf_problem("Hi {name", "Salut {nom}") is None
