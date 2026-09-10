"""Locale no longer resolves through ~/.sepal-ui-config.

Module absence is asserted against *this* checkout rather than with a bare
``ImportError`` -- see ``tests._import_probe`` for why the interpreter at large
is the wrong thing to ask.
"""

import json
from configparser import ConfigParser
from pathlib import Path

import pytest

from pysepal.translator import Translator
from tests._import_probe import shipped_locations


@pytest.fixture
def messages(tmp_path: Path) -> Path:
    keys = {"en": {"test_key": "Test key"}, "fr-FR": {"test_key": "Clef de test"}}
    folder = tmp_path / "message"
    folder.mkdir()
    for lang, values in keys.items():
        (folder / lang).mkdir()
        (folder / lang / "locale.json").write_text(json.dumps(values, indent=2))
    return folder


@pytest.fixture
def machine_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ~/.sepal-ui-config that sets locale to fr-FR, wired into the bound name.

    ``monkeypatch.setenv("HOME", ...)`` would not reach this: translator.py binds
    ``config_file`` into its own module namespace at import time, so patching the
    env var lands too late. Patch the name actually bound in the module instead.
    ``raising=False`` covers both sides of the fix: the attribute exists before
    it and is gone after.
    """
    config_path = tmp_path / ".sepal-ui-config"
    config = ConfigParser()
    config.add_section("sepal-ui")
    config.set("sepal-ui", "locale", "fr-FR")
    with config_path.open("w") as f:
        config.write(f)
    monkeypatch.setattr("pysepal.translator.translator.config_file", config_path, raising=False)
    return config_path


def test_untargeted_translator_ignores_a_machine_config(messages, machine_config):
    assert Translator(messages).test_key == "Test key"


def test_find_target_without_a_target_is_english(messages, machine_config):
    assert Translator.find_target(messages, "") == ("", "en")


def test_explicit_target_still_wins(messages):
    assert Translator(messages, "fr-FR").test_key == "Clef de test"


def test_translator_module_no_longer_imports_the_config():
    import pysepal.translator.translator as mod

    assert not hasattr(mod, "config_file")


def test_module_l10n_entry_point_is_gone():
    shipped = shipped_locations("pysepal.bin.module_l10n")
    assert shipped == [], shipped
