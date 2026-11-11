import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

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
    [(None, "…"), (0, "0.1 MB"), (200_000, "0.2 MB"), (14_600_000, "14.6 MB"), (2_300_000_000, "2.3 GB")],
)
def test_size_text(n, expected):
    assert size_text(n) == expected


def _flat(node, prefix=""):
    if isinstance(node, dict) and not set(node) <= {"one", "other", "many", "few", "two", "zero"}:
        return {k for key, v in node.items() for k in _flat(v, f"{prefix}{key}.")}
    return {prefix}


def test_every_key_exists_in_each_shipped_language():
    root = Path(__file__).parents[2] / "pysepal" / "message"
    keys = {l: _flat(json.loads((root / l / "project.json").read_text())) for l in ("en", "es", "fr")}
    assert keys["es"] == keys["en"] == keys["fr"]
