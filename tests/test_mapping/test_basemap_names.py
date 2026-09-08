"""No mapping test may hard-code a basemap that xyzservices can withdraw.

Issue #1044. ``get_xyz_dict`` keeps a provider only while ``requires_token()``
is false, so any provider xyzservices decides needs a key leaves
``basemap_tiles`` on the next release and every test naming it starts raising
``ValueError: Basemap can only be one of the following``. 2026.9.1 did exactly
that to the whole CARTO family, breaking ``test_SepalMap::test_init`` on all
three Python versions.

pysepal #1035 saw this coming and took the library off those names, but left
the tests that pass them as explicit basemaps. This guard is what stops the
next one being written: only the entries pysepal defines itself in
``xyz_tiles`` are ours to rely on.
"""

import ast
from pathlib import Path

import pytest

from pysepal.mapping.basemaps import get_xyz_dict, xyz_tiles

# This module names providers in its own failure message, so it cannot scan itself.
MAPPING_TESTS = sorted(
    p for p in Path(__file__).parent.glob("test_*.py") if p.name != Path(__file__).name
)


def _pysepal_owned() -> set:
    """The basemap keys and layer names pysepal ships, which cannot disappear."""
    return set(xyz_tiles) | {entry["name"] for entry in xyz_tiles.values()}


def _string_constants(path: Path) -> set:
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


@pytest.mark.parametrize("path", MAPPING_TESTS, ids=lambda p: p.name)
def test_no_mapping_test_hard_codes_an_upstream_basemap(path: Path) -> None:
    upstream = set(get_xyz_dict(free_only=False))
    named = (_string_constants(path) & upstream) - _pysepal_owned()

    assert not named, (
        f"{path.name} names {sorted(named)}, which xyzservices owns. Any of these "
        f"leaves basemap_tiles the moment upstream marks it as needing a key. "
        f"Use an xyz_tiles key instead and resolve the layer name through "
        f"basemap_tiles[key].name."
    )
