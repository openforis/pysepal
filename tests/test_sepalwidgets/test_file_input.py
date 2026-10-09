"""Test the FileInput widget in pysepal.sepalwidgets.file_input."""

from pathlib import Path

import pytest

from pysepal.sepalwidgets import file_input as file_input_module
from pysepal.sepalwidgets.file_input import FileInput


def test_select_file_accepts_path(tmp_path: Path) -> None:
    """select_file must accept a Path and store string traits.

    current_folder is a Unicode trait, so assigning a Path raised a TraitError.
    """
    csv = tmp_path / "classes.csv"
    csv.write_text("lc_class,desc,color\n1,a,#000000\n")

    file_input = FileInput(initial_folder=str(tmp_path), root=str(tmp_path))
    file_input.select_file(csv)

    assert file_input.value == str(csv)
    assert file_input.current_folder == str(tmp_path)


def test_select_file_accepts_str(tmp_path: Path) -> None:
    """select_file must also accept a plain string path (str has no .parent)."""
    csv = tmp_path / "classes.csv"
    csv.write_text("lc_class,desc,color\n1,a,#000000\n")

    file_input = FileInput(initial_folder=str(tmp_path), root=str(tmp_path))
    file_input.select_file(str(csv))

    assert file_input.value == str(csv)
    assert file_input.current_folder == str(tmp_path)


@pytest.fixture
def jail(tmp_path: Path) -> Path:
    """A root folder holding one vector file, next to a file outside it."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "inside.geojson").write_text("{}")
    (tmp_path / "outside.geojson").write_text("{}")
    return root


def test_current_folder_cannot_climb_above_root(jail: Path) -> None:
    """A folder written by the browser is resolved, so ``..`` can't leave the root."""
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    file_input.current_folder = str(jail / ".." / "..")

    assert file_input.current_folder == str(jail)
    assert [f["name"] for f in file_input.file_list] == ["inside.geojson"]


def test_symlink_cannot_lead_out_of_root(jail: Path) -> None:
    """A symlink inside the root is followed before the check."""
    (jail / "escape").symlink_to(jail.parent, target_is_directory=True)
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    file_input.current_folder = str(jail / "escape")

    assert file_input.current_folder == str(jail)


@pytest.mark.parametrize("trait", ["value", "v_model", "file"])
def test_selection_outside_root_is_refused(jail: Path, trait: str) -> None:
    """Every synced selection trait refuses a path outside the root."""
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    setattr(file_input, trait, str(jail.parent / "outside.geojson"))
    assert getattr(file_input, trait) == ""

    setattr(file_input, trait, str(jail / "inside.geojson"))
    assert getattr(file_input, trait) == str(jail / "inside.geojson")


def test_root_is_not_writable_from_the_browser(jail: Path) -> None:
    """The browser can't widen the root through the widget state."""
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    file_input.set_state({"root": "/"})

    assert file_input.root == str(jail)


def test_no_local_files_in_a_shared_app(jail: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Where one process serves many users, its disk is nobody's workspace."""
    monkeypatch.setattr(file_input_module, "local_files_allowed", lambda: False)
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    assert file_input.file_list == []
    assert file_input.error_messages

    file_input.value = str(jail / "inside.geojson")
    assert file_input.value == ""
