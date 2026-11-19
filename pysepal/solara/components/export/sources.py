"""What the export dialog offers: sources, destinations, bands and defaults."""

from __future__ import annotations

import asyncio
from typing import Collection, Sequence

from pysepal_api import AsyncSepalClient, SepalClient

from pysepal.scripts.gee_interface import GEEInterface

from .models import (
    DEFAULT_TABLE_FILE_FORMAT,
    TARGET_LABELS,
    ExportBackend,
    ExportKind,
    ExportSource,
    ExportTarget,
    ResolvedExport,
    infer_export_kind,
    sanitize_export_name,
)

# Debounce for the live GEE asset-existence check; task cancellation on new
# input means no API call fires while the user is still typing.
GEE_ASSET_CONFLICT_CHECK_DELAY = 0.35

_TARGET_ORDER: tuple[ExportTarget, ...] = ("gee", "drive", "sepal")


def targets_for(
    backend: ExportBackend,
    sepal_client: SepalClient | None,
    async_sepal_client: AsyncSepalClient | None,
) -> frozenset[ExportTarget]:
    """Destinations the backend can run with the clients at hand."""
    has_client = sepal_client is not None or async_sepal_client is not None
    if backend == "taskmanager":
        return frozenset({"sepal"} if has_client else ())
    workspace = sepal_client is not None if backend == "direct" else has_client
    return frozenset({"gee", "drive", "sepal"} if workspace else {"gee", "drive"})


def coerce_default_target(
    default_target: ExportTarget,
    available: Collection[ExportTarget],
) -> ExportTarget:
    """Keep ``default_target`` when available, else the first available destination."""
    if default_target in available or not available:
        return default_target
    return next(target for target in _TARGET_ORDER if target in available)


def enabled_sources(sources: Sequence[ExportSource]) -> tuple[ExportSource, ...]:
    """Return the sources the user can pick."""
    return tuple(source for source in sources if not source.disabled)


def source_by_id(
    sources: Sequence[ExportSource],
    source_id: str,
) -> ExportSource | None:
    """Return the source with ``source_id``, or ``None``."""
    for source in sources:
        if source.id == source_id:
            return source
    return None


def get_active_source(
    sources: Sequence[ExportSource],
    selected_source_id: str,
) -> ExportSource | None:
    """Return the user-picked source, or ``None`` when nothing valid is selected."""
    selected = source_by_id(sources, selected_source_id)
    if selected is not None and not selected.disabled:
        return selected
    return None


_SOURCE_KIND_GROUPS: tuple[tuple[ExportKind, str], ...] = (
    ("image", "Images"),
    ("table", "Feature collections"),
)


def get_source_items(sources: Sequence[ExportSource]) -> list[dict[str, object]]:
    """Build VSelect items grouped by kind with headers and dividers.

    Falls back to a flat list when only one kind is present, so small-asset
    modules don't see a single-group header.
    """
    grouped = {
        kind: [source for source in sources if source.kind == kind]
        for kind, _label in _SOURCE_KIND_GROUPS
    }
    populated_groups = [(kind, label) for kind, label in _SOURCE_KIND_GROUPS if grouped[kind]]

    def _source_item(source: ExportSource) -> dict[str, object]:
        return {
            "text": source.label,
            "value": source.id,
            "disabled": source.disabled,
        }

    if len(populated_groups) <= 1:
        return [_source_item(source) for source in sources]

    items: list[dict[str, object]] = []
    for index, (kind, label) in enumerate(populated_groups):
        if index > 0:
            items.append({"divider": True})
        items.append({"header": label})
        items.extend(_source_item(source) for source in grouped[kind])
    return items


def get_target_items(
    sepal_client: SepalClient | AsyncSepalClient | None,
    *,
    available: Collection[ExportTarget] | None = None,
) -> list[dict[str, object]]:
    """Return the destination radio items, disabling those that cannot run.

    Without ``available``, SEPAL is disabled when no client is available.
    """
    if available is None:
        available = targets_for("auto", sepal_client, None)
    return [
        {"text": TARGET_LABELS[target], "value": target, "disabled": target not in available}
        for target in _TARGET_ORDER
    ]


def resolve_source_state(
    source: ExportSource | None,
) -> tuple[ResolvedExport | None, ExportKind | None, str | None]:
    """Resolve a source and verify its declared kind matches the real ee object.

    Returns ``(resolved, kind, None)`` on success, else ``(None, None, error)``.
    """
    if source is None:
        return None, None, None

    try:
        resolved = source.resolve()
    except Exception as exc:
        return None, None, str(exc)

    try:
        inferred_kind = infer_export_kind(resolved.ee_object)
    except Exception as exc:
        return None, None, str(exc)

    if inferred_kind != source.kind:
        return (
            None,
            None,
            (
                f"Source `{source.label}` declared kind `{source.kind}` but resolved to "
                f"`{inferred_kind}`."
            ),
        )

    return resolved, source.kind, None


