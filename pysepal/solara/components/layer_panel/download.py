"""Download of the files behind a local layer."""

import io
import zipfile
from typing import Optional

from pysepal.layers import LayerSpec, VectorSource, local_files

DOWNLOAD_MAX_BYTES = 500_000_000
"Largest download the panel serves; the bytes travel over the websocket and stay in memory."


def _is_shapefile(spec: LayerSpec) -> bool:
    return isinstance(spec.source, VectorSource) and spec.source.format == "ESRI Shapefile"


def download_size(spec: LayerSpec) -> Optional[int]:
    """Total size in bytes of the files a download of ``spec`` reads.

    Args:
        spec: The layer spec.

    Returns:
        The size, or None when the source is not a local file or the file is missing.
    """
    files = local_files(spec)
    if not files:
        return None
    try:
        return sum(path.stat().st_size for path in files)
    except OSError:
        return None


def is_too_large(size: int) -> bool:
    """Whether ``size`` bytes is above :data:`DOWNLOAD_MAX_BYTES`.

    Args:
        size: The download size in bytes.
    """
    return size > DOWNLOAD_MAX_BYTES


def is_downloadable(spec: LayerSpec) -> bool:
    """Whether the layer's data is a local file that exists.

    Args:
        spec: The layer spec.
    """
    return download_size(spec) is not None


def download_filename(spec: LayerSpec) -> str:
    """Name of the file a download of ``spec`` produces.

    Args:
        spec: The layer spec.

    Raises:
        ValueError: If the source is not a local file.
    """
    files = local_files(spec)
    if not files:
        raise ValueError(f"Layer {spec.id!r} has no local file to download")
    return f"{files[0].stem}.zip" if _is_shapefile(spec) else files[0].name


def download_payload(spec: LayerSpec) -> tuple[bytes, str]:
    """Read the file behind a local layer.

    A shapefile is zipped in memory with the recognised sidecars that exist.

    Args:
        spec: The layer spec.

    Returns:
        The bytes and the file name.

    Raises:
        ValueError: If the source is not a local file.
    """
    name = download_filename(spec)
    files = local_files(spec)
    if not _is_shapefile(spec):
        return files[0].read_bytes(), name
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return buffer.getvalue(), name
