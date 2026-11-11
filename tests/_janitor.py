"""Janitor for pysepal GEE test assets.

Lists children of `projects/<project>/assets/pysepal-tests/` and deletes any
older than --max-age. Dry-run by default.

Usage:
    python -m tests._janitor                    # dry-run, 24h filter
    python -m tests._janitor --yes              # delete assets older than 24h
    python -m tests._janitor --max-age=0 --yes  # delete everything
    python -m tests._janitor --max-age=7d --yes # delete assets older than 7 days
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from typing import Any, Callable, Optional

import ee


def _parse_max_age(raw: str) -> dt.timedelta:
    """Parse strings like '24h', '7d', '0' into a timedelta."""
    if raw == "0":
        return dt.timedelta(0)
    if not raw:
        raise argparse.ArgumentTypeError("max-age may not be empty")
    unit = raw[-1].lower()
    amount_str = raw[:-1]
    try:
        amount = int(amount_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid max-age amount: {amount_str!r}") from exc
    if amount < 0:
        raise argparse.ArgumentTypeError("max-age amount must be non-negative")
    if unit == "h":
        return dt.timedelta(hours=amount)
    if unit == "d":
        return dt.timedelta(days=amount)
    raise argparse.ArgumentTypeError(f"Invalid max-age unit: {unit!r}. Use 'h' or 'd' or pass '0'.")


def _container_path() -> str:
    """Return the asset path of the pysepal-tests container in the current project."""
    project_id = ee.data.getProjectConfig()["name"].split("/")[1]
    return f"projects/{project_id}/assets/pysepal-tests"


_DELETE_ATTEMPTS = 3
_RETRY_DELAY = 5  # seconds


def delete_recursive(asset_id: str) -> None:
    """Delete an asset, and everything under it when it is a folder.

    Children go first: Earth Engine refuses to delete a folder that still has
    contents. Replaces ``pysepal.scripts.gee.delete_assets``, removed in 4.0 --
    which took a ``dry_run`` flag it compared with ``is True``, so any truthy
    value that was not the singleton armed a real delete.

    Args:
        asset_id: the full asset name, e.g. ``projects/p/assets/folder``.

    Raises:
        RuntimeError: the folder still has children after ``_DELETE_ATTEMPTS``
            listings.
    """
    if ee.data.getAsset(asset_id)["type"] != "FOLDER":
        ee.data.deleteAsset(asset_id)
        return

    # A child can appear after the listing (a late export, or a listing that
    # lags behind a finished task), so list again when GEE refuses the delete.
    for attempt in range(_DELETE_ATTEMPTS):
        if attempt:
            time.sleep(_RETRY_DELAY)
        for child in ee.data.listAssets({"parent": asset_id}).get("assets", []):
            delete_recursive(child["name"])
        try:
            ee.data.deleteAsset(asset_id)
            return
        except ee.EEException as exc:
            if "delete its children" not in str(exc):
                raise
            error = exc

    raise RuntimeError(
        f"{asset_id} still has children after {_DELETE_ATTEMPTS} attempts"
    ) from error


def _parse_update_time(raw: Any) -> Optional[dt.datetime]:
    """Parse a GEE updateTime (RFC3339 string or millis int) into a UTC datetime."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if isinstance(raw, (int, float)):
        return dt.datetime.fromtimestamp(float(raw) / 1000.0, tz=dt.timezone.utc)
    return None


def _list_stale(
    container: str,
    max_age: dt.timedelta,
    now: Optional[dt.datetime] = None,
    list_fn: Callable = ee.data.listAssets,
) -> list[dict]:
    """Return assets under `container` whose updateTime is older than now - max_age."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cutoff = now - max_age
    try:
        response = list_fn({"parent": container})
    except ee.EEException as exc:
        msg = str(exc).lower()
        if "not found" in msg or "does not exist" in msg:
            return []
        raise

    stale: list[dict] = []
    for asset in response.get("assets", []):
        updated = _parse_update_time(asset.get("updateTime") or asset.get("update_time"))
        if updated is None:
            continue
        if updated <= cutoff:
            stale.append({"id": asset["name"], "updated": updated})
    return stale


def main(argv: Optional[list[str]] = None) -> int:
    """Run the janitor CLI."""
    parser = argparse.ArgumentParser(
        description="Clean stale pysepal test assets under pysepal-tests/."
    )
    parser.add_argument(
        "--max-age",
        type=_parse_max_age,
        default=dt.timedelta(hours=24),
        help="Skip assets younger than this. Format: '24h', '7d', or '0'. Default: 24h.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually delete. Without this flag, prints what would be deleted.",
    )
    args = parser.parse_args(argv)

    if not ee.data.is_initialized():
        ee.Initialize()

    container = _container_path()
    stale = _list_stale(container, args.max_age)

    if not stale:
        print(f"No stale assets in {container} (max-age={args.max_age}).")
        return 0

    print(f"Found {len(stale)} stale folder(s) under {container}:")
    for asset in stale:
        print(f"  {asset['id']}  (updated: {asset['updated'].isoformat()})")

    if not args.yes:
        print("\nDry-run. Pass --yes to delete.")
        return 0

    for asset in stale:
        print(f"Deleting {asset['id']}...")
        delete_recursive(asset["id"])

    print(f"Deleted {len(stale)} folder(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
