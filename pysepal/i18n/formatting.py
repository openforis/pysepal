"""Validate the named placeholders accepted in message templates."""

from string import Formatter
from typing import FrozenSet, Optional, Set


def placeholders(message: str) -> Optional[FrozenSet[str]]:
    """Return field names, or None for unsupported template syntax.

    Fields are simple names. Escaped braces are literal text. Positional
    fields are returned as numbers so English validation can name that error.
    Object traversal, conversions and format specifications are not part of
    the message language; callers format values before passing them to msg().
    """
    names: Set[str] = set()
    auto = 0
    try:
        for _, field, spec, conversion in Formatter().parse(message):
            if field is None:
                continue
            if spec or conversion is not None:
                return None
            if field == "":
                names.add(str(auto))
                auto += 1
            elif field.isidentifier() or field.isdigit():
                names.add(field)
            else:
                return None
    except ValueError:
        return None
    return frozenset(names)


def target_leaf_problem(english: str, target: str, *, plural: bool = False) -> Optional[str]:
    """Return a template or argument mismatch, allowing count in any plural form."""
    given = placeholders(target)
    if given is None:
        return "malformed_template"
    wanted = placeholders(english)
    if wanted is None:
        return "malformed_template"
    if plural:
        given = given - {"count"}
        wanted = wanted - {"count"}
    if wanted != given:
        return "placeholder_mismatch"
    return None
