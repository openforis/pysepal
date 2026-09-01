"""The shipped demo catalogues bind and are clean.

They are the first applications on the new API, so a problem here is a problem
a module author would hit on day one.
"""

from pathlib import Path

import pytest

import pysepal
from pysepal.i18n import catalog

DEMO_ROOT = Path(pysepal.__file__).parents[1] / "demo_apps"

CATALOGUES = [
    DEMO_ROOT / "solara_map_app" / "component" / "message",
    DEMO_ROOT / "solara_raster_app" / "message",
]


@pytest.mark.parametrize("folder", CATALOGUES, ids=lambda p: p.parent.name)
def test_the_demo_catalogue_binds(folder):
    assert catalog(folder).available_locales() == ("en", "es", "fr")


@pytest.mark.parametrize("folder", CATALOGUES, ids=lambda p: p.parent.name)
def test_the_demo_catalogue_has_no_problems(folder):
    problems = catalog(folder).check()
    assert problems == (), [(p.code, p.locale, p.key) for p in problems]
