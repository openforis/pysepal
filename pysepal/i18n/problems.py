"""Compare a translated locale with English and report what a translator broke.

These never raise. A missing translation is normal; a placeholder typo makes
one message fall back to English. Neither should stop an application starting,
and both should be visible in CI.

A malformed English template is the author's mistake, not a translator's, so
it is left unreported here and surfaces loudly at render instead.
"""

from dataclasses import dataclass
from typing import List, Set, Tuple

from pysepal.i18n.flatten import PLURAL_CATEGORIES
from pysepal.i18n.formatting import placeholders, target_leaf_problem
from pysepal.i18n.loading import LocaleData


@dataclass(frozen=True)
class CatalogProblem:
    """One thing a translated catalogue gets wrong.

    Args:
        code: One of ``missing_key``, ``extra_key``, ``placeholder_mismatch``,
            ``malformed_template``, ``shape_mismatch``,
            ``unsupported_plural_category``, or ``unreadable_locale``. The
            last one is emitted by
            :meth:`~pysepal.i18n.binding.BoundCatalog.check` itself, not by
            :func:`compare_locale`, when the locale fails to load at all.
        locale: The locale the problem is in.
        key: The dotted key it is about, or ``""`` for ``unreadable_locale``,
            which is about the whole locale rather than one key.
        detail: A sentence naming what differs.
    """

    code: str
    locale: str
    key: str
    detail: str


def compare_locale(english: LocaleData, target: LocaleData) -> Tuple[CatalogProblem, ...]:
    """Return every problem in ``target``, measured against English.

    Args:
        english: The authoritative data.
        target: The translated data to check.

    Returns:
        A tuple sorted by ``(code, locale, key)``, empty when the translation
        is clean.
    """
    problems: List[CatalogProblem] = []
    skip_english: Set[str] = set()
    skip_target: Set[str] = set()

    for base in english.plural_keys & set(target.messages):
        problems.append(
            CatalogProblem(
                "shape_mismatch",
                target.code,
                base,
                "English is a plural node; this locale has a plain message",
            )
        )
        skip_english.update(f"{base}.{category}" for category in PLURAL_CATEGORIES)
        skip_target.add(base)

    for base in target.plural_keys & set(english.messages):
        problems.append(
            CatalogProblem(
                "shape_mismatch",
                target.code,
                base,
                "English is a plain message; this locale has a plural node",
            )
        )
        skip_english.add(base)
        skip_target.update(f"{base}.{category}" for category in PLURAL_CATEGORIES)

    for key in english.messages:
        if key in skip_english or key in target.messages:
            continue
        problems.append(CatalogProblem("missing_key", target.code, key, "not translated yet"))

    for key, message in target.messages.items():
        if key in skip_target:
            continue
        if key in english.messages:
            code = target_leaf_problem(english.messages[key], message)
            if code == "malformed_template":
                problems.append(
                    CatalogProblem(
                        code,
                        target.code,
                        key,
                        "the template cannot be parsed, so English stays active",
                    )
                )
            elif code == "placeholder_mismatch":
                wanted = placeholders(english.messages[key])
                given = placeholders(message)
                problems.append(
                    CatalogProblem(
                        code,
                        target.code,
                        key,
                        f"English needs {sorted(wanted)}; this locale has {sorted(given)}. "
                        "English stays active for this message.",
                    )
                )
            continue
        base, _, category = key.rpartition(".")
        if base in english.plural_keys:
            problems.append(
                CatalogProblem(
                    "unsupported_plural_category",
                    target.code,
                    key,
                    f"'{category}' is not a plural category this release supports, "
                    "so it is never used",
                )
            )
        else:
            problems.append(
                CatalogProblem("extra_key", target.code, key, "absent from English, so never used")
            )

    return tuple(sorted(problems, key=lambda problem: (problem.code, problem.locale, problem.key)))
