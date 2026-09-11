"""Cardinal plural categories from Babel's CLDR data."""

import math
from decimal import Decimal
from functools import lru_cache
from numbers import Real
from typing import Any, FrozenSet

from babel import Locale, UnknownLocaleError
from babel.plural import PluralRule

from pysepal._locale import normalize_locale

PLURAL_CATEGORIES = frozenset({"zero", "one", "two", "few", "many", "other"})


@lru_cache(maxsize=128)
def _rule(code: str) -> PluralRule:
    canonical = normalize_locale(code)
    for candidate in (canonical, canonical.split("-")[0], "en"):
        try:
            return Locale.parse(candidate, sep="-").plural_form
        except (UnknownLocaleError, ValueError):
            continue
    raise ValueError(f"No plural rules for {code!r}")


def plural_categories(code: str) -> FrozenSet[str]:
    """Return the cardinal categories a locale can select, including other."""
    return frozenset(_rule(code).tags) | {"other"}


def select_plural_category(code: str, count: Any) -> str:
    """Select a locale's cardinal form for a finite numeric count."""
    if isinstance(count, bool) or not isinstance(count, (Real, Decimal)):
        raise ValueError("count must be a finite number")
    finite = (
        count.is_finite()
        if isinstance(count, Decimal)
        else isinstance(count, int) or math.isfinite(count)
    )
    if not finite:
        raise ValueError("count must be a finite number")
    return _rule(code)(count)
