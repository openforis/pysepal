"""Download of the files behind a local layer."""

import io
import zipfile

from pysepal.layers import LayerSpec, VectorSource, local_files


def _is_shapefile(spec: LayerSpec) -> bool:
    return isinstance(spec.source, VectorSource) and spec.source.format == "ESRI Shapefile"


def is_downloadable(spec: LayerSpec) -> bool:
    """Whether the layer's data is a local file.

    Args:
        spec: The layer spec.
    """
    return bool(local_files(spec))


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
