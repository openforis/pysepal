"""Unit tests for tests._janitor."""

from __future__ import annotations

import argparse
import datetime as dt
from unittest.mock import MagicMock

import ee
import pytest

from tests import _janitor


def _rfc3339(moment: dt.datetime) -> str:
    """Render a datetime in the format GEE returns in updateTime."""
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def test_parse_max_age_hours():
    assert _janitor._parse_max_age("24h") == dt.timedelta(hours=24)


def test_parse_max_age_days():
    assert _janitor._parse_max_age("7d") == dt.timedelta(days=7)


def test_parse_max_age_zero():
    assert _janitor._parse_max_age("0") == dt.timedelta(0)


def test_parse_max_age_invalid():
    with pytest.raises(argparse.ArgumentTypeError):
        _janitor._parse_max_age("7x")


def test_parse_max_age_negative_rejected():
    with pytest.raises(argparse.ArgumentTypeError):
        _janitor._parse_max_age("-1h")


def test_list_stale_filters_by_age():
    now = dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.timezone.utc)
    list_fn = MagicMock(
        return_value={
            "assets": [
                {
                    "name": "projects/x/assets/pysepal-tests/sepal-ui-aaa",
                    "updateTime": _rfc3339(now - dt.timedelta(hours=48)),
                },
                {
                    "name": "projects/x/assets/pysepal-tests/sepal-ui-bbb",
                    "updateTime": _rfc3339(now - dt.timedelta(hours=1)),
                },
            ]
        }
    )
    stale = _janitor._list_stale(
        "projects/x/assets/pysepal-tests",
        dt.timedelta(hours=24),
        now=now,
        list_fn=list_fn,
    )
    assert len(stale) == 1
    assert stale[0]["id"].endswith("sepal-ui-aaa")


def test_list_stale_max_age_zero_returns_all():
    now = dt.datetime(2026, 4, 20, 12, 0, tzinfo=dt.timezone.utc)
    list_fn = MagicMock(
        return_value={
            "assets": [
                {
                    "name": "projects/x/assets/pysepal-tests/sepal-ui-aaa",
                    "updateTime": _rfc3339(now - dt.timedelta(minutes=1)),
                },
            ]
        }
    )
    stale = _janitor._list_stale(
        "projects/x/assets/pysepal-tests",
        dt.timedelta(0),
        now=now,
        list_fn=list_fn,
    )
    assert len(stale) == 1


def test_list_stale_container_missing_returns_empty():
    list_fn = MagicMock(
        side_effect=ee.EEException("Asset 'projects/x/assets/pysepal-tests' not found")
    )
    stale = _janitor._list_stale(
        "projects/x/assets/pysepal-tests",
        dt.timedelta(0),
        list_fn=list_fn,
    )
    assert stale == []


def test_list_stale_permission_error_is_reraised():
    list_fn = MagicMock(side_effect=ee.EEException("Permission denied for user"))
    with pytest.raises(ee.EEException):
        _janitor._list_stale(
            "projects/x/assets/pysepal-tests",
            dt.timedelta(0),
            list_fn=list_fn,
        )


class _FakeAssets:
    """In-memory stand-in for the ``ee.data`` asset calls used by delete_recursive.

    ``deleteAsset`` refuses a folder that still has children, as GEE does.
    ``late`` maps a folder to children that appear after its first listing.
    """

    def __init__(self, assets: dict[str, str], late=None):
        self.assets = dict(assets)
        self.late = dict(late or {})

    def _children(self, parent: str) -> list[str]:
        return sorted(n for n in self.assets if n.rpartition("/")[0] == parent)

    def getAsset(self, name: str) -> dict:
        return {"name": name, "type": self.assets[name]}

    def listAssets(self, params: dict) -> dict:
        parent = params["parent"]
        response = {"assets": [{"name": n, "type": self.assets[n]} for n in self._children(parent)]}
        for name, kind in self.late.pop(parent, {}).items():
            self.assets[name] = kind
        return response

    def deleteAsset(self, name: str) -> None:
        if self._children(name):
            raise ee.EEException(f"Before trying to delete an asset, delete its children: '{name}'")
        del self.assets[name]


@pytest.fixture
def fake_assets(monkeypatch):
    """Patch ``ee.data`` with a fake asset store and return a factory for it."""
    monkeypatch.setattr(_janitor.time, "sleep", lambda _: None)

    def _install(*args, **kwargs) -> _FakeAssets:
        fake = _FakeAssets(*args, **kwargs)
        for name in ("getAsset", "listAssets", "deleteAsset"):
            monkeypatch.setattr(ee.data, name, getattr(fake, name))
        return fake

    return _install


def test_delete_recursive_lists_again_when_a_child_appears(fake_assets):
    root = "projects/x/assets/pysepal-tests/sepal-ui-aaa"
    fake = fake_assets(
        {root: "FOLDER", f"{root}/table": "TABLE"},
        late={root: {f"{root}/image": "IMAGE"}},
    )

    _janitor.delete_recursive(root)

    assert fake.assets == {}


def test_delete_recursive_gives_up_after_bounded_attempts(fake_assets, monkeypatch):
    root = "projects/x/assets/pysepal-tests/sepal-ui-aaa"
    fake = fake_assets({root: "FOLDER"})
    # a child that every listing misses, so the folder can never be deleted
    hidden = f"{root}/hidden"
    fake.assets[hidden] = "TABLE"
    monkeypatch.setattr(ee.data, "listAssets", lambda params: {"assets": []})

    with pytest.raises(RuntimeError, match="still has children"):
        _janitor.delete_recursive(root)

    assert root in fake.assets


def test_delete_recursive_reraises_other_errors(fake_assets, monkeypatch):
    root = "projects/x/assets/pysepal-tests/sepal-ui-aaa"
    fake = fake_assets({root: "FOLDER"})

    def _denied(name: str) -> None:
        raise ee.EEException("Permission denied")

    monkeypatch.setattr(ee.data, "deleteAsset", _denied)

    with pytest.raises(ee.EEException, match="Permission denied"):
        _janitor.delete_recursive(root)

    assert root in fake.assets
