"""Text formatters of the project manager: relative times and sizes."""

from datetime import datetime
from typing import Optional

from babel.numbers import format_decimal

from pysepal._locale import normalize_locale
from pysepal.i18n import current_locale
from pysepal.message import msg


def relative_time(when: datetime, now: datetime) -> str:
    """'just now', 'N minutes ago', 'N hours ago' or 'N days ago'. A time a
    little ahead of ``now`` reads 'just now'.
    """
    # Timestamps, so a naive (local) and an aware time compare.
    seconds = max(0, int(now.timestamp() - when.timestamp()))
    if seconds < 60:
        return msg("project.ago_now")
    if seconds < 3600:
        return msg("project.ago_minutes", count=seconds // 60)
    if seconds < 86400:
        return msg("project.ago_hours", count=seconds // 3600)
    return msg("project.ago_days", count=seconds // 86400)


def size_text(n: Optional[int]) -> str:
    """A size on disk: MB below 1 GB (never under 0.1), GB from 1 GB, one
    decimal in the current locale. ``None`` (not measured yet) is an ellipsis.
    """
    if n is None:
        return "…"
    locale = normalize_locale(current_locale() or "en").replace("-", "_")

    def num(x: float) -> str:
        return format_decimal(x, format="0.0", locale=locale)

    return f"{num(n / 1e9)} GB" if n >= 1e9 else f"{num(max(n / 1e6, 0.1))} MB"
