"""Whether the sample files beside the demos are among the user's files."""

from component.parameter import DUMMY_DATA_DIR

from pysepal.scripts.filesystem import FileSystem


def sample_folder(filesystem: FileSystem) -> str:
    """The sample data folder, or ``""`` when ``filesystem`` cannot reach it.

    Through a SEPAL session the file inputs browse the user's workspace, which
    does not hold the folder beside the demos.
    """
    return str(DUMMY_DATA_DIR) if filesystem.contains(DUMMY_DATA_DIR) else ""
