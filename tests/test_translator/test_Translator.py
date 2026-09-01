"""Test the Translator object."""

import json
from pathlib import Path

import pytest

from pysepal.message import ms
from pysepal.translator import Translator


def test_init(translation_folder: Path) -> None:
    """Check the Translator can be inited.

    Args:
        translation_folder: the folder where the language keys are stored
    """
    # assert that the test key exist in fr
    translator = Translator(translation_folder, "fr")
    assert translator.test_key == "Clef de test"

    # assert that the the code work if the path is a str
    translator = Translator(str(translation_folder), "fr")
    assert translator.test_key == "Clef de test"

    # assert that the test does not exist in es and we fallback to en
    translator = Translator(translation_folder, "es")
    assert translator.test_key == "Test key"

    # assert that using a non existing lang lead to fallback to english
    translator = Translator(translation_folder, "it")
    assert translator.test_key == "Test key"

    # check the internal variables once to make sure that they are not removed/changed
    translator = Translator(translation_folder, "fr")
    assert translator._folder == str(translation_folder)
    assert translator._default == "en"
    assert translator._match is True

    return


def test_search_key() -> None:
    """Check that a key can be searched in the bbuild messages."""
    # assert that having a wrong key  at root level
    # in the json will raise an error
    key = "toto"
    d = {"toto": {"a": "b"}, "c": "d"}

    with pytest.raises(Exception):
        Translator.search_key(d, key)

    # Search when the key is in a deeper nested level
    key = "nested_key"
    d = {"en": {"level1": {"level2": {"nested_key": "value"}}}}

    with pytest.raises(Exception):
        Translator.search_key(d, key)

    return


def test_search_key_in_second_sibling() -> None:
    """A protected key hiding in the second of two sibling dicts must still be found.

    Regression test: search_key used to return right after the first dict
    child, so any sibling coming after it was never searched.
    """
    key = "toto"
    d = {"first": {"a": "b"}, "second": {"toto": "c"}}

    with pytest.raises(Exception):
        Translator.search_key(d, key)

    return


def test_search_key_in_a_deeper_later_sibling() -> None:
    """A later sibling nested one level deeper must also be found.

    A fix that only widens the search to immediate siblings would still
    miss this case.
    """
    key = "toto"
    d = {"first": {"a": "b"}, "second": {"deeper": {"toto": "c"}}}

    with pytest.raises(Exception):
        Translator.search_key(d, key)

    return


def test_search_key_does_not_raise_when_key_is_absent() -> None:
    """A dictionary that never contains the key must not raise."""
    key = "toto"
    d = {"first": {"a": "b"}, "second": {"deeper": {"c": "d"}}}

    Translator.search_key(d, key)

    return


def test_translator_rejects_a_protected_key_in_a_later_section(tmp_path: Path) -> None:
    """The constructor must refuse a protected key wherever it hides, not just in the first section.

    Args:
        tmp_path: a temporary folder to build a throwaway catalog in
    """
    catalog = {"first": {"a_key": "value"}, "second": {"get": "value"}}
    folder = tmp_path / "message" / "en"
    folder.mkdir(parents=True)
    (folder / "locale.json").write_text(json.dumps(catalog, indent=2))

    with pytest.raises(Exception, match=r"You cannot use the key get"):
        Translator(tmp_path / "message")

    return


def test_sanitize() -> None:
    """Check that the dict are sanitized by the Translator object."""
    # a test dict with many embedded numbered list
    # but also an already existing list
    test = {
        "a": {"0": "b", "1": "c"},
        "d": {"e": {"0": "f", "1": "g"}, "h": "i"},
        "j": ["k", "l"],
    }

    # the sanitize version of this
    result = {
        "a": ["b", "c"],
        "d": {"e": ["f", "g"], "h": "i"},
        "j": ["k", "l"],
    }

    assert Translator.sanitize(test) == result

    return


def test_delete_empty() -> None:
    """Check the translator remove empty keys."""
    test = {"a": "", "b": 1, "c": {"d": ""}, "e": {"f": "", "g": 2}}
    result = {"b": 1, "c": {}, "e": {"g": 2}}

    assert Translator.delete_empty(test) == result

    return


def test_find_target(translation_folder: Path) -> None:
    """Check the targets is found in the folder list and understand ISO 2 codes.

    Args:
        translation_folder: the folder where the language keys are stored
    """
    # test grid
    test_grid = {
        "en": ("en", "en"),
        "en-US": ("en-US", "en"),
        "fr-FR": ("fr-FR", "fr-FR"),
        "fr-CA": ("fr-CA", "fr"),
        "fr": ("fr", "fr"),
        "da": ("da", ""),
    }

    # loop in the test grid to check multiple language combinations
    for k, v in test_grid.items():
        assert Translator.find_target(translation_folder, k) == v

    return


def test_available_locales(translation_folder: Path) -> None:
    """Check the locales are correctly parsed from the existing files.

    Args:
        translation_folder: the folder where the language keys are stored
    """
    # expected grid
    res = ["es", "fr", "fr-FR", "en"]

    # create the translator
    # -en- to -en-
    translator = Translator(translation_folder)

    for locale in res:
        assert locale in translator.available_locales()

    # Check no hidden and protected files are in locales
    locales = translator.available_locales()
    assert not all([(loc.startswith(".") or loc.startswith("_")) for loc in locales])

    return


def test_key_use() -> None:
    """Check that are used at least once."""
    # check key usage method
    # don't test if all keys are translated, crowdin will monitor it
    lib_folder = Path(__file__).parents[2] / "pysepal"

    assert "test_key" in ms.key_use(lib_folder, "ms")

    return


@pytest.fixture(scope="module")
def translation_folder(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate a fully qualified translation folder with limited keys in en, fr and es."""
    # set up the appropriate keys for each language
    keys = {
        "en": {"a_key": "A key", "test_key": "Test key"},
        "fr": {"a_key": "Une clef", "test_key": "Clef de test"},
        "fr-FR": {"a_key": "Une clef", "test_key": "Clef de test"},
        "es": {"a_key": "Una llave"},
    }

    message_dir = tmp_path_factory.mktemp("temp") / "message"
    message_dir.mkdir()
    for lan, d in keys.items():
        folder = message_dir / lan
        folder.mkdir()
        (folder / "locale.json").write_text(json.dumps(d, indent=2))

    return message_dir
