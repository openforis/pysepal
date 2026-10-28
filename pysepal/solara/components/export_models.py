"""Core models and helpers for the Solara export system."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable, Literal, Optional

import ee
from pysepal_api import SepalClient

ExportTarget = Literal["gee", "drive", "sepal"]
ExportKind = Literal["image", "table"]
ExportBackend = Literal["auto", "direct", "taskmanager"]

TABLE_FILE_FORMATS = [
    {"text": "CSV", "value": "CSV"},
    {"text": "GeoJSON", "value": "GEO_JSON"},
    {"text": "Shapefile", "value": "SHP"},
    {"text": "KML", "value": "KML"},
    {"text": "KMZ", "value": "KMZ"},
]
DEFAULT_TABLE_FILE_FORMAT = "SHP"
TARGET_LABELS = {
    "gee": "Earth Engine asset",
    "drive": "Google Drive",
    "sepal": "SEPAL workspace",
}
SUCCESS_TASK_STATES = {"COMPLETED", "SUCCEEDED"}
FAILED_TASK_STATES = {
    "FAILED",
    "FAILURE",
    "ERROR",
    "CANCELLED",
    "CANCELED",
    "CANCEL_REQUESTED",
}
DEFAULT_IMAGE_FILE_FORMAT = "GEO_TIFF"


@dataclass(frozen=True, slots=True)
class ExportSource:
    """Parent-owned declaration of one exportable source."""

    id: str
    label: str
    kind: ExportKind
    resolve: Callable[[], "ResolvedExport"]
    description: str = ""
    disabled: bool = False
    icon: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedExport:
    """Concrete export payload resolved from a source."""

    ee_object: object
    default_name: str
    region: object = None
    default_scale: int | None = None
    selectors: tuple[str, ...] | None = None
    bands: tuple[str, ...] | None = None
    """Bands (images) / properties (tables) offered in the picker; ``None`` hides it."""
    default_bands: tuple[str, ...] | None = None
    """Initial picker selection; defaults to all ``bands``."""
    gee_folder: str = ""
    drive_folder: str = ""
    sepal_folder: str = ""
    table_file_format: str = DEFAULT_TABLE_FILE_FORMAT
    image_file_format: str = DEFAULT_IMAGE_FILE_FORMAT
    max_pixels: int | None = 1_000_000_000
    max_vertices: int | None = None
    priority: int | None = None
    vis_params: Optional[dict] = None
    """Optional SEPAL-convention visualization parameters to embed on the
    exported image.

    When set on an ``image``-kind source, the engine wraps ``ee_object`` with
    :func:`pysepal.mapping.visualization.set_viz_params` before submission, so
    the resulting Earth Engine asset carries the ``visualization_*`` properties
    that SepalMap (and other SEPAL recipes) read on display. Pass the same dict
    shape accepted by ``set_viz_params`` (keys: ``name``, ``type``, ``bands``,
    ``min``, ``max``, ``palette``, ``values``, ``labels``, ``inverted``).

    Ignored for ``table``-kind sources.
    """


@dataclass(frozen=True, slots=True)
class ExportRequest:
    """Immutable export request snapshot passed into background work."""

    ee_object: object
    export_kind: ExportKind
    target: ExportTarget
    name: str
    region: object = None
    scale: Optional[int] = None
    gee_asset_id: Optional[str] = None
    drive_folder: Optional[str] = None
    sepal_folder: Optional[str] = None
    table_file_format: str = DEFAULT_TABLE_FILE_FORMAT
    image_file_format: str = DEFAULT_IMAGE_FILE_FORMAT
    selectors: Optional[tuple[str, ...]] = None
    max_pixels: Optional[int] = None
    max_vertices: Optional[int] = None
    priority: Optional[int] = None
    cleanup_drive_after_sepal: bool = True
    poll_interval_seconds: float = 3.0
    timeout_seconds: float = 1800.0
    vis_params: Optional[dict] = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Structured export outcome for host apps and inline summaries."""

    target: ExportTarget
    export_kind: ExportKind
    name: str
    message: str
    task_id: Optional[str] = None
    asset_id: Optional[str] = None
    drive_folder: Optional[str] = None
    drive_items: tuple[str, ...] = ()
    sepal_paths: tuple[str, ...] = ()
    backend: Literal["direct", "taskmanager"] = "direct"
    status: Literal["submitted", "completed"] = "submitted"
    sepal_task_id: Optional[str] = None
    output_directory: Optional[str] = None

    @property
    def ee_task_id(self) -> Optional[str]:
        """Explicit alias for the legacy ``task_id`` (never a SEPAL task ID)."""
        return self.task_id


def sanitize_export_name(value: str) -> str:
    """Normalize user input into a filename-safe export name."""
    cleaned = re.sub(r"\s+", "_", (value or "").strip())
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._-")
    return cleaned or "export"


def infer_export_kind(ee_object: object) -> ExportKind:
    """Infer whether the export source is an image or a table collection."""
    image_cls = getattr(getattr(ee, "image", None), "Image", None)
    table_cls = getattr(getattr(ee, "featurecollection", None), "FeatureCollection", None)
    image_collection_cls = getattr(
        getattr(ee, "imagecollection", None),
        "ImageCollection",
        None,
    )

    if image_cls is not None and isinstance(ee_object, image_cls):
        return "image"
    if table_cls is not None and isinstance(ee_object, table_cls):
        return "table"
    if image_collection_cls is not None and isinstance(ee_object, image_collection_cls):
        raise TypeError(
            "ExportDataComponent does not support ee.ImageCollection inputs. "
            "Convert the collection to an ee.Image first."
        )

    if hasattr(ee_object, "bandNames"):
        return "image"
    if hasattr(ee_object, "first") and hasattr(ee_object, "size"):
        return "table"

    raise TypeError("ExportDataComponent supports ee.Image and ee.FeatureCollection inputs only.")


