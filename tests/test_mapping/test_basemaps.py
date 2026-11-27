"""Test the basemaps registered in the SepalMap."""

import re

import pytest
from mapframe import Basemap
from xyzservices import TileProvider

from pysepal import mapping as sm
from pysepal.mapping import basemaps
from pysepal.mapping.basemaps import (
    BASEMAP_NAMES,
    basemap_label,
    get_basemap,
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


def test_the_leaflet_tables_are_gone() -> None:
    """The basemaps are MapLibre sources now; the ipyleaflet tile layers went with the map."""
    assert not hasattr(basemaps, "basemap_tiles")
    assert not hasattr(basemaps, "xyz_to_leaflet")


def test_basemap_names_cover_the_free_providers() -> None:
    # only pysepal's own entries are guaranteed to be there; the xyzservices
    # ones come and go with the upstream release, minus those MapLibre cannot draw.
    assert all(key in BASEMAP_NAMES for key in xyz_tiles)
    drawable = set()
    for provider in sm.basemaps.get_xyz_dict().values():
        try:
            Basemap.from_xyz(provider)
        except ValueError:
            continue
        drawable.add(provider.name)
    assert drawable <= set(BASEMAP_NAMES)


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


def test_a_subdomain_template_draws_on_every_subdomain():
    assert get_basemap("OpenStreetMap").tiles == tuple(
        f"https://{s}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png" for s in "abc"
    )


def test_a_provider_maplibre_cannot_draw_is_left_out(monkeypatch):
    odd = TileProvider(name="Odd", url="https://t.test/{z}/{x}/{y}/{ext}", attribution="")
    monkeypatch.setattr(basemaps, "get_xyz_dict", lambda: {"Odd": odd})
    assert "Odd" not in basemaps._build_sources()


def test_unknown_name_lists_the_valid_ones():
    with pytest.raises(ValueError, match="SEPAL_LIGHT"):
        get_basemap("no such basemap")
