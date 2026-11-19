"""The pre-package ``export_*`` module paths keep working until pysepal 5."""

import importlib
import sys

import pytest

COMPONENTS = "pysepal.solara.components"


@pytest.mark.parametrize("name", ["models", "engine", "hook", "dialog", "launcher"])
def test_old_module_path_is_the_package_module(name):
    old = f"{COMPONENTS}.export_{name}"
    sys.modules.pop(old, None)

    with pytest.warns(DeprecationWarning, match=f"{COMPONENTS}.export instead"):
        legacy = importlib.import_module(old)

    assert legacy is importlib.import_module(f"{COMPONENTS}.export.{name}")


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
