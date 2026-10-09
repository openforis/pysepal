"""Custom FileInput widget that leverages vuetify templates and reads any :class:`FileSystem`.

Note: FileInputComponent has moved to pysepal.solara.components.inputs.file_input.
Importing it from this module is deprecated.
"""

from pathlib import Path, PurePosixPath
from typing import Optional, Union

import ipyvuetify as v
from pysepal_api import SepalClient
from traitlets import Bool, Int, List, Unicode, validate

from pysepal.logger import log
from pysepal.message import msg
from pysepal.scripts.filesystem import (
    FileDetails,
    FileSystem,
    ListDirectoryResponse,
    LocalFileSystem,
    PathOutsideRootError,
    SandboxFileSystem,
)
from pysepal.sepalwidgets.widget import SepalWidget

__all__ = ["FileDetails", "FileInput", "ListDirectoryResponse"]


def local_files_allowed() -> bool:
    """Whether this process's own filesystem belongs to the person using the app."""
    from pysepal.solara.session_manager import serves_many_users

    return not serves_many_users()


def is_within(path: Union[str, Path], root: Union[str, Path]) -> bool:
    """Whether ``path`` stays inside ``root`` once ``..`` and symlinks are resolved."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def _default_filesystem(root: str) -> Optional[FileSystem]:
    """The user's files when the caller names no filesystem, or None if there are none."""
    if local_files_allowed():
        return LocalFileSystem(root or None)

    from pysepal.solara.errors import SepalSessionError
    from pysepal.solara.utils import get_current_filesystem

    try:
        return get_current_filesystem()
    except SepalSessionError:
        return None


class FileInput(v.VuetifyTemplate, SepalWidget):

    template_file = Unicode(str(Path(__file__).parent / "vue/FileInput.vue")).tag(sync=True)

    file_list = List([]).tag(sync=True)
    current_folder = Unicode("/").tag(sync=True)
    loading = Bool(False).tag(sync=True)
    extensions = List(Unicode()).tag(sync=True)
    label = Unicode("Select a file").tag(sync=True)
    value = Unicode().tag(sync=True)
    v_model = Unicode().tag(sync=True)
    file = Unicode().tag(sync=True)
    clearable = Bool(True).tag(sync=True)
    error_messages = List([]).tag(sync=True)

    root = Unicode("/").tag(sync=True)

    reload_files = Int(0).tag(sync=True)
    base_path = Unicode("").tag(sync=True)

    filesystem: Optional[FileSystem] = None
    "Where the files live; None when this runtime gives the user no files."

    def __init__(
        self,
        initial_folder: str = "",
        root: str = "",
        sepal_client: SepalClient = None,
        filesystem: Optional[FileSystem] = None,
        **kwargs,
    ):
        """Custom widget to select a file of the user, on the local disk or in SEPAL.

        Paths are absolute and ``value`` is one of them. Read the selected file
        through :attr:`filesystem`, e.g. ``filesystem.local_copy(value)``.

        Args:
            initial_folder: The folder shown first, relative to the filesystem root
                unless absolute.
            root: The folder the user cannot leave, the filesystem root by default.
            sepal_client: Browse this client's SEPAL workspace.
            filesystem: Browse this filesystem. Takes precedence over ``sepal_client``.
                By default: the user's files for this runtime, see
                :func:`pysepal.solara.get_current_filesystem`.
        """
        self.client = sepal_client
        if filesystem is None and sepal_client is not None:
            filesystem = SandboxFileSystem(sepal_client)
        self.filesystem = filesystem if filesystem is not None else _default_filesystem(root)

        super().__init__(**kwargs)

        if self.filesystem is None:
            self.error_messages = [msg("widgets.fileinput.no_local_files")]
            self.file_list = []
            return

        self.root = str(self.filesystem.resolve(root or self.filesystem.root))
        self.initial_folder = str(self.filesystem.resolve(initial_folder or self.root))
        log.debug(f"FileInput root: {self.root}, initial folder: {self.initial_folder}")
        if not self._allows(self.initial_folder):
            raise ValueError(
                f"Initial folder {self.initial_folder} is not a subdirectory of {self.root}"
            )
        self.current_folder = self.initial_folder

        self.load_files()
        self.observe(self.load_files, "current_folder")
        self.observe(self.load_files, "reload_files")
        self.observe(lambda chg: setattr(self, "v_model", chg["new"]), "value")
        self.observe(lambda chg: setattr(self, "file", chg["new"]), "value")

    def _allows(self, path: str) -> bool:
        """Whether a path the browser sent may be listed or selected."""
        if self.filesystem is None:
            return False
        try:
            resolved = self.filesystem.resolve(path)
        except PathOutsideRootError:
            return False
        return resolved.is_relative_to(PurePosixPath(self.root))

    @validate("current_folder")
    def _keep_folder_in_root(self, proposal):
        if self._allows(proposal["value"]):
            return proposal["value"]
        return self.root

    @validate("value", "v_model", "file")
    def _keep_selection_in_root(self, proposal):
        if not proposal["value"] or self._allows(proposal["value"]):
            return proposal["value"]
        return ""

    def set_state(self, sync_data):
        """Apply browser state, except ``root``: the bound is set in Python only."""
        sync_data = {k: v for k, v in sync_data.items() if k != "root"}
        super().set_state(sync_data)

    def load_files(self, *_):
        """Load the files in the current folder."""
        if self.filesystem is None:
            return

        log.debug(f"Loading files in {self.current_folder} with root {self.root}")
        try:
            self.loading = True
            file_list = self.filesystem.list(self.current_folder, extensions=self.extensions)

            # place the parent directory at the top
            if self.current_folder != self.root:
                parent = str(PurePosixPath(self.current_folder).parent)
                file_list.files.insert(
                    0, FileDetails(name="..", path=parent, type="directory", size=0)
                )

            self.file_list = file_list.model_dump()["files"]

        except Exception as error:
            log.error(f"Failed to load files: {error}")
        finally:
            self.loading = False

    def reset(self):
        """Reset the file input widget."""
        self.value = ""
        if self.filesystem is not None:
            self.current_folder = self.initial_folder

    def select_file(self, path: Union[str, Path]):
        """Select a file from the list."""
        if self.filesystem is None or not self._allows(str(path)):
            raise ValueError(f"{path} is not a file this input can select")
        path = self.filesystem.resolve(path)

        if isinstance(self.filesystem, LocalFileSystem) and not Path(path).is_file():
            raise Exception(f"{path} is not a file")

        self.current_folder = str(path.parent)
        self.value = str(path)


def __getattr__(name: str):
    if name == "FileInputComponent":
        import warnings

        warnings.warn(
            "FileInputComponent has moved to pysepal.solara.components.inputs.file_input. "
            "Importing from pysepal.sepalwidgets.file_input is deprecated and will be "
            "removed in a future version.",
            DeprecationWarning,
            stacklevel=2,
        )
        from pysepal.solara.components.inputs.file_input import FileInputComponent

        return FileInputComponent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
