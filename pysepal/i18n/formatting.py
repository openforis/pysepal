"""Read the placeholders a message template needs."""

from string import Formatter
from typing import FrozenSet, Optional, Set


def placeholders(message: str) -> Optional[FrozenSet[str]]:
    """Return the placeholder names a message needs, or None if it cannot be parsed.

    Args:
        message: A ``str.format`` template.

    Returns:
        The root name of every replacement field: ``{a.b}`` and ``{a[0]}`` both
        contribute ``a``, and each bare ``{}`` contributes its implicit position
        so that losing one positional slot is still a difference. ``None`` when
        the template is malformed -- a translator's mistake to report, not raise.
    """
    names: Set[str] = set()
    auto = 0
    try:
        for _, field, _, _ in Formatter().parse(message):
            if field is None:
                continue
            if field == "":
                names.add(str(auto))
                auto += 1
            else:
                names.add(field.split(".")[0].split("[")[0])
    except ValueError:
        return None
    return frozenset(names)


def target_leaf_problem(english: str, target: str) -> Optional[str]:
    """Return why a translated leaf cannot replace English, or None if it can.

    Args:
        english: The authoritative template.
        target: The translated template offered in its place.

    Returns:
        ``"malformed_template"`` when the target cannot be parsed,
        ``"placeholder_mismatch"`` when its placeholders differ from English's,
        or ``None`` when the target is usable. An English template that cannot
        be parsed imposes no constraint, so a parseable target still wins.
    """
    given = placeholders(target)
    if given is None:
        return "malformed_template"
    wanted = placeholders(english)
    if wanted is not None and wanted != given:
        return "placeholder_mismatch"
    return None
