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
    DEMO_ROOT / "solara_aoi_app" / "message",
    DEMO_ROOT / "solara_vector_app" / "message",
]


@pytest.mark.parametrize("folder", CATALOGUES, ids=lambda p: p.parent.name)
def test_the_demo_catalogue_binds(folder):
    assert catalog(folder).available_locales() == ("en", "es", "fr")


@pytest.mark.parametrize("folder", CATALOGUES, ids=lambda p: p.parent.name)
def test_the_demo_catalogue_has_no_problems(folder):
    problems = catalog(folder).check()
    assert problems == (), [(p.code, p.locale, p.key) for p in problems]


def test_a_demo_shows_the_plural_selection_in_every_locale():
    """The demos are the reference; a feature no demo uses is a feature nobody copies.

    ``one``/``other`` is the part of the catalogue format an author is least
    likely to reach for on their own, so it has to be visible in a shipped app.
    """
    messages = catalog(DEMO_ROOT / "solara_raster_app" / "message")

    for locale in messages.available_locales():
        singular = messages._resolve(locale, "toasts.cleared", count=1)
        plural = messages._resolve(locale, "toasts.cleared", count=3)
        # the wording has to change, not only the number: a flat
        # "{count} layers removed" would pass a digits-only comparison
        assert singular.replace("1", "") != plural.replace("3", ""), locale


def test_french_demo_zero_preserves_the_count():
    messages = catalog(DEMO_ROOT / "solara_raster_app" / "message")
    assert messages._resolve("fr", "toasts.cleared", count=0) == "0 couche supprimée"
