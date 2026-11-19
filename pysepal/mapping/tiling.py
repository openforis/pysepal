"""Prepare a raster for fast tile serving.

``rio-tiler`` reads full-resolution pixels for every tile when the source has no
overviews, so low zooms are slow and each tile logs a ``NoOverviewWarning``.
:func:`prepare_for_tiles` returns a tiled COG with overviews, kept in a cache
directory and reused on later calls, and is a fast no-op when the raster is
already good enough.

Everything runs through rasterio's own GDAL rather than the ``gdal_translate``
/ ``gdaladdo`` / ``gdalwarp`` binaries: those cannot be declared as a dependency
-- they are not on PyPI -- so a ``pip install`` would silently fall back to
serving unprepared, unprojected rasters.

``rasterio`` is imported inside the functions that need it. ``pysepal.mapping``
pulls this module in, and importing rasterio costs ~160ms, which an app that only
draws Earth Engine layers should not pay to display a map.
"""

import contextlib
import hashlib
import logging
import os
import pathlib
import uuid
from typing import Iterator, Optional, Union

from pysepal.scripts.scratch import scratch_root

__all__ = ["analyze_tif", "prepare_for_tiles"]

log = logging.getLogger("sepalui.mapping.tiling")

#: Overrides where prepared rasters are cached, for a sandbox with a disk quota.
CACHE_DIR_ENV_VAR = "PYSEPAL_TILE_CACHE"

#: Edge of a tile block, and the size overviews are built down to.
BLOCK_SIZE = 512


def default_cache_dir() -> pathlib.Path:
    """The directory prepared rasters are cached in.

    A prepared COG is a derived file, so it belongs on scratch rather than in the
    user's home: on a SEPAL sandbox the home export is nfs4 and quota'd, which
    would make every tile read cross the network and charge the user for the
    copy. :func:`~pysepal.scripts.scratch.scratch_root` is container-local there.

    A fixed name under that root rather than :func:`scratch_dir`, which mints a
    unique directory per call and would defeat the caching entirely.

    Returns:
        ``$PYSEPAL_TILE_CACHE`` when set, otherwise ``pysepal-tiles`` under the
        scratch root.
    """
    override = os.environ.get(CACHE_DIR_ENV_VAR)
    if override:
        return pathlib.Path(override)

    return scratch_root() / "pysepal-tiles"


def _optimize_for_tiles(
    image: Union[str, pathlib.Path],
    categorical: Optional[bool] = None,
    warp_to_3857: bool = False,
) -> str:
    """Return a tiling-optimized (cached COG with overviews) path.

    Best-effort wrapper around :func:`prepare_for_tiles`: on failure the raw
    raster is served, which still tiles, just more slowly.
    """
    try:
        return prepare_for_tiles(str(image), warp_to_3857=warp_to_3857, categorical=categorical)[
            "path"
        ]
    except Exception as e:
        log.warning("Tiling optimization failed for %s (%s); serving the raw raster.", image, e)
        return str(image)


def _hash_for_cache(path: str, *recipe: str) -> str:
    """Identify a cache entry by its source *and* how it was prepared.

    ``recipe`` carries everything that changes the output for the same input --
    overview resampling, class renumbering -- so a second call asking for
    different treatment does not get handed the first call's file.

    ``st_mtime_ns`` rather than whole seconds: a rewrite that keeps the byte
    count and lands inside the same second would otherwise look unchanged.
    """
    st = os.stat(path)
    h = hashlib.sha1()
    h.update(path.encode())
    h.update(str(st.st_size).encode())
    h.update(str(st.st_mtime_ns).encode())
    for item in recipe:
        h.update(b"\x00")
        h.update(item.encode())
    return h.hexdigest()[:16]


