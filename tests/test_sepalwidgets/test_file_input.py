"""Test the FileInput widget in pysepal.sepalwidgets.file_input."""

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from traitlets import TraitError

from pysepal.scripts.filesystem import (
    FileDetails,
    ListDirectoryResponse,
    LocalFileSystem,
    SandboxFileSystem,
)
from pysepal.sepalwidgets.file_input import FileInput
from pysepal.solara import session_manager
from pysepal.solara import utils as solara_utils
from pysepal.solara._topology import SessionPlan, SessionSource

PER_CONNECTION = SessionPlan(SessionSource.PER_CONNECTION, "test")


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


def test_a_symlink_then_dotdot_is_refused(jail: Path) -> None:
    """The browser can't reach a file through ``link/..`` either."""
    (jail.parent / "other" / "deep").mkdir(parents=True)
    (jail.parent / "other" / "secret.csv").write_text("")
    (jail / "link").symlink_to(jail.parent / "other" / "deep", target_is_directory=True)
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    file_input.set_state({"value": str(jail / "link" / ".." / "secret.csv")})

    assert file_input.value == ""


def test_the_root_bounds_a_wider_filesystem(jail: Path) -> None:
    """A root narrower than the filesystem's is enforced by the input itself."""
    (jail / "escape").symlink_to(jail.parent, target_is_directory=True)
    file_input = FileInput(filesystem=LocalFileSystem(jail.parent), root=str(jail))

    file_input.current_folder = str(jail / "escape")
    assert file_input.current_folder == str(jail)

    file_input.value = str(jail.parent / "outside.geojson")
    assert file_input.value == ""


def test_a_relative_initial_folder_is_taken_from_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locally as on SEPAL, where the workspace root is the home folder."""
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    tasks = tmp_path / "module_results" / "app" / "tasks"
    tasks.mkdir(parents=True)

    file_input = FileInput(
        initial_folder="module_results/app/tasks", root=str(tmp_path / "module_results" / "app")
    )

    assert file_input.current_folder == str(tasks)


def test_root_is_not_writable_from_the_browser(jail: Path) -> None:
    """The browser can't widen the root through the widget state."""
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    file_input.set_state({"root": "/"})

    assert file_input.root == str(jail)


def test_remote_selection_stays_within_a_narrow_root() -> None:
    """The SEPAL workspace bound does not replace the picker's narrower root."""
    root = "/home/sepal-user/allowed"
    files = SimpleNamespace(
        list=lambda folder, extensions=None: SimpleNamespace(path=folder, files=[])
    )
    file_input = FileInput(
        initial_folder=root,
        root=root,
        sepal_client=SimpleNamespace(files=files),
    )

    file_input.set_state({"current_folder": "/home/sepal-user/private"})
    assert file_input.current_folder == root

    file_input.set_state({"value": "/home/sepal-user/private/secret.csv"})
    assert file_input.value == ""

    file_input.set_state({"value": "../private/secret.csv"})
    assert file_input.value == ""

    file_input.set_state({"value": f"{root}/visible.csv"})
    assert file_input.value == f"{root}/visible.csv"

    file_input.set_state({"value": "allowed/visible.csv"})
    assert file_input.value == "allowed/visible.csv"


