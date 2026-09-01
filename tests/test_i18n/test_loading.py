"""Reading a message directory, and overlaying a target locale on English."""

import json

import pytest

from pysepal.i18n.errors import CatalogError
from pysepal.i18n.loading import discover_locale_codes, load_locale, overlay


def test_english_comes_first_then_the_rest_sorted(build_catalog):
    folder = build_catalog(
        {"fr": {"a": {"t": "T"}}, "en": {"a": {"t": "T"}}, "ar-SA": {"a": {"t": "T"}}}
    )
    assert discover_locale_codes(folder) == ("en", "ar-SA", "fr")


def test_discovery_sorts_and_returns_the_raw_directory_names(build_catalog):
    """The codes are directory names, and the sort is what the matcher relies on."""
    folder = build_catalog(
        {"en": {"a": {"t": "T"}}, "ZH-hans": {"a": {"t": "T"}}, "ar-SA": {"a": {"t": "T"}}}
    )
    assert discover_locale_codes(folder) == ("en", "ZH-hans", "ar-SA")


def test_a_folder_without_english_is_refused(build_catalog):
    folder = build_catalog({"fr": {"app": {"title": "Risque"}}})
    with pytest.raises(CatalogError, match="no readable 'en' directory"):
        discover_locale_codes(folder)


def test_two_directories_normalising_to_one_code_are_refused(build_catalog):
    folder = build_catalog(
        {"en": {"a": {"t": "T"}}, "pt-BR": {"a": {"t": "T"}}, "pt_br": {"a": {"t": "T"}}}
    )
    with pytest.raises(CatalogError, match="both normalise to"):
        discover_locale_codes(folder)


def test_a_directory_with_no_json_is_not_offered(build_catalog):
    """A locale is a directory that ships at least one message file."""
    folder = build_catalog({"en": {"a": {"t": "T"}}, "fr": {}})
    assert discover_locale_codes(folder) == ("en",)


def test_a_pycache_directory_is_not_offered_as_a_locale(build_catalog):
    """The motivating bug: __pycache__ exists on every machine that imported the module.

    No name-based special case -- it is excluded because it ships no JSON,
    the same rule an ordinary empty directory is excluded by.
    """
    folder = build_catalog({"en": {"a": {"t": "T"}}})
    pycache = folder / "__pycache__"
    pycache.mkdir()
    (pycache / "loading.cpython-312.pyc").write_bytes(b"\x00")
    assert discover_locale_codes(folder) == ("en",)


def test_an_english_directory_with_no_json_is_refused(build_catalog):
    """An empty en/ must refuse to bind, not silently produce an empty catalogue."""
    folder = build_catalog({"en": {}})
    with pytest.raises(CatalogError, match="no readable 'en' directory"):
        discover_locale_codes(folder)


def test_a_locale_whose_json_sits_in_a_nested_subdirectory_is_not_offered(build_catalog):
    """Not recursive: matches load_locale's own non-recursive glob."""
    folder = build_catalog({"en": {"a": {"t": "T"}}, "fr": {}})
    nested = folder / "fr" / "nested"
    nested.mkdir()
    (nested / "b.json").write_text(json.dumps({"t": "T"}))
    assert discover_locale_codes(folder) == ("en",)


def test_every_file_in_a_locale_is_merged(build_catalog):
    folder = build_catalog({"en": {"app": {"app": {"title": "T"}}, "chips": {"chips": {"n": "N"}}}})
    data = load_locale(folder, "en")
    assert data.messages == {"app.title": "T", "chips.n": "N"}
    assert data.code == "en"


def test_plural_keys_accumulate_across_files(build_catalog):
    """The cross-file union must survive an ordinary file processed after a plural one."""
    folder = build_catalog(
        {
            "en": {
                "a": {"chips": {"models": {"one": "1 model", "other": "{count} models"}}},
                "b": {"app": {"title": "T"}},
            }
        }
    )
    data = load_locale(folder, "en")
    assert data.messages == {
        "chips.models.one": "1 model",
        "chips.models.other": "{count} models",
        "app.title": "T",
    }
    assert data.plural_keys == frozenset({"chips.models"})


def test_an_english_plural_node_missing_a_category_is_refused(build_catalog):
    """The strict rule reaches this call site, not just flatten_document."""
    folder = build_catalog({"en": {"c": {"chips": {"models": {"one": "1 model"}}}}})
    with pytest.raises(CatalogError, match="exactly the string leaves"):
        load_locale(folder, "en")


def test_two_files_colliding_on_one_key_are_refused(build_catalog):
    """File order silently decides the winner today."""
    folder = build_catalog({"en": {"a": {"app": {"title": "One"}}, "b": {"app": {"title": "Two"}}}})
    with pytest.raises(CatalogError, match=r"app\.title"):
        load_locale(folder, "en")


def test_a_key_that_is_both_leaf_and_prefix_is_refused(build_catalog):
    """The one ambiguity `count` could hit."""
    folder = build_catalog({"en": {"a": {"app": "Plain"}, "b": {"app": {"title": "Nested"}}}})
    with pytest.raises(CatalogError, match="both a message and a prefix"):
        load_locale(folder, "en")