@contextlib.contextmanager
def _write_atomically(dst: Union[str, pathlib.Path]) -> Iterator[str]:
    """Yield a temporary path to write, moved onto ``dst`` only once it is whole.

    Two kernels adding the same raster resolve to the same cache entry, and a
    reader that opens a half-written GeoTIFF fails in ways that look like a
    corrupt source.
    """
    dst = pathlib.Path(dst)
    # unique per writer, not just per process: add_raster_async hands preparation
    # to a thread pool, so two concurrent adds share a pid and would otherwise
    # write the same file -- one publishing it while the other is mid-write
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.part")
    try:
        yield str(tmp)
        os.replace(tmp, dst)
    finally:
        with contextlib.suppress(OSError):
            if tmp.exists():
                tmp.unlink()


def _guess_categorical(ds) -> bool:
    """Guess whether a raster holds classes rather than a continuous measure.

    Only consulted when the caller doesn't say: passing ``class_colors`` to
    ``add_raster`` settles it, and this dtype test cannot tell a class map from
    an integer DEM.
    """
    return ds.count == 1 and ds.dtypes[0].startswith(
        ("int8", "uint8", "int16", "uint16", "int32", "uint32")
    )


def _has_overviews(ds) -> bool:
    return any(ds.overviews(i + 1) for i in range(ds.count))


def _is_tiled(ds) -> bool:
    # block_shapes is None on some drivers; treat as not tiled
    try:
        bs = ds.block_shapes
        return bool(bs) and all((b[0] > 1 and b[1] > 1) for b in bs)
    except Exception:
        return False


def _needs_reproject(ds, target_epsg: Optional[int]) -> bool:
    if not target_epsg or not ds.crs:
        return False
    try:
        return ds.crs.to_epsg() != target_epsg
    except Exception:
        return True


def _predictor_for(dtype: str) -> int:
    """The DEFLATE predictor that matches the sample format.

    2 is horizontal differencing, defined for integers only; floating point
    needs 3, and using 2 there either errors or compresses badly.
    """
    return 3 if dtype.startswith("float") else 2


def analyze_tif(path: str) -> dict:
    """Report the tiling-relevant properties of a raster.

    Args:
        path: Path to the raster file.

    Returns:
        CRS, size, band count, dtype, whether it is tiled, its overview levels
        and a guess at whether the data is categorical.
    """
    import rasterio as rio

    with rio.open(path) as ds:
        return {
            "path": path,
            "crs": str(ds.crs),
            "epsg": (ds.crs.to_epsg() if ds.crs else None),
            "width": ds.width,
            "height": ds.height,
            "bands": ds.count,
            "dtype": ds.dtypes[0],
            "tiled": _is_tiled(ds),
            "overviews": [ds.overviews(i + 1) for i in range(ds.count)],
            "categorical_guess": _guess_categorical(ds),
        }


def _write_cog(source, dst: str, resampling: str, dtype: str) -> None:
    """Copy a dataset (or a warping view of one) out as a COG with overviews.

    ``rasterio.shutil.copy`` is GDAL's ``CreateCopy``, so the pixels stream
    rather than landing in a numpy array first -- a raster far larger than
    memory still converts.
    """
    from rasterio.shutil import copy as rio_copy

    rio_copy(
        source,
        dst,
        driver="COG",
        compress="DEFLATE",
        level=6,
        predictor=_predictor_for(dtype),
        blocksize=BLOCK_SIZE,
        overviews="AUTO",
        resampling=resampling,
        num_threads="ALL_CPUS",
        bigtiff="IF_SAFER",
    )