def test_no_files_in_a_shared_app_without_a_session(
    jail: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where one process serves many users, its disk is nobody's workspace."""
    monkeypatch.setattr(session_manager, "_current_plan", lambda: PER_CONNECTION)
    file_input = FileInput(initial_folder=str(jail), root=str(jail))

    assert file_input.filesystem is None
    assert file_input.file_list == []
    assert file_input.error_messages

    file_input.value = str(jail / "inside.geojson")
    assert file_input.value == ""


def test_a_shared_app_browses_the_users_workspace(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a session, the default filesystem is the user's SEPAL workspace."""
    workspace = SandboxFileSystem(client=None)
    monkeypatch.setattr(session_manager, "_current_plan", lambda: PER_CONNECTION)
    monkeypatch.setattr(solara_utils, "get_current_filesystem", lambda: workspace)
    monkeypatch.setattr(
        SandboxFileSystem,
        "list",
        lambda self, folder=None, extensions=None: ListDirectoryResponse(
            path=str(folder),
            files=[FileDetails(name="a.csv", path=f"{folder}/a.csv", type="file", size=1)],
        ),
    )

    file_input = FileInput(initial_folder="data")

    assert file_input.filesystem is workspace
    assert file_input.root == "/home/sepal-user"
    assert file_input.current_folder == "/home/sepal-user/data"
    assert [f["name"] for f in file_input.file_list] == ["..", "a.csv"]

    file_input.value = "/home/sepal-user/data/a.csv"
    assert file_input.v_model == "/home/sepal-user/data/a.csv"
    file_input.value = "/etc/passwd"
    assert file_input.v_model == ""


def test_a_root_outside_the_workspace_shows_no_files() -> None:
    """A container path handed to a SEPAL workspace is not an error, just empty."""
    file_input = FileInput(filesystem=SandboxFileSystem(client=None), root="/opt/app/data")

    assert file_input.filesystem is None
    assert file_input.file_list == []
    assert file_input.error_messages


def test_an_initial_folder_outside_the_root_opens_the_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container path as the first folder falls back to the workspace root."""
    monkeypatch.setattr(
        SandboxFileSystem,
        "list",
        lambda self, folder=None, extensions=None: ListDirectoryResponse(
            path=str(folder), files=[]
        ),
    )

    file_input = FileInput(
        filesystem=SandboxFileSystem(client=None), initial_folder="/opt/app/data"
    )

    assert file_input.current_folder == "/home/sepal-user"


def test_an_explicit_filesystem_is_browsed(jail: Path) -> None:
    """Any FileSystem can back the input."""
    file_input = FileInput(filesystem=LocalFileSystem(jail))

    assert file_input.root == str(jail)
    assert [f["name"] for f in file_input.file_list] == ["inside.geojson"]


@pytest.fixture
def batch(jail: Path) -> Path:
    """A root with files in two folders, so a selection can span both."""
    (jail / "a.csv").write_text("")
    (jail / "sub").mkdir()
    (jail / "sub" / "b.csv").write_text("")
    (jail / "sub" / "c.tif").write_text("")
    return jail


def test_multiple_mode_holds_a_list(batch: Path) -> None:
    """With multiple=True every selection trait is a list, empty by default."""
    file_input = FileInput(root=str(batch), multiple=True)

    assert file_input.value == []
    assert file_input.v_model == []

    file_input.value = [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]

    assert file_input.v_model == [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]
    assert file_input.file == file_input.v_model


def test_multiple_mode_takes_an_initial_list(batch: Path) -> None:
    file_input = FileInput(root=str(batch), multiple=True, v_model=[str(batch / "a.csv")])

    assert file_input.v_model == [str(batch / "a.csv")]


def test_select_file_adds_to_the_selection(batch: Path) -> None:
    """select_file adds a path once, in the order the files were picked."""
    file_input = FileInput(root=str(batch), multiple=True)

    file_input.select_file(batch / "sub" / "b.csv")
    file_input.select_file(batch / "a.csv")
    file_input.select_file(batch / "a.csv")

    assert file_input.value == [str(batch / "sub" / "b.csv"), str(batch / "a.csv")]


def test_the_selection_survives_a_folder_change(batch: Path) -> None:
    """A batch can span folders: entering another one keeps what was picked."""
    file_input = FileInput(root=str(batch), multiple=True)
    file_input.set_state({"value": [str(batch / "a.csv")]})

    file_input.set_state({"current_folder": str(batch / "sub")})
    file_input.set_state({"value": [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]})

    assert file_input.current_folder == str(batch / "sub")
    assert file_input.v_model == [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]


def test_multiple_mode_lists_only_the_extensions_asked(batch: Path) -> None:
    file_input = FileInput(
        initial_folder=str(batch / "sub"), root=str(batch), multiple=True, extensions=[".csv"]
    )

    assert [f["name"] for f in file_input.file_list] == ["..", "b.csv"]


def test_reset_clears_the_whole_selection(batch: Path) -> None:
    file_input = FileInput(root=str(batch), multiple=True)
    file_input.value = [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]

    file_input.reset()

    assert file_input.value == []
    assert file_input.v_model == []


@pytest.mark.parametrize("trait", ["value", "v_model", "file"])
def test_each_path_of_a_list_is_checked_against_the_root(batch: Path, trait: str) -> None:
    """A list from the browser is never trusted: paths outside the root are dropped."""
    (batch / "link").symlink_to(batch.parent, target_is_directory=True)
    file_input = FileInput(root=str(batch), multiple=True)

    file_input.set_state(
        {
            trait: [
                str(batch / "a.csv"),
                str(batch.parent / "outside.geojson"),
                str(batch / ".." / "outside.geojson"),
                str(batch / "link" / "outside.geojson"),
                str(batch / "sub" / "b.csv"),
            ]
        }
    )

    assert getattr(file_input, trait) == [str(batch / "a.csv"), str(batch / "sub" / "b.csv")]


def test_a_list_drops_duplicates(batch: Path) -> None:
    file_input = FileInput(root=str(batch), multiple=True)

    file_input.value = [str(batch / "a.csv"), str(batch / "a.csv")]

    assert file_input.value == [str(batch / "a.csv")]


def test_multiple_mode_wraps_a_single_path(batch: Path) -> None:
    """A str given to a multiple input, e.g. by a bound model, becomes a one-item list."""
    file_input = FileInput(root=str(batch), multiple=True)

    file_input.v_model = str(batch / "a.csv")
    assert file_input.v_model == [str(batch / "a.csv")]

    file_input.v_model = ""
    assert file_input.v_model == []


def test_single_mode_refuses_a_list(batch: Path) -> None:
    """Single mode keeps its str value; a list there is a caller error, not a selection."""
    file_input = FileInput(root=str(batch))

    with pytest.raises(TraitError):
        file_input.v_model = [str(batch / "a.csv")]
    assert file_input.v_model == ""


def test_changing_the_mode_clears_the_selection(batch: Path) -> None:
    file_input = FileInput(root=str(batch))
    file_input.value = str(batch / "a.csv")

    file_input.multiple = True
    assert file_input.value == []
    assert file_input.v_model == []

    file_input.value = [str(batch / "a.csv")]
    file_input.multiple = False
    assert file_input.value == ""
    assert file_input.v_model == ""


def test_the_mode_is_not_writable_from_the_browser(batch: Path) -> None:
    """The app decides whether it receives a str or a list, not the browser."""
    file_input = FileInput(root=str(batch))

    file_input.set_state({"multiple": True})

    assert file_input.multiple is False
    assert file_input.v_model == ""


def test_remote_list_stays_within_a_narrow_root() -> None:
    """On the SEPAL workspace too, each path of the list must be in the input's root."""
    root = "/home/sepal-user/allowed"
    files = SimpleNamespace(
        list=lambda folder, extensions=None: SimpleNamespace(path=folder, files=[])
    )
    file_input = FileInput(
        initial_folder=root,
        root=root,
        sepal_client=SimpleNamespace(files=files),
        multiple=True,
    )

    file_input.set_state(
        {
            "value": [
                f"{root}/a.csv",
                "/home/sepal-user/private/secret.csv",
                "../private/secret.csv",
                "allowed/b.csv",
                "/etc/passwd",
            ]
        }
    )

    assert file_input.value == [f"{root}/a.csv", "allowed/b.csv"]


def test_no_files_refuses_every_path_of_a_list(jail: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a filesystem, a multiple input selects nothing."""
    monkeypatch.setattr(session_manager, "_current_plan", lambda: PER_CONNECTION)
    file_input = FileInput(initial_folder=str(jail), root=str(jail), multiple=True)

    file_input.value = [str(jail / "inside.geojson")]

    assert file_input.value == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_selection_logic() -> None:
    """The Vue side toggles files, keeps them across folders and clears them all."""
    harness = Path(__file__).parents[1] / "js" / "file_input_selection.mjs"
    vue = Path(__file__).parents[2] / "pysepal" / "sepalwidgets" / "vue" / "FileInput.vue"
    subprocess.run(["node", str(harness), str(vue)], check=True, capture_output=True, text=True)
