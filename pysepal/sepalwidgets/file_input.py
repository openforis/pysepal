"""Custom FileInput widget that leverages vuetify templates and reads any :class:`FileSystem`.

Note: FileInputComponent has moved to pysepal.solara.components.inputs.file_input.
Importing it from this module is deprecated.
"""

from pathlib import Path
from typing import Union

from pysepal.scripts.filesystem import FileDetails, ListDirectoryResponse
from pysepal.sepalwidgets.widget import SepalWidget
from pysepal.solara.components.inputs._file_input_widget import (  # noqa: F401
    FileInputWidget,
    _default_filesystem,
    _resolve_bounds,
    local_files_allowed,
)

__all__ = ["FileDetails", "FileInput", "ListDirectoryResponse"]


def is_within(path: Union[str, Path], root: Union[str, Path]) -> bool:
    """Whether ``path`` stays inside ``root`` once ``..`` and symlinks are resolved."""
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        return False


class FileInput(FileInputWidget, SepalWidget):
    """The file picker of :class:`FileInputWidget` with the :class:`SepalWidget` API."""


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
