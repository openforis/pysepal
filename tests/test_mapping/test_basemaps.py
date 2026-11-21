"""Test the basemaps registered in the SepalMap."""

import re

import pytest
from ipyleaflet import TileLayer
from pysepal_map import Basemap
from xyzservices import TileProvider

from pysepal import mapping as sm
from pysepal.mapping import basemaps
from pysepal.mapping.basemaps import (
    BASEMAP_NAMES,
    basemap_label,
    get_basemap,
    tile_urls,
    xyz_tiles,
)

PLACEHOLDER = re.compile(r"\{[^}]*\}")


def test_get_xyz_dict() -> None:
    """Check the free set is the token-free subset of everything xyzservices ships.

    Asserted as a property rather than against named providers: xyzservices
    moves providers behind an API key between releases -- 2026.9.1 did it to
    the whole CARTO family -- so any name hard-coded here is a future failure
    (#1044).
    """
    free = sm.basemaps.get_xyz_dict()
    every = sm.basemaps.get_xyz_dict(free_only=False)

    assert free, "no keyless provider survived the filter"
    assert set(free) <= set(every)
    assert not any(p.requires_token() for p in free.values())
    assert any(
        p.requires_token() for p in every.values()
    ), "free_only=False must also return the providers that need a key"

    return


def test_xyz_to_leaflet() -> None:
    """Check the maps can be transformed in TileLayer."""
    basemaps = sm.basemaps.xyz_to_leaflet()

    # only pysepal's own entries are guaranteed to be there; the xyzservices
    # ones come and go with the upstream release.
    assert all(key in basemaps for key in xyz_tiles)
    assert set(sm.basemaps.get_xyz_dict()) <= set(basemaps)

    for tile in basemaps.values():
        assert isinstance(tile, TileLayer)

    return


@pytest.mark.parametrize("name", BASEMAP_NAMES)
def test_every_basemap_has_maplibre_tiles(name):
    basemap = get_basemap(name)
    assert isinstance(basemap, Basemap) and basemap.tiles
    for tile in basemap.tiles:
        assert set(PLACEHOLDER.findall(tile)) <= {"{z}", "{x}", "{y}"}
    assert 0 <= basemap.max_zoom <= 24
    assert basemap_label(name)


def test_sepal_backgrounds_use_the_configured_urls():
    assert get_basemap("SEPAL_LIGHT").tiles == (basemaps.BASEMAP_LIGHT,)
    assert get_basemap("SEPAL_DARK").tiles == (basemaps.BASEMAP_DARK,)
    assert get_basemap("SEPAL_LIGHT").attribution == basemaps.BASEMAP_ATTRIBUTION
    assert basemap_label("SEPAL_DARK") == "SEPAL Dark"


def test_pysepal_entries_come_first_in_the_same_order():
    assert list(BASEMAP_NAMES[: len(xyz_tiles)]) == list(xyz_tiles)


def test_tile_urls_expands_subdomains():
    assert tile_urls("https://{s}.t.test/{z}/{x}/{y}{r}.png", "ab") == (
        "https://a.t.test/{z}/{x}/{y}.png",
        "https://b.t.test/{z}/{x}/{y}.png",
    )
    assert tile_urls("https://{s}.t.test/{z}", ["x", "y", "z"]) == tuple(
        f"https://{c}.t.test/{{z}}" for c in "xyz"
    )
    assert tile_urls("https://t.test/{z}/{x}/{y}") == ("https://t.test/{z}/{x}/{y}",)


def _provider(**options) -> TileProvider:
    return TileProvider(
        name="Synthetic",
        url="https://{s}.synthetic.test/{variant}/{z}/{x}/{y}.png",
        attribution="synthetic",
        variant="base",
        **options,
    )


def test_provider_subdomains_are_all_kept():
    source = basemaps._provider_source(_provider(subdomains="12"))
    assert source["tiles"] == (
        "https://1.synthetic.test/base/{z}/{x}/{y}.png",
        "https://2.synthetic.test/base/{z}/{x}/{y}.png",
    )


def test_tms_providers_are_excluded():
    assert basemaps._provider_source(_provider(tms=True)) is None


def test_unfilled_placeholders_are_excluded():
    odd = TileProvider(name="Odd", url="https://t.test/{z}/{x}/{y}/{ext}", attribution="")
    assert basemaps._provider_source(odd) is None


def test_unknown_name_lists_the_valid_ones():
    with pytest.raises(ValueError, match="SEPAL_LIGHT"):
        get_basemap("no such basemap")