def prepare_for_tiles(
    path: str,
    cache_dir: Optional[str] = None,
    warp_to_3857: bool = False,
    force: bool = False,
    categorical: Optional[bool] = None,
) -> dict:
    """Return a tiling-optimized copy of a raster, building it if needed.

    The copy is cached under ``cache_dir`` and reused on later calls, so repeat
    adds of the same raster cost nothing.

    Args:
        path: Path to the source raster.
        cache_dir: Where to keep the optimized copy. Defaults to
            :func:`default_cache_dir`.
        warp_to_3857: Reproject to Web Mercator, in the same pass that writes
            the COG.
        force: Rebuild even when a cached copy is available.
        categorical: Whether the values are class codes, which decides between
            NEAREST and AVERAGE overview resampling. Guessed from the dtype when
            not given.

    Returns:
        ``{"path": optimized_path, "report": analyze_tif(optimized_path)}``.
        ``path`` is the source itself when no work was needed.
    """
    import rasterio as rio
    from rasterio.enums import Resampling
    from rasterio.vrt import WarpedVRT

    path = os.path.abspath(path)
    rep = analyze_tif(path)
    if categorical is None:
        categorical = rep["categorical_guess"]
    resampling = "NEAREST" if categorical else "AVERAGE"

    # Open once (context-managed) instead of leaking a handle per rio.open call.
    with rio.open(path) as ds:
        need_reproj = _needs_reproject(ds, 3857) if warp_to_3857 else False
        good_enough = rep["tiled"] and _has_overviews(ds) and not need_reproj

    if good_enough and not force:
        return {"path": path, "report": rep}

    cache_dir = str(cache_dir or default_cache_dir())
    os.makedirs(cache_dir, exist_ok=True)
    tag = _hash_for_cache(path, resampling)
    out = os.path.join(
        cache_dir,
        f"{os.path.basename(path)}.{tag}" + (".3857.cog.tif" if warp_to_3857 else ".cog.tif"),
    )
    # the tag covers the source and the resampling, so an existing entry is this
    # exact raster already prepared the same way
    if os.path.exists(out) and not force:
        return {"path": out, "report": analyze_tif(out)}

    with rio.open(path) as ds, _write_atomically(out) as tmp:
        if warp_to_3857:
            # the VRT warps lazily, so reprojecting costs no intermediate file
            with WarpedVRT(ds, crs="EPSG:3857", resampling=Resampling[resampling.lower()]) as vrt:
                _write_cog(vrt, tmp, resampling, rep["dtype"])
        else:
            _write_cog(ds, tmp, resampling, rep["dtype"])

    return {"path": out, "report": analyze_tif(out)}


def prepare_raster_file(
    image: Union[str, pathlib.Path],
    class_colors: Optional[dict],
    optimize: bool,
    warp_to_3857: bool = False,
) -> tuple:
    """Produce the serve-ready raster path, doing all of the expensive work.

    Touches only the filesystem, so it is safe to run off the UI thread. Returns the
    path to serve and the ``class_colors`` restated in whatever codes that path uses.
    """
    # raster_style imports this module, so these cannot sit at the top
    from pysepal.mapping.raster_style import _densify_class_codes, _needs_dense_codes
    from pysepal.message import msg

    image = pathlib.Path(image)

    if not image.is_file():
        raise Exception(msg("mapping.no_image"))

    source = image
    if class_colors and _needs_dense_codes(class_colors):
        cache_dir = default_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        source, class_colors = _densify_class_codes(image, class_colors, cache_dir)

    if warp_to_3857 and not optimize:
        # reprojecting means writing a new raster, which is the very thing
        # optimize=False asks us not to do
        log.warning("warp_to_3857 needs optimize=True; %s is served in its own CRS.", image)

    # rio-tiler reads full-resolution pixels for every tile when the source
    # has no overviews, so serve a prepared COG. Fast no-op when the raster
    # is already tiled with overviews. class_colors settles the overview
    # resampling either way -- without it the raster is being drawn as a ramp,
    # so averaged overviews are right even for the integer dtypes
    # prepare_for_tiles would otherwise guess were classes (an int16 DEM).
    served = (
        _optimize_for_tiles(
            source,
            categorical=bool(class_colors),
            warp_to_3857=warp_to_3857,
        )
        if optimize
        else str(source)
    )
    return served, class_colors
