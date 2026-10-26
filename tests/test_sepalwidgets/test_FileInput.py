"""Test the FileInput widget."""

from pathlib import Path
from typing import List

import pytest
from traitlets import Any

from pysepal import sepalwidgets as sw
from pysepal.model import Model


def test_init(root_dir: Path) -> None:
    """Init the widget.

    Args:
        root_dir: the patht to the root of the repository
    """
    # default init
    file_input = sw.FileInput()

    assert isinstance(file_input, sw.FileInput)
    assert file_input.v_model == ""

    # init with a string
    file_input = sw.FileInput(folder=str(root_dir))

    assert isinstance(file_input, sw.FileInput)
    assert file_input.v_model == ""

    # get all the names
    assert "pysepal" in get_names(file_input)

    # default init
    file_input = sw.FileInput([".rst"], folder=root_dir)

    assert "LICENSE" not in get_names(file_input)
    assert "AUTHORS.rst" in get_names(file_input)

    return


def test_bind(file_input: sw.FileInput) -> None:
    """Check binding with a model works.

    Args:
        file_input: a widget instance
    """
    # init a model
    class TestModel(Model):
        out = Any(None).tag(sync=True)

    model = TestModel()

    # bind the model to the fileinput
    model.bind(file_input, "out")

    # edit the widget
    path = "toto.ici.shp"
    file_input.v_model = path

    # check that the bind worked as expected
    assert model.out == path
    assert file_input.file_menu.v_model is False

    return


def test_on_file_select(root_dir: Path, file_input: sw.FileInput, readme: Path) -> None:
    """Check that A file can be selected.

    Args:
        root_dir: the path to the root of the repository
        file_input: a instance of the widget
        readme: the path to the readme file
    """
    file_input._on_file_select({"new": root_dir})

    assert file_input.v_model == ""
    assert "README.rst" in get_names(file_input)

    # select readme
    file_input._on_file_select({"new": readme})
    assert file_input.v_model in str(readme)

    # check that select is not changed if nothing is provided
    file_input._on_file_select({"new": None})
    assert file_input.v_model in str(readme)

    return


def test_on_reload(file_input: sw.FileInput, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Check that updating file content is updated when clicking on reload.

    Args:
        file_input: a widget instance
    """
    tmp_path_dir = tmp_path_factory.mktemp("temp")

    # move to the tmp directory
    file_input._on_file_select({"new": tmp_path_dir})

    # assert that the file does not exist
    name = "text.txt"

    assert name not in get_names(file_input)

    # create the file and reload the widget
    tmp_file = tmp_path_dir / name
    tmp_file.write_text("a test \n")
    file_input._on_reload(None, None, None)

    assert name in get_names(file_input)

    # delete the file
    tmp_file.unlink()

    return


def test_reset(file_input: sw.FileInput, root_dir: Path, readme: Path):
    """Reset the control after setting it to readme.

    Args:
        root_dir: the path to the root of the repository
        file_input: a instance of the widget
        readme: the path to the readme file
    """
    # move into pysepal folders
    file_input.select_file(readme)

    # reset to default
    file_input.reset()

    # assert that the folder has been reset
    assert file_input.v_model == ""
    assert file_input.folder != str(root_dir)

    return


def test_select_file(file_input: sw.FileInput, readme: Path) -> None:
    """Check selecting a known file.

    Args:
        file_input: a widget instance
        readme: the path to the readme file
    """
    # move into pysepal folders
    file_input.select_file(readme)

    # assert that the file has been selected
    assert file_input.v_model == str(readme)

    # assert exception if path is not a file
    with pytest.raises(Exception):
        file_input.select_file(readme.parent)

    return


def test_root(file_input: sw.FileInput, root_dir: Path) -> None:
    """Add a root folder to a file_input and check that you can't go higher.

    Args:
        file_input: a widget instance
        root_dir: the path to the root of this repository
    """
    # set the root to the current folder and reload
    file_input.root = str(root_dir)
    file_input._on_reload()

    current_items = file_input.file_list

    # Try to go to the parent root folder
    root_parent = Path(file_input.root).parent

    file_input._on_file_select({"new": root_parent})

    new_items = file_input.file_list

    # Assert that trying to go to the parent root folder does not work
    assert current_items == new_items

    return


@pytest.fixture
def jail(tmp_path: Path) -> Path:
    """A root folder holding one vector file, next to a file outside it."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "inside.geojson").write_text("{}")
    (tmp_path / "outside.geojson").write_text("{}")
    return root


def test_browser_cannot_leave_root(jail: Path) -> None:
    """Folders and files written by the browser are checked against the resolved root.

    Args:
        jail: a root folder with a sibling file outside it
    """
    file_input = sw.FileInput(folder=jail, root=jail)

    # the list group v_model is what a click in the menu writes
    file_input.file_list.children[0].v_model = str(jail / ".." / "..")
    assert file_input.folder == jail

    for trait in ["v_model", "file"]:
        setattr(file_input, trait, str(jail.parent / "outside.geojson"))
        assert getattr(file_input, trait) == ""

    file_input.v_model = str(jail / "inside.geojson")
    assert file_input.v_model == str(jail / "inside.geojson")


def test_root_is_not_writable_from_the_browser(jail: Path) -> None:
    """The browser can't widen the root through the widget state.

    Args:
        jail: a root folder with a sibling file outside it
    """
    file_input = sw.FileInput(folder=jail, root=jail)

    file_input.set_state({"root": ""})

    assert file_input.root == str(jail)


def test_no_local_files_in_a_shared_app(jail: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Where one process serves many users, its disk is nobody's workspace.

    Args:
        jail: a root folder with a sibling file outside it
        monkeypatch: pytest monkeypatch fixture
    """
    from pysepal.sepalwidgets import file_input as file_input_module

    monkeypatch.setattr(file_input_module, "local_files_allowed", lambda: False)
    file_input = sw.FileInput(folder=jail)

    assert get_names(file_input) == []

    file_input.v_model = str(jail / "inside.geojson")
    assert file_input.v_model == ""


@pytest.fixture(scope="function")
def file_input(root_dir: Path) -> sw.FileInput:
    """Create a default file_input in the root_dir.

    Returns:
        an object instance
    """
    return sw.FileInput(folder=root_dir)


def get_names(file_input: sw.FileInput) -> List[str]:
    """Get the list name of a fileinput object.

    Args:
        file_input: a file_input widget

    Returns:
        the names of the current files
    """
    item_list = file_input.file_list.children[0].children

    def get_name(item):
        return item.children[1].children[0].children[0]

    return [get_name(i) for i in item_list]
