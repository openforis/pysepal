"""Read the placeholders a message template needs."""

from string import Formatter
from typing import FrozenSet, Optional, Set

_CONVERSIONS: FrozenSet[str] = frozenset({"s", "r", "a"})
"""The conversions ``str.format`` accepts after ``!``."""


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
    if _scan(message, names, 0) is None:
        return None
    return frozenset(names)


def _scan(message: str, names: Set[str], auto: int) -> Optional[int]:
    """Collect every field name of ``message`` into ``names``.

    ``Formatter().parse`` reports a field's format spec and conversion but does
    not check either, and both can fail only at render:

    - a spec carries replacement fields of its own in ``{name:{width}}``, so
      ``width`` is a value the message needs and the scan recurses into it;
    - ``{name!z}`` parses cleanly and raises inside ``str.format``.

    Missing either one lets a translation pass ``check()`` and then break the
    render, which is the failure the two-layer overlay exists to prevent.

    Args:
        message: A ``str.format`` template, or one template's format spec.
        names: Collected field names; mutated in place.
        auto: The next implicit position, threaded through nested specs so a
            template and its spec cannot both claim position 0.

    Returns:
        The next implicit position, or None when the template is malformed.
    """
    try:
        parsed = list(Formatter().parse(message))
    except ValueError:
        return None

    for _, field, spec, conversion in parsed:
        if conversion is not None and conversion not in _CONVERSIONS:
            return None
        if field is None:
            continue
        if field == "":
            names.add(str(auto))
            auto += 1
        else:
            names.add(field.split(".")[0].split("[")[0])
        if spec:
            nested = _scan(spec, names, auto)
            if nested is None:
                return None
            auto = nested
    return auto


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