def test_the_leaf_and_prefix_error_names_both_files(build_catalog):
    """A real multi-file catalogue needs to know where to edit, not just what collides."""
    folder = build_catalog({"en": {"a": {"app": "Plain"}, "b": {"app": {"title": "Nested"}}}})
    with pytest.raises(CatalogError) as exc_info:
        load_locale(folder, "en")
    assert "a.json" in str(exc_info.value)
    assert "b.json" in str(exc_info.value)


def test_invalid_json_is_refused(build_catalog):
    folder = build_catalog({"en": {}})
    (folder / "en" / "broken.json").write_text("{not json")
    with pytest.raises(CatalogError, match=r"broken\.json"):
        load_locale(folder, "en")


def test_a_file_that_is_not_valid_utf8_is_refused(build_catalog):
    """A mis-encoded file must raise CatalogError, not UnicodeDecodeError."""
    folder = build_catalog({"en": {}})
    (folder / "en" / "cafe.json").write_bytes(
        json.dumps({"hello": "Café"}, ensure_ascii=False).encode("latin-1")
    )
    with pytest.raises(CatalogError, match=r"cafe\.json"):
        load_locale(folder, "en")


def test_an_unreadable_file_is_refused(build_catalog):
    """A directory named *.json is a portable way to force OSError, unlike a chmod game.

    chmod 0o000 does not stop a read on Windows (it only toggles the
    read-only attribute, which blocks writes, not reads), so it would be
    flaky in a cross-platform matrix. read_text() on a directory raises
    OSError on every platform.
    """
    folder = build_catalog({"en": {}})
    (folder / "en" / "adir.json").mkdir()
    with pytest.raises(CatalogError, match=r"adir\.json"):
        load_locale(folder, "en")


def test_the_messages_mapping_is_immutable(build_catalog):
    folder = build_catalog({"en": {"app": {"app": {"title": "T"}}}})
    with pytest.raises(TypeError):
        load_locale(folder, "en").messages["app.title"] = "changed"


def test_a_target_replaces_only_the_keys_english_defines(build_catalog):
    folder = build_catalog(
        {
            "en": {"app": {"app": {"title": "Spatial Risk", "sub": "Subtitle"}}},
            "fr": {"app": {"app": {"title": "Risque spatial", "ghost": "Fantome"}}},
        }
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    assert composite["app.title"] == "Risque spatial"
    assert composite["app.sub"] == "Subtitle"
    assert "app.ghost" not in composite


def test_a_target_may_translate_one_plural_form_and_inherit_the_other(build_catalog):
    folder = build_catalog(
        {
            "en": {"c": {"chips": {"models": {"one": "1 model", "other": "{count} models"}}}},
            "fr": {"c": {"chips": {"models": {"other": "{count} modeles"}}}},
        }
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    assert composite["chips.models.one"] == "1 model"
    assert composite["chips.models.other"] == "{count} modeles"


def test_a_target_plural_category_this_release_lacks_is_dropped(build_catalog):
    """`ru-RU` needs three forms. Until the selector grows, `few` is not a key."""
    folder = build_catalog(
        {
            "en": {"c": {"chips": {"models": {"one": "1 model", "other": "{count} models"}}}},
            "ru-RU": {"c": {"chips": {"models": {"one": "1", "few": "2", "other": "{count}"}}}},
        }
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "ru-RU"))
    assert "chips.models.few" not in composite
    assert composite["chips.models.one"] == "1"


def test_overlay_ignores_a_target_leaf_whose_placeholders_differ(build_catalog):
    """A mismatch would raise at render; English stays active and check() reports it."""
    folder = build_catalog(
        {"en": {"a": {"hello": "Hi {name}"}}, "fr": {"a": {"hello": "Salut {nom}"}}}
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    assert composite["hello"] == "Hi {name}"


def test_overlay_ignores_a_malformed_target_leaf(build_catalog):
    folder = build_catalog(
        {"en": {"a": {"hello": "Hi {name}"}}, "fr": {"a": {"hello": "Bonjour {nom"}}}
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    assert composite["hello"] == "Hi {name}"


def test_overlay_lets_a_parseable_target_replace_a_malformed_english_leaf(build_catalog):
    """A malformed English template imposes no constraint, so a working target still wins.

    French users get "Salut {nom}"; English's own render still crashes loudly
    on "Hi {name" -- that half of the old ruling is unchanged, only which side
    a *good* translation is held hostage to.
    """
    folder = build_catalog(
        {"en": {"a": {"hello": "Hi {name"}}, "fr": {"a": {"hello": "Salut {nom}"}}}
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    assert composite["hello"] == "Salut {nom}"


def test_the_composite_is_immutable(build_catalog):
    folder = build_catalog(
        {"en": {"a": {"app": {"title": "T"}}}, "fr": {"a": {"app": {"title": "F"}}}}
    )
    composite = overlay(load_locale(folder, "en"), load_locale(folder, "fr"))
    with pytest.raises(TypeError):
        composite["app.title"] = "changed"
