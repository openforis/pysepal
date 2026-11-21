"""Module to load basemaps from different providers."""

import logging
import os
import re
from collections.abc import Sequence
from typing import Optional

from box import Box
from ipyleaflet import TileLayer
from pysepal_map import Basemap
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


def xyz_to_leaflet() -> dict:
    """Convert all available xyz tile services to ipyleaflet tile layers.

    Adapted from https://github.com/giswqs/geemap.

    Returns:
        A dictionary of ipyleaflet tile layers.
    """
    leaflet_dict = {}

    for key in xyz_tiles:
        name = xyz_tiles[key]["name"]
        url = xyz_tiles[key]["url"]
        attribution = xyz_tiles[key]["attribution"]
        leaflet_dict[key] = TileLayer(
            url=url, name=name, attribution=attribution, max_zoom=22, base=True
        )

    for item in get_xyz_dict().values():
        leaflet_dict[item.name] = TileLayer(
            url=item.build_url(),
            name=item.name,
            max_zoom=item.get("max_zoom", 22),
            attribution=item.attribution,
            base=True,
        )

    return leaflet_dict


basemap_tiles: Box = Box(xyz_to_leaflet(), frozen_box=True)
"the basemaps list as a box"


_PLACEHOLDER = re.compile(r"\{[^}]*\}")
_DRAWABLE = frozenset({"{z}", "{x}", "{y}", "{s}", "{r}"})
_MAX_ZOOM = 24
_DEFAULT_MAX_ZOOM = 22


def tile_urls(template: str, subdomains: str | Sequence[str] = "abc") -> tuple[str, ...]:
    """Expand a tile URL template into one URL per subdomain.

    Args:
        template: URL with ``{z}``, ``{x}``, ``{y}`` and optionally ``{s}`` and ``{r}``.
        subdomains: the subdomains ``{s}`` stands for, one character each when a string.

    Returns:
        One URL per subdomain with ``{r}`` dropped, or the template alone without ``{s}``.
    """
    template = template.replace("{r}", "")
    if "{s}" not in template:
        return (template,)
    return tuple(template.replace("{s}", sub) for sub in subdomains)


def _provider_source(provider: TileProvider) -> Optional[dict]:
    """Describe a xyzservices provider for MapLibre, or ``None`` when it cannot be drawn."""
    if provider.get("tms"):
        return None
    try:
        template = provider.build_url(fill_subdomain=False)
    except (KeyError, ValueError, IndexError):
        return None
    if set(_PLACEHOLDER.findall(template)) - _DRAWABLE:
        return None
    return {
        "tiles": tile_urls(template, provider.get("subdomains", "abc")),
        "attribution": provider.get("attribution", ""),
        "max_zoom": min(int(provider.get("max_zoom", _DEFAULT_MAX_ZOOM)), _MAX_ZOOM),
        "label": provider.name,
    }


def _build_sources() -> dict[str, dict]:
    sources: dict[str, dict] = {}
    excluded = []
    for key, entry in xyz_tiles.items():
        sources[key] = {
            "tiles": tile_urls(entry["url"]),
            "attribution": entry["attribution"],
            "max_zoom": _DEFAULT_MAX_ZOOM,
            "label": entry["name"],
        }
    for provider in get_xyz_dict().values():
        source = _provider_source(provider)
        if source is None:
            excluded.append(provider.name)
        else:
            sources[provider.name] = source
    if excluded:
        log.debug("Basemaps MapLibre cannot draw as XYZ: %s", ", ".join(excluded))
    return sources


_SOURCES: dict[str, dict] = _build_sources()

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
    source = _SOURCES[name]
    return Basemap(
        tiles=source["tiles"], attribution=source["attribution"], max_zoom=source["max_zoom"]
    )


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
    return _SOURCES[name]["label"]
