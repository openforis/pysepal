"""Module to load basemaps from different providers."""

import logging
import os
from typing import Optional

from mapframe import Basemap
from xyzservices import TileProvider
from xyzservices import providers as xyz

log = logging.getLogger("sepalui.mapping")

# CARTO watermarks its raster tiles when they are requested without an API key. The
# key is a deployment secret, so it arrives through the environment and never ships in
# the package; without it the backgrounds fall back to a keyless provider.
CARTODB_BASEMAP_KEY: str = os.getenv("CARTODB_BASEMAP_KEY", "")
"API key for the CARTO backgrounds. Unset means the keyless Esri fallback."

ESRI_LIGHT: str = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
ESRI_DARK: str = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"

BASEMAP_LIGHT: str = (
    f"https://basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}.png?key={CARTODB_BASEMAP_KEY}"
    if CARTODB_BASEMAP_KEY
    else ESRI_LIGHT
)
"URL template of the light background basemap."

BASEMAP_DARK: str = (
    f"https://basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png?key={CARTODB_BASEMAP_KEY}"
    if CARTODB_BASEMAP_KEY
    else ESRI_DARK
)
"URL template of the dark background basemap."

# Tied to the key so the credit can never drift from the provider actually serving the
# tiles; CARTO's free tier is granted in exchange for it staying visible.
BASEMAP_ATTRIBUTION: str = "CARTO, OpenStreetMap" if CARTODB_BASEMAP_KEY else "Esri"
"Attribution of the background basemaps."

xyz_tiles: dict = {
    "SEPAL_LIGHT": {
        "url": BASEMAP_LIGHT,
        "attribution": BASEMAP_ATTRIBUTION,
        "name": "SEPAL Light",
    },
    "SEPAL_DARK": {
        "url": BASEMAP_DARK,
        "attribution": BASEMAP_ATTRIBUTION,
        "name": "SEPAL Dark",
    },
    "OpenStreetMap": {
        "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "OpenStreetMap",
        "name": "OpenStreetMap",
    },
    "ROADMAP": {
        "url": "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "name": "Google Maps",
    },
    "SATELLITE": {
        "url": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "name": "Google Satellite",
    },
    "TERRAIN": {
        "url": "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "name": "Google Terrain",
    },
    "HYBRID": {
        "url": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        "attribution": "Google",
        "name": "Google Satellite",
    },
}
"Custom XYZ tile services."


def get_xyz_dict(
    free_only: bool = True,
    _collection: Optional[dict] = None,
    _output: Optional[dict] = None,
) -> dict:
    """Returns a dictionary of xyz services.

    Args:
        free_only: Whether to return only free xyz tile services that do not require an access token.
        _collection: the collection to anylize (subset of :code:`xyz`)
        _output: the dict to use as an output (mutable object)

    Returns:
        A dictionary of xyz services.
    """
    # the 2 following lies avoid to display xyz descriptor in the method documentation
    # do not replace in the prototype default values
    _collection = xyz if _collection is None else _collection
    _output = {} if _output is None else _output

    for v in _collection.values():
        if isinstance(v, TileProvider):
            if not (v.requires_token() and free_only):
                _output[v.name] = v
        else:  # it's a Bunch
            get_xyz_dict(free_only, v, _output)

    return _output


_DEFAULT_MAX_ZOOM = 22


def _build_sources() -> dict[str, tuple[Basemap, str]]:
    """Each basemap MapLibre can draw, with its label; pysepal's own come first."""
    sources = {
        key: (
            Basemap(
                tiles=(entry["url"],), attribution=entry["attribution"], max_zoom=_DEFAULT_MAX_ZOOM
            ),
            entry["name"],
        )
        for key, entry in xyz_tiles.items()
    }
    excluded = []
    for provider in get_xyz_dict().values():
        try:
            sources[provider.name] = (Basemap.from_xyz(provider), provider.name)
        except ValueError:
            excluded.append(provider.name)
    if excluded:
        log.debug("Basemaps MapLibre cannot draw as XYZ: %s", ", ".join(excluded))
    return sources


_SOURCES: dict[str, tuple[Basemap, str]] = _build_sources()

BASEMAP_NAMES: tuple[str, ...] = tuple(_SOURCES)
"Names of the basemaps :func:`get_basemap` accepts."


def get_basemap(name: str) -> Basemap:
    """Return a basemap by name, ready for the MapLibre map.

    Args:
        name: one of :data:`BASEMAP_NAMES`.

    Returns:
        The basemap.

    Raises:
        ValueError: when the name is unknown or the provider cannot be drawn by MapLibre.
    """
    if name not in _SOURCES:
        raise ValueError(f"Basemap can only be one of the following: {', '.join(BASEMAP_NAMES)}")
    return _SOURCES[name][0]


def basemap_label(name: str) -> str:
    """Return the display name of a basemap.

    Args:
        name: one of :data:`BASEMAP_NAMES`.

    Returns:
        The label to show in the picker.

    Raises:
        ValueError: when the name is unknown.
    """
    if name not in _SOURCES:
        raise ValueError(f"Basemap can only be one of the following: {', '.join(BASEMAP_NAMES)}")
    return _SOURCES[name][1]
