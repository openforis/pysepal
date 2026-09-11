"""One locale algorithm for pysepal: normalisation and offered-code matching.

It lives above :mod:`pysepal.solara` so the catalogue loader, the Solara locale
surface and the Python side of ``LocaleSelect`` all resolve a code the same
way. ``Translator.find_target`` and the old ``match_offered_locale`` disagreed,
so a ``pt`` request against a ``pt-BR`` catalogue could depend on the order the
filesystem listed the directories in.

``LocaleSelect.vue`` carries a JavaScript transcription of the same rules,
because the browser resolves local storage and ``navigator.language`` before
Python can act. ``tests/fixtures/locale_matching.json`` holds them in parity.
"""

from typing import Dict, Iterable


def normalize_locale(code: str) -> str:
    """Return ``code`` in canonical IETF BCP 47 casing.

    ``_`` becomes ``-``; the primary subtag is lowercased; a four-letter
    alphabetic subtag is a script and is title-cased; a two-letter alphabetic
    subtag is a region and is uppercased; anything else is lowercased.

    Args:
        code: A locale code in any casing, with ``-`` or ``_`` separators.

    Returns:
        The canonical spelling, or ``""`` when ``code`` is empty.
    """
    if not code:
        return ""
    primary, *rest = code.replace("_", "-").split("-")
    canonical = [primary.lower()]
    for subtag in rest:
        if len(subtag) == 4 and subtag.isalpha():
            canonical.append(subtag.title())
        elif len(subtag) == 2 and subtag.isalpha():
            canonical.append(subtag.upper())
        else:
            canonical.append(subtag.lower())
    return "-".join(canonical)


def match_offered_locale(candidate: str, offered: Iterable[str]) -> str:
    """Return the code from ``offered`` that best matches ``candidate``.

    Comparison is case-insensitive and treats ``_`` as ``-``. Preference is an
    exact match, then the bare primary subtag, then the first offered variant
    sharing the primary subtag, in the order given. Fixing that order is the
    caller's job: directory discovery sorts, so the filesystem cannot decide a
    language, while a curated table keeps its curation --
    ``pysepal/data/locale.parquet`` lists ``es-ES`` ahead of nineteen regional
    variants for a reason. ``navigator.language`` reports
    ``es-CL`` where an app ships ``es``, and a catalogue may ship ``pt-BR``
    where the browser reports ``pt``; both resolve rather than fall through to
    English.

    Args:
        candidate: The code to match, in IETF BCP 47.
        offered: The codes to match against. Their original spelling is
            returned, because each one is a message directory name.

    Returns:
        The matching offered code, or ``""`` so callers can try their next
        source.
    """
    wanted = normalize_locale(candidate)
    if not wanted:
        return ""

    by_canonical: Dict[str, str] = {}
    for code in offered:
        by_canonical.setdefault(normalize_locale(code), code)

    if wanted in by_canonical:
        return by_canonical[wanted]
    primary = wanted.split("-")[0]
    if primary in by_canonical:
        return by_canonical[primary]
    return next(
        (code for canonical, code in by_canonical.items() if canonical.split("-")[0] == primary),
        "",
    )
