"""Translations select their own cardinal forms and fall back in English."""

from decimal import Decimal

import pytest

from pysepal.i18n import MessageFormatError, catalog


def test_french_zero_uses_the_translated_one_form(build_catalog):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "fr": {"app": {"models": {"one": "{count} modèle", "other": "{count} modèles"}}},
            }
        )
    )
    assert messages._resolve("fr", "models", count=0) == "0 modèle"


@pytest.mark.parametrize(
    ("count", "form"),
    [
        (1, "one"),
        (2, "few"),
        (5, "many"),
        (21, "one"),
        (0, "many"),
        (Decimal("1.5"), "other"),
    ],
)
def test_russian_cardinal_forms(build_catalog, count, form):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "ru-RU": {
                    "app": {
                        "models": {
                            "one": "{count} one",
                            "few": "{count} few",
                            "many": "{count} many",
                            "other": "{count} other",
                        }
                    }
                },
            }
        )
    )
    assert messages._resolve("ru", "models", count=count) == f"{count} {form}"
    assert messages.check() == ()


@pytest.mark.parametrize(
    ("count", "form"),
    [
        (0, "zero"),
        (1, "one"),
        (2, "two"),
        (3, "few"),
        (11, "many"),
        (100, "other"),
    ],
)
def test_arabic_cardinal_forms(build_catalog, count, form):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "ar-SA": {
                    "app": {
                        "models": {
                            "zero": "{count} zero",
                            "one": "{count} one",
                            "two": "{count} two",
                            "few": "{count} few",
                            "many": "{count} many",
                            "other": "{count} other",
                        }
                    }
                },
            }
        )
    )
    assert messages._resolve("ar", "models", count=count) == f"{count} {form}"
    assert messages.check() == ()


def test_missing_target_form_uses_english_rules_for_the_number(build_catalog):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "fr": {"app": {"models": {"other": "{count} modèles"}}},
            }
        )
    )
    assert messages._resolve("fr", "models", count=0) == "0 models"
    assert messages._resolve("fr", "models", count=1) == "1 model"
    assert messages._resolve("fr", "models", count=2) == "2 modèles"


def test_invalid_target_form_uses_english_rules(build_catalog):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "fr": {
                    "app": {
                        "models": {
                            "one": "{missing} modèle",
                            "other": "{count} modèles",
                        }
                    }
                },
            }
        )
    )
    assert messages._resolve("fr", "models", count=0) == "0 models"
    assert any(p.code == "placeholder_mismatch" and p.key == "models.one" for p in messages.check())


def test_chinese_needs_only_other(build_catalog):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
                "zh-CN": {"app": {"models": {"other": "{count} 模型"}}},
            }
        )
    )
    assert messages._resolve("zh-CN", "models", count=1) == "1 模型"
    assert messages.check() == ()


def test_an_unreadable_target_uses_english_plural_rules(build_catalog):
    folder = build_catalog(
        {
            "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
            "fr": {"app": {"models": {"one": "{count} modèle"}}},
        }
    )
    (folder / "fr" / "app.json").write_text("{invalid JSON")
    assert catalog(folder)._resolve("fr", "models", count=0) == "0 models"


def test_plural_forms_cannot_introduce_new_application_arguments(build_catalog):
    messages = catalog(
        build_catalog(
            {
                "en": {
                    "app": {
                        "models": {
                            "one": "{user}: 1 model",
                            "other": "{user}: {count} models",
                        }
                    }
                },
                "ru-RU": {"app": {"models": {"few": "{admin}: {count} few"}}},
            }
        )
    )
    assert messages._resolve("ru", "models", user="Ana", count=2) == "Ana: 2 models"
    assert any(p.code == "placeholder_mismatch" and p.key == "models.few" for p in messages.check())


@pytest.mark.parametrize("count", ["2", None, True, float("nan"), float("inf")])
def test_invalid_counts_are_application_errors(build_catalog, count):
    messages = catalog(
        build_catalog(
            {
                "en": {"app": {"models": {"one": "1 model", "other": "{count} models"}}},
            }
        )
    )
    with pytest.raises(MessageFormatError, match="count"):
        messages._resolve("en", "models", count=count)
