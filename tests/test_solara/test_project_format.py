"""The project manager's text formatters and its translations."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from pysepal import message
from pysepal.i18n import catalog
from pysepal.solara.components.project._format import relative_time, size_text

NOW = datetime(2026, 1, 10, 12, 0, 0)


@pytest.mark.parametrize(
    "delta,expected",
    [
        (timedelta(seconds=-30), "just now"),
        (timedelta(seconds=59), "just now"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(minutes=29), "29 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=13), "13 hours ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=8), "8 days ago"),
    ],
)
def test_relative_time(delta, expected):
    assert relative_time(NOW - delta, NOW) == expected


def test_relative_time_of_an_aware_time_against_a_naive_now():
    assert relative_time(NOW.astimezone() - timedelta(minutes=29), NOW) == "29 minutes ago"


@pytest.mark.parametrize(
    "n,expected",
    [
        (None, "…"),
        (0, "0.1 MB"),
        (200_000, "0.2 MB"),
        (14_600_000, "14.6 MB"),
        (2_300_000_000, "2.3 GB"),
        (999_999_999, "1.0 GB"),
    ],
)
def test_size_text(n, expected):
    assert size_text(n) == expected


def test_es_and_fr_translate_every_project_message():
    """Missing or extra keys, plural forms and placeholders, as pysepal's own check sees them."""
    problems = catalog(Path(message.__file__).parent).check()
    assert [
        p
        for p in problems
        if p.locale in ("es", "fr")
        and (p.key.startswith("project.") or p.code == "unreadable_locale")
    ] == []
