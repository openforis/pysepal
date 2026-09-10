"""Flattening one message document, and the errors that stop a bad one."""

import pytest

from pysepal.i18n.errors import CatalogError
from pysepal.i18n.flatten import flatten_document


def flatten(document):
    """English: the module author's own structure, checked strictly."""
    return flatten_document(document, locale="en", source="app.json", authoritative=True)


def target(document):
    """A translated locale: permissive, because a translator is not the author."""
    return flatten_document(document, locale="fr", source="app.json", authoritative=False)


def test_nested_objects_become_dotted_keys():
    messages, plural_keys = flatten({"app": {"title": "Spatial Risk"}})
    assert messages == {"app.title": "Spatial Risk"}
    assert plural_keys == frozenset()


def test_a_numeric_object_flattens_instead_of_becoming_a_tuple():
    """Translator.sanitize turned this into a tuple; the flat map does not."""
    messages, _ = flatten({"aoi_sel": {"adm": {"0": "Country", "1": "Region"}}})
    assert messages == {"aoi_sel.adm.0": "Country", "aoi_sel.adm.1": "Region"}


def test_a_plural_node_contributes_one_key_per_category():
    messages, plural_keys = flatten(
        {"chips": {"models": {"one": "1 model", "other": "{count} models"}}}
    )
    assert messages == {"chips.models.one": "1 model", "chips.models.other": "{count} models"}
    assert plural_keys == frozenset({"chips.models"})


def test_a_leaf_that_is_not_a_string_is_refused():
    with pytest.raises(CatalogError, match="every leaf must be a string"):
        flatten({"app": {"retries": 3}})


def test_a_dot_inside_a_key_segment_is_refused():
    with pytest.raises(CatalogError, match="contains a dot"):
        flatten({"app.title": "Spatial Risk"})


def test_a_document_that_is_not_an_object_is_refused():
    with pytest.raises(CatalogError, match="must be a JSON object"):
        flatten(["Spatial Risk"])


def test_a_plural_node_missing_a_category_is_refused():
    with pytest.raises(CatalogError, match="exactly the string leaves"):
        flatten({"chips": {"models": {"one": "1 model"}}})


def test_a_plural_node_with_an_extra_category_is_refused():
    """`few` is not supported yet; silently dropping it would hide the mistake."""
    with pytest.raises(CatalogError, match="exactly the string leaves"):
        flatten({"chips": {"models": {"one": "1", "few": "2", "other": "{count}"}}})


def test_a_plural_category_that_is_not_a_string_is_refused():
    with pytest.raises(CatalogError, match="exactly the string leaves"):
        flatten({"chips": {"models": {"one": "1 model", "other": {"deep": "no"}}}})


def test_a_plural_node_at_the_root_is_refused():
    with pytest.raises(CatalogError, match="at the root"):
        flatten({"one": "1 model", "other": "{count} models"})


def test_a_target_may_translate_one_plural_form():
    messages, plural_keys = target({"chips": {"models": {"other": "{count} modeles"}}})
    assert messages == {"chips.models.other": "{count} modeles"}
    assert plural_keys == frozenset({"chips.models"})


def test_a_target_may_carry_a_category_this_release_lacks():
    """`ru-RU` needs three forms. The overlay drops `few`; check() reports it."""
    messages, _ = target({"c": {"m": {"one": "1", "few": "2", "other": "{count}"}}})
    assert set(messages) == {"c.m.one", "c.m.few", "c.m.other"}


def test_a_target_still_cannot_nest_under_a_plural_category():
    with pytest.raises(CatalogError, match="every leaf must be a string"):
        target({"c": {"m": {"one": {"deep": "no"}, "other": "x"}}})


def test_a_target_plural_category_containing_a_dot_is_refused():
    """Unreachable for English -- the shape check above catches a bad category name first.

    A target skips that shape check, so this is the one case that can
    actually reach the dot-in-category-name check.
    """
    with pytest.raises(CatalogError, match="contains a dot"):
        target({"c": {"m": {"one.x": "1 model", "other": "{count} models"}}})


def test_a_bare_positional_placeholder_in_english_is_refused():
    with pytest.raises(CatalogError, match=r"'app\.hello' uses a positional placeholder"):
        flatten({"app": {"hello": "Hi {}"}})


def test_an_explicit_positional_placeholder_in_english_is_refused():
    with pytest.raises(CatalogError, match=r"'app\.hello' uses a positional placeholder"):
        flatten({"app": {"hello": "Hi {0}"}})


def test_a_positional_placeholder_in_a_target_is_not_a_load_error():
    """A translator's own mistake; already a placeholder_mismatch against English."""
    messages, _ = target({"app": {"hello": "Salut {}"}})
    assert messages == {"app.hello": "Salut {}"}


def test_a_named_placeholder_in_english_is_unaffected():
    messages, _ = flatten({"app": {"hello": "Hi {name}"}})
    assert messages == {"app.hello": "Hi {name}"}


def test_an_escaped_brace_in_english_is_unaffected():
    messages, _ = flatten({"app": {"hello": "literal {{brace}} text"}})
    assert messages == {"app.hello": "literal {{brace}} text"}