def default_gee_folder(sepal_client: SepalClient | None) -> str:
    """Return the asset folder used when a source names none: the module name."""
    if sepal_client is not None and sepal_client.module_name:
        return str(sepal_client.module_name).strip("/")
    return "pysepal_exports"


async def resolve_gee_asset_conflict(
    *,
    target: ExportTarget,
    has_active_source: bool,
    asset_id: str,
    gee_interface: GEEInterface,
    debounce_seconds: float = GEE_ASSET_CONFLICT_CHECK_DELAY,
) -> tuple[bool, str]:
    """Probe Earth Engine for a name collision against the resolved asset id.

    Returns ``(conflict, candidate_path)``; lookup failures count as no conflict,
    since the engine-side guard is authoritative at submit time.
    """
    candidate = (asset_id or "").strip()
    if target != "gee" or not has_active_source or not candidate:
        return False, ""

    if debounce_seconds > 0:
        await asyncio.sleep(debounce_seconds)

    try:
        existing = await gee_interface.get_asset_async(candidate, not_exists_ok=True)
    except Exception:
        return False, ""

    if existing is None:
        return False, ""
    return True, candidate


def build_default_gee_asset_id(
    asset_root: str,
    resolved_export: ResolvedExport,
    sepal_client: SepalClient | None,
) -> str:
    """Pre-fill a GEE asset path as ``{asset_root}/{gee_folder or module}/{name}``.

    Ignores the asset root when ``gee_folder`` is absolute (``projects/…``);
    returns ``""`` while the asset root is still loading.
    """
    if not asset_root or "{project}" in asset_root:
        return ""

    name = sanitize_export_name(resolved_export.default_name) or "export"
    folder = (resolved_export.gee_folder or default_gee_folder(sepal_client) or "").strip("/")

    if folder.startswith("projects/"):
        return f"{folder.rstrip('/')}/{name}"

    root = asset_root.rstrip("/")
    if not folder:
        return f"{root}/{name}"
    return f"{root}/{folder}/{name}"


def defaults_signature(
    resolved_export: ResolvedExport | None,
    export_kind: ExportKind | None,
    sepal_client: SepalClient | None,
) -> tuple[object, ...]:
    """Return what the per-source defaults depend on, to reapply them when it changes."""
    if resolved_export is None:
        return ()

    return (
        export_kind,
        resolved_export.default_scale if export_kind == "image" else None,
        resolved_export.gee_folder or default_gee_folder(sepal_client),
        resolved_export.drive_folder or "",
        resolved_export.sepal_folder or "",
        resolved_export.table_file_format or DEFAULT_TABLE_FILE_FORMAT,
    )


def available_bands_for(resolved_export: ResolvedExport | None) -> tuple[str, ...]:
    """Return the *declared* ``ResolvedExport.bands`` catalog, or ``()``.

    Image sources that omit it get bands auto-discovered instead
    (see :func:`discover_image_bands`).
    """
    if resolved_export is None or not resolved_export.bands:
        return ()
    return tuple(resolved_export.bands)


def default_bands_for(
    resolved_export: ResolvedExport | None,
    available: tuple[str, ...],
) -> tuple[str, ...]:
    """Return the initial selection for ``available``, in catalog order.

    Whole catalog by default, narrowed to ``ResolvedExport.default_bands`` when
    declared; an empty overlap falls back to the full catalog.
    """
    if not available:
        return ()
    requested = resolved_export.default_bands if resolved_export is not None else None
    if not requested:
        return available
    requested_set = set(requested)
    return tuple(band for band in available if band in requested_set) or available


def resolved_default_bands(resolved_export: ResolvedExport | None) -> tuple[str, ...]:
    """Return the initial selection for a source's *declared* catalog."""
    return default_bands_for(resolved_export, available_bands_for(resolved_export))


async def discover_image_bands(
    gee_interface: GEEInterface,
    ee_object: object,
) -> tuple[str, ...]:
    """Fetch an image's band names via GEE, returning ``()`` on any failure.

    Auto-populates the picker for image sources without a declared ``bands``
    catalog; failures just leave the picker hidden and export the full image.
    """
    band_names_fn = getattr(ee_object, "bandNames", None)
    if band_names_fn is None:
        return ()
    try:
        names = await gee_interface.get_info_async(band_names_fn())
    except Exception:
        return ()
    if not names:
        return ()
    return tuple(str(name) for name in names)


def normalize_band_selection(
    available: tuple[str, ...],
    selected: tuple[str, ...],
) -> tuple[str, ...]:
    """Filter ``selected`` against ``available`` and preserve catalog order."""
    if not available:
        return ()
    selected_set = set(selected)
    return tuple(band for band in available if band in selected_set)


__all__ = [
    "available_bands_for",
    "build_default_gee_asset_id",
    "coerce_default_target",
    "default_bands_for",
    "default_gee_folder",
    "defaults_signature",
    "discover_image_bands",
    "enabled_sources",
    "get_active_source",
    "get_source_items",
    "get_target_items",
    "normalize_band_selection",
    "resolve_gee_asset_conflict",
    "resolve_source_state",
    "resolved_default_bands",
    "source_by_id",
    "targets_for",
]
