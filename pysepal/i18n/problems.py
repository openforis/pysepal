"""Compare translated messages with English identities and arguments."""

from dataclasses import dataclass
from typing import Tuple

from pysepal.i18n.formatting import placeholders
from pysepal.i18n.loading import LocaleData, translation_problem
from pysepal.i18n.plurals import plural_categories


@dataclass(frozen=True)
class CatalogProblem:
    """One catalogue problem: code, locale, dotted key and an explanation."""

    code: str
    locale: str
    key: str
    detail: str


def compare_locale(english: LocaleData, target: LocaleData) -> Tuple[CatalogProblem, ...]:
    """Report missing forms, extra keys, shape changes and invalid templates."""
    problems = []
    categories = plural_categories(target.code)
    plain_keys = {
        key for key in english.messages if key.rpartition(".")[0] not in english.plural_keys
    }
    expected = plain_keys | {
        f"{base}.{category}" for base in english.plural_keys for category in categories
    }
    mismatched = (english.plural_keys & target.messages.keys()) | (target.plural_keys & plain_keys)
    for base in mismatched:
        problems.append(
            CatalogProblem(
                "shape_mismatch",
                target.code,
                base,
                "English and the translation disagree on whether this message is plural",
            )
        )

    def shape_changed(key: str) -> bool:
        return key in mismatched or key.rpartition(".")[0] in mismatched

    for key in expected - target.messages.keys():
        if not shape_changed(key):
            problems.append(CatalogProblem("missing_key", target.code, key, "not translated yet"))

    for key, message in target.messages.items():
        if shape_changed(key):
            continue
        if key in expected:
            code = translation_problem(english, key, message)
            if code is not None:
                if code == "malformed_template":
                    detail = "Only named placeholders and escaped braces are supported; English stays active"
                else:
                    base = key.rpartition(".")[0]
                    plural = base in english.plural_keys
                    reference = (
                        english.messages[f"{base}.other"] if plural else english.messages[key]
                    )
                    optional = {"count"} if plural else set()
                    wanted = placeholders(reference) - optional
                    given = placeholders(message) - optional
                    detail = f"English needs {sorted(wanted)}; this locale has {sorted(given)}. English stays active"
                problems.append(CatalogProblem(code, target.code, key, detail))
        elif key.rpartition(".")[0] in english.plural_keys:
            problems.append(
                CatalogProblem(
                    "unsupported_plural_category",
                    target.code,
                    key,
                    f"'{key.rpartition('.')[2]}' is never used by this locale's cardinal rules",
                )
            )
        else:
            problems.append(
                CatalogProblem("extra_key", target.code, key, "absent from English, so never used")
            )
    return tuple(sorted(problems, key=lambda problem: (problem.code, problem.locale, problem.key)))
