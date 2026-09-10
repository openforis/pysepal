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


def test_a_nested_field_in_a_format_spec_is_a_value_the_message_needs():
    """``{name:{width}}`` needs ``width`` too; missing it raises inside str.format."""
    assert placeholders("Hi {name:{width}}") == frozenset({"name", "width"})


def test_a_nested_spec_does_not_reuse_the_outer_auto_position():
    """``"{:{}}".format(v, w)`` consumes two slots, so the scan must count both."""
    assert placeholders("{:{}}") == frozenset({"0", "1"})


def test_an_unknown_conversion_makes_the_template_malformed():
    """``{n!z}`` parses cleanly and only raises inside str.format."""
    assert placeholders("Hi {name!z}") is None


def test_the_conversions_str_format_accepts_are_read_normally():
    for conversion in ("s", "r", "a"):
        assert placeholders(f"Hi {{name!{conversion}}}") == frozenset({"name"})


def test_a_target_needing_an_extra_spec_value_cannot_replace_english():
    """It would pass a name-only comparison and then raise at render."""
    assert target_leaf_problem("Hi {name}", "Salut {name:{width}}") == "placeholder_mismatch"


def test_a_target_with_an_unknown_conversion_cannot_replace_english():
    assert target_leaf_problem("Hi {name}", "Salut {name!z}") == "malformed_template"
