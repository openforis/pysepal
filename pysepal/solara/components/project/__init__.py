"""Folder-per-project management: a store contract and the Project window built on it.

Usage::

    class MyStore(ProjectStore):
        def describe(self, name, folder):
            data = json.loads(self.manifest_path(name).read_text())
            chips = ((f"{len(data['layers'])} layers", False),)
            return ProjectInfo(name, updated_at=datetime.fromisoformat(data["saved"]), chips=chips)

    store = MyStore(Path.home() / "module_results" / "my_app")

    ProjectPanel(
        store,
        current=app.project.value and app.project.value.name,
        on_open=app.load,  # (name) -> bool, sync or async
        on_create=app.create,  # (name) -> bool
        on_close=close_dialog,
    )
"""

from .dialogs import ConfirmDeleteDialog, ManageProjectsDialog, NameForm
from .panel import ProjectPanel
from .store import ProjectInfo, ProjectStore

__all__ = [
    "ConfirmDeleteDialog",
    "ManageProjectsDialog",
    "NameForm",
    "ProjectInfo",
    "ProjectPanel",
    "ProjectStore",
]
