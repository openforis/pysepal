"""The pre-package ``export_*`` module paths keep working until pysepal 5."""

import importlib
import sys

import pytest

COMPONENTS = "pysepal.solara.components"

# The public names of the export_* modules in pysepal 4.3.0.
OLD_PUBLIC_NAMES = {
    "models": [
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
        "RemoteCancelOutcome",
        "RemoteCancelStatus",
        "ResolvedExport",
        "extract_task_id",
        "get_task_state_name",
        "infer_export_kind",
        "matches_drive_export_prefix",
        "resolve_asset_folder",
        "resolve_sepal_folder",
        "sanitize_export_name",
        "validate_asset_id_under_root",
    ],
    "engine": ["cancel_export_task", "submit_export_request"],
    "hook": [
        "ExportDialogController",
        "available_bands_for",
        "default_bands_for",
        "discover_image_bands",
        "get_active_source",
        "get_controller_source_state",
        "get_source_items",
        "get_target_items",
        "normalize_band_selection",
        "resolve_source_state",
        "resolved_default_bands",
        "use_export_dialog",
    ],
    "dialog": ["BandSelectorField", "ExportDialog", "InlineExportFeedback"],
    "launcher": ["ExportLauncher"],
    "taskmanager": [
        "TASKMANAGER_ENV_FLAG",
        "EXPORT_BACKENDS",
        "taskmanager_opted_in",
        "validate_backend",
        "taskmanager_rejection",
        "select_backend",
        "cancel_taskmanager_export",
        "submit_taskmanager_export",
    ],
}


@pytest.mark.parametrize("name", sorted(OLD_PUBLIC_NAMES))
def test_old_module_path_is_the_package_module(name):
    old = f"{COMPONENTS}.export_{name}"
    sys.modules.pop(old, None)

    with pytest.warns(
        DeprecationWarning, match=rf"Import from {COMPONENTS}\.export\.{name} instead"
    ):
        legacy = importlib.import_module(old)

    assert legacy is importlib.import_module(f"{COMPONENTS}.export.{name}")


@pytest.mark.parametrize("name", sorted(OLD_PUBLIC_NAMES))
def test_the_suggested_module_has_every_old_public_name(name):
    module = importlib.import_module(f"{COMPONENTS}.export.{name}")

    assert [n for n in OLD_PUBLIC_NAMES[name] if not hasattr(module, n)] == []


def test_names_apps_import_from_old_paths_still_resolve():
    from pysepal.solara.components import export

    sys.modules.pop(f"{COMPONENTS}.export_dialog", None)
    sys.modules.pop(f"{COMPONENTS}.export_hook", None)
    sys.modules.pop(f"{COMPONENTS}.export_models", None)
    with pytest.warns(DeprecationWarning):
        from pysepal.solara.components.export_dialog import ExportDialog
        from pysepal.solara.components.export_hook import (
            ExportDialogController,
            use_export_dialog,
        )
        from pysepal.solara.components.export_models import get_task_state_name

    assert ExportDialog is export.ExportDialog
    assert ExportDialogController is export.ExportDialogController
    assert use_export_dialog is export.use_export_dialog
    assert get_task_state_name is export.get_task_state_name
