"""Decide how a local raster is coloured when it is served as tiles.

Two ways to paint a raster, both returning the keyword arguments that
``localtileserver.get_leaflet_tile_layer`` expects, so
:meth:`~pysepal.mapping.SepalMap.add_raster` can pick one and stay a single code
path:

- categorical, from an explicit ``{class code: '#rrggbb'}`` mapping
- continuous, stretching a matplotlib colormap across the value range

Everything here is internal to ``add_raster``.
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from pysepal.mapping.tiling import _hash_for_cache, _write_atomically

__all__ = []

log = logging.getLogger("sepalui.mapping.raster_style")

# rio-tiler renders through a 256-entry lookup table, so a class code has to be a
# byte to survive to the tile. Codes outside that range are renumbered instead.
MAX_CLASS_CODE = 255


def _hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convert ``'#rgb'`` or ``'#rrggbb'`` to an ``(r, g, b)`` tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"{hex_color!r} is not a '#rgb' or '#rrggbb' color")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _build_class_colormap(class_colors: dict) -> dict:
    """Build a discrete ``{pixel value: (r, g, b, a)}`` LUT for a categorical raster.

    Only the declared classes are in the LUT, including code 0 -- an area
    calculation treats it as a valid, sampleable class, so it has to be visible.
    Anything absent renders transparent, which rio-tiler already does for an
    unmatched value; padding the LUT out to 256 entries instead would push
    rio-tiler onto its ``make_lut`` path, where a value above 255 wraps into a
    real class and gets painted with that class's color.
    """
    return {int(code): (*_hex_to_rgb(color), 255) for code, color in class_colors.items()}


def _needs_dense_codes(class_colors: dict) -> bool:
    """Whether the class codes have to be renumbered before they can be served."""
    codes = [int(code) for code in class_colors]
    return any(code < 0 or code > MAX_CLASS_CODE for code in codes)


def _densify_class_codes(image: Path, class_colors: dict, cache_dir: Path) -> Tuple[Path, dict]:
    """Rewrite a raster as ``uint8`` with its class codes renumbered from 1.

    A tile is colored through a 256-entry table, so a code outside ``0..255``
    cannot reach the renderer as itself. Renumbering to a dense range is the only
    way to draw such a class; 0 is reserved for the transparent background.

    Args:
        image: the source raster.
        class_colors: the caller's ``{class code: '#rrggbb'}`` mapping.
        cache_dir: where the renumbered copy is kept.

    Returns:
        the path to serve, and the ``class_colors`` restated in the new codes.
    """
    # rasterio stays lazy: importing it costs ~160ms and a GEE-only app that
    # never touches a local raster should not pay that at import time
    import rasterio as rio

    codes = sorted(int(code) for code in class_colors)
    if len(codes) > MAX_CLASS_CODE:
        raise ValueError(
            f"{len(codes)} classes exceed the {MAX_CLASS_CODE} a tile palette can hold"
        )

    dense = {code: position + 1 for position, code in enumerate(codes)}
    renumbered = {dense[code]: class_colors[code] for code in codes}
    for color in renumbered.values():
        _hex_to_rgb(color)  # fail before rewriting a raster for an unusable palette

    # the renumbering depends on which classes were asked for, so the codes are
    # part of the identity: mapping {300, 1024} and later just {1024} produce
    # different pixels, and sharing one file would paint 300 as 1024
    tag = _hash_for_cache(str(image), *(str(code) for code in codes))
    dst = cache_dir / f"{image.name}.{tag}.classes.tif"
    if dst.exists():
        return dst, renumbered

    with rio.open(image) as ds:
        profile = ds.profile | {
            "driver": "GTiff",
            "dtype": "uint8",
            "count": 1,
            "nodata": 0,
            "tiled": True,
            "blockxsize": 512,
            "blockysize": 512,
            "compress": "deflate",
        }
        with _write_atomically(dst) as tmp:
            with rio.open(tmp, "w", **profile) as out:
                for _, window in ds.block_windows(1):
                    source = ds.read(1, window=window)
                    target = np.zeros(source.shape, dtype="uint8")
                    for code, position in dense.items():
                        target[source == code] = position
                    out.write(target, 1, window=window)

    log.info("Renumbered %s to dense uint8 class codes so every class can be drawn.", image)
    return dst, renumbered


def _class_color_kwargs(class_colors: dict) -> Optional[dict]:
    """Return the ``get_leaflet_tile_layer`` kwargs for a categorical raster.

    The LUT is registered server-side rather than passed as a matplotlib
    ``Colormap``: that is the only localtileserver route preserving per-class
    alpha, since the Colormap path forces alpha to 1 and loses the transparent
    background. Returns ``None`` when the registration helper is unavailable, so
    the caller can fall back to a continuous colormap.

    ``vmin``/``vmax`` pin the render range to the byte range the class codes
    already live in. Without them localtileserver rescales any non-``uint8`` tile
    onto 0-255 before the colormap runs, which turns class codes into ramp
    positions and leaves the whole raster transparent; pinning both ends makes
    that rescale an identity.
    """
    try:
        from localtileserver.tiler.palettes import register_colormap
    except ImportError:
        return None

    return {
        "colormap": register_colormap(_build_class_colormap(class_colors)),
        "vmin": 0,
        "vmax": MAX_CLASS_CODE,
    }


def _continuous_color_kwargs(image: Path, bands, colormap) -> dict:
    """Return the ``get_leaflet_tile_layer`` kwargs for a continuous raster.

    A multi-band source without an explicit single band is rendered as an RGB
    composite; anything else is one band with ``colormap`` across its range.

    ``colormap`` goes straight through -- ``get_leaflet_tile_layer`` accepts a
    name, a matplotlib ``Colormap`` or a list of colors, and only the arguments
    it names (``indexes``, ``colormap``, ``vmin``, ``vmax``, ``nodata``,
    ``stretch``, ``expression``) reach the tile URL. Everything else lands on the
    widget as an unrecognised trait and is silently dropped, which is what the
    large-image ``style`` dict used here until 3.9.0 did.
    """
    import rasterio as rio

    with rio.open(image) as ds:
        count = ds.count

    if isinstance(bands, (list, tuple)) and len(bands) == 1:
        bands = bands[0]

    if count > 1 and not isinstance(bands, int):
        return {"indexes": list(bands) if bands else [3, 2, 1]}

    return {"indexes": [bands if isinstance(bands, int) else 1], "colormap": colormap}
