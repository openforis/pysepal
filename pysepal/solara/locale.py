"""Offered-locale matching and presentation for the locale picker."""

from __future__ import annotations

from typing import Dict, Iterable, List

from pysepal._locale import match_offered_locale


def describe_offered_locales(
    offered: Iterable[str], catalog: Iterable[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Pair each offered locale code with a display name and flag.

    ``offered`` comes from the app's message folders and is authoritative:
    every code is returned, because a catalog the app ships must be
    selectable. ``catalog`` only supplies presentation, matched through
    :func:`match_offered_locale`, so a bare ``es`` borrows the name and flag
    of ``es-ES`` while keeping ``es`` as its value -- the value is a folder
    name that :class:`~pysepal.translator.Translator` has to be able to find.

    Args:
        offered: Locale codes the app has catalogs for.
        catalog: Display records, each with ``code``, ``name`` and ``flag``.

    Returns:
        One record per offered code, sorted by display name.
    """
    by_code = {record["code"]: record for record in catalog}
    described = []
    for code in offered:
        match = by_code.get(match_offered_locale(code, by_code))
        described.append(
            {
                "code": code,
                "name": match["name"] if match else code,
                "flag": match["flag"] if match else "",
            }
        )
    return sorted(described, key=lambda record: record["name"])
