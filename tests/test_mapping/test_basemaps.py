"""Test the basemaps registered in the SepalMap."""

from ipyleaflet import TileLayer

from pysepal import mapping as sm
from pysepal.mapping.basemaps import xyz_tiles


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