def resolve_asset_folder(root_folder: str, requested_folder: Optional[str]) -> str:
    """Resolve a requested GEE folder against the user's asset root."""
    root = PurePosixPath((root_folder or "").rstrip("/"))
    requested = (requested_folder or "").strip().strip("/")

    if not requested:
        return str(root)

    if requested.startswith("projects/"):
        return str(PurePosixPath(requested))

    return str(root / requested)


def resolve_sepal_folder(
    sepal_client: SepalClient,
    requested_folder: Optional[str],
) -> PurePosixPath:
    """Resolve a destination folder inside the user's SEPAL workspace."""
    base_results = PurePosixPath(str(sepal_client.results_path))
    requested = (requested_folder or "").strip()

    if not requested:
        return base_results

    requested_path = PurePosixPath(requested)
    if requested_path.is_absolute():
        return requested_path

    return base_results / requested_path


def validate_asset_id_under_root(asset_id: str, asset_root: str) -> Optional[str]:
    """Return an error message if ``asset_id`` does not live under ``asset_root``.

    Earth Engine only lets a user write to assets beneath their own asset root
    (``projects/<project>/assets/``). This guards the dialog (live UI hint)
    and the engine (submit-time validation) with one shared rule.

    Returns ``None`` when:
    - ``asset_root`` is empty or still the ``{project}`` placeholder — the UI
      can defer validation until ``_load_asset_root`` finishes.
    - ``asset_id`` is empty — empty is a separate "required" error that the
      caller already surfaces.

    Returns an error string otherwise: when the path does not start under the
    root, or when only the root is given with no asset name beneath it.
    """
    if not asset_root or "{project}" in asset_root:
        return None

    normalized_id = (asset_id or "").strip()
    if not normalized_id:
        return None

    expected_root = asset_root.rstrip("/") + "/"
    if not normalized_id.startswith(expected_root):
        return f"Asset id must live under `{expected_root}`."

    leaf = normalized_id[len(expected_root) :].strip("/")
    if not leaf:
        return f"Asset id must include a name segment under `{expected_root}`."

    return None


def matches_drive_export_prefix(filename: str, prefix: str) -> bool:
    """Return ``True`` when a Drive filename belongs to an export prefix."""
    return (
        filename == prefix
        or filename.startswith(f"{prefix}.")
        or filename.startswith(f"{prefix}-")
        or filename.startswith(f"{prefix}_")
    )


def get_task_state_name(task: object) -> Optional[str]:
    """Normalize task state from ee-client, dict, or legacy task objects."""
    if task is None:
        return None

    candidates = []

    if isinstance(task, dict):
        metadata = task.get("metadata")
        candidates.extend(
            [
                task.get("state"),
                metadata.get("state") if isinstance(metadata, dict) else None,
            ]
        )

    metadata = getattr(task, "metadata", None)
    candidates.extend([getattr(task, "state", None), getattr(metadata, "state", None)])

    for candidate in candidates:
        if candidate:
            return str(candidate).split(".")[-1].upper()

    return None


def extract_task_id(task_or_id: object) -> Optional[str]:
    """Extract a task identifier from ee-client return values."""
    if task_or_id is None:
        return None
    if isinstance(task_or_id, str):
        return task_or_id
    if isinstance(task_or_id, dict):
        return task_or_id.get("id") or task_or_id.get("name")

    for attr_name in ("id", "name"):
        value = getattr(task_or_id, attr_name, None)
        if callable(value):
            value = value()
        if value:
            return str(value)

    metadata = getattr(task_or_id, "metadata", None)
    for attr_name in ("id", "name"):
        value = getattr(metadata, attr_name, None)
        if value:
            return str(value)

    return None


def _build_result_message(result: ExportResult) -> str:
    if result.target == "sepal" and result.output_directory:
        return f"Export completed in SEPAL: `{result.output_directory}`."
    if result.target == "gee" and result.asset_id:
        return f"Earth Engine export submitted to `{result.asset_id}`."
    if result.target == "drive":
        folder = result.drive_folder or "Drive root"
        return f"Google Drive export submitted to `{folder}` as `{result.name}`."
    if result.target == "sepal":
        if len(result.sepal_paths) == 1:
            return f"Export copied to SEPAL: `{result.sepal_paths[0]}`."
        return f"Export copied to SEPAL with {len(result.sepal_paths)} files."
    return result.message


__all__ = [
    "DEFAULT_IMAGE_FILE_FORMAT",
    "DEFAULT_TABLE_FILE_FORMAT",
    "FAILED_TASK_STATES",
    "SUCCESS_TASK_STATES",
    "TABLE_FILE_FORMATS",
    "TARGET_LABELS",
    "ExportBackend",
    "ExportKind",
    "ExportRequest",
    "ExportResult",
    "ExportSource",
    "ExportTarget",
    "ResolvedExport",
    "_build_result_message",
    "extract_task_id",
    "get_task_state_name",
    "infer_export_kind",
    "matches_drive_export_prefix",
    "resolve_asset_folder",
    "resolve_sepal_folder",
    "sanitize_export_name",
    "validate_asset_id_under_root",
]
