"""ProjectStore: listing, naming, sizing, renaming and deleting project folders."""

import pytest

from pysepal.solara.components.project import ProjectInfo, ProjectStore


def _make(root, name, manifest="project.json"):
    (root / name).mkdir(parents=True)
    (root / name / manifest).write_text("{}")


def test_missing_root_lists_nothing(tmp_path):
    s = ProjectStore(tmp_path / "nope")
    assert s.names() == [] and s.infos() == []


def test_infos_only_folders_with_manifest_sorted_casefold(tmp_path):
    for n in ("beta", "Alpha"):
        _make(tmp_path, n)
    (tmp_path / "no_manifest").mkdir()
    s = ProjectStore(tmp_path)
    assert [i.name for i in s.infos()] == ["Alpha", "beta"]
    assert set(s.names()) == {"Alpha", "beta", "no_manifest"}
    assert s.infos()[0].updated_at is not None and s.infos()[0].readable


def test_describe_none_skips_and_raise_marks_unreadable(tmp_path):
    for n in ("a", "b", "c"):
        _make(tmp_path, n)

    class S(ProjectStore):
        def describe(self, name, folder):
            if name == "a":
                return None
            if name == "b":
                raise ValueError("corrupt")
            return ProjectInfo(name, chips=(("2 things", True),), subtitle="x")

    infos = S(tmp_path).infos()
    assert [(i.name, i.readable) for i in infos] == [("b", False), ("c", True)]


def test_unreadable_project_is_logged(tmp_path, caplog):
    _make(tmp_path, "b")

    class S(ProjectStore):
        def describe(self, name, folder):
            raise ValueError("corrupt")

    S(tmp_path).infos()
    [record] = [r for r in caplog.records if r.exc_info]
    assert record.levelname == "WARNING" and "corrupt" in str(record.exc_info[1])


@pytest.mark.parametrize(
    "name,code",
    [
        ("", "empty"),
        ("  ", "empty"),
        ("a/b", "chars"),
        ("..", "chars"),
        ("ALPHA", "exists"),
        ("new one_2-x", None),
    ],
)
def test_validate_name(tmp_path, name, code):
    _make(tmp_path, "Alpha")
    assert ProjectStore(tmp_path).validate_name(name) == code


def test_validate_name_exclude_and_manifestless_folder(tmp_path):
    _make(tmp_path, "Alpha")
    (tmp_path / "bare").mkdir()
    s = ProjectStore(tmp_path)
    assert s.validate_name("alpha", exclude="Alpha") is None
    assert s.validate_name("bare") == "exists"


def test_size_sums_files_without_following_links(tmp_path):
    _make(tmp_path, "p")
    (tmp_path / "p" / "data.bin").write_bytes(b"x" * 1000)
    big = tmp_path / "outside.bin"
    big.write_bytes(b"x" * 5000)
    (tmp_path / "p" / "link").symlink_to(big)
    assert 1000 <= ProjectStore(tmp_path).size("p") < 5000


def test_rename_moves_folder_and_refuses_existing(tmp_path):
    _make(tmp_path, "a")
    _make(tmp_path, "b")
    s = ProjectStore(tmp_path)
    s.rename("a", "c")
    assert [i.name for i in s.infos()] == ["b", "c"]
    with pytest.raises(FileExistsError):
        s.rename("b", "c")


def test_rename_with_name_pattern_renames_manifest(tmp_path):
    _make(tmp_path, "a", manifest="a_project.json")
    s = ProjectStore(tmp_path, manifest="{name}_project.json")
    s.rename("a", "z")
    assert (tmp_path / "z" / "z_project.json").is_file() and [i.name for i in s.infos()] == ["z"]


def test_delete_removes_folder_keeps_link_target(tmp_path):
    _make(tmp_path, "p")
    (tmp_path / "p" / "sub").mkdir()
    (tmp_path / "p" / "sub" / "f").write_text("x")
    keep = tmp_path / "keep"
    keep.mkdir()
    (keep / "f").write_text("x")
    (tmp_path / "p" / "link").symlink_to(keep, target_is_directory=True)
    ProjectStore(tmp_path).delete("p")
    assert not (tmp_path / "p").exists() and (keep / "f").is_file()


def test_delete_of_a_linked_project_removes_only_the_link(tmp_path):
    target = tmp_path / "elsewhere"
    _make(tmp_path, "elsewhere")
    (target / "data.bin").write_text("x")
    root = tmp_path / "root"
    root.mkdir()
    (root / "p").symlink_to(target, target_is_directory=True)
    ProjectStore(root).delete("p")
    assert not (root / "p").exists() and not (root / "p").is_symlink()
    assert (target / "data.bin").is_file() and (target / "project.json").is_file()


def test_delete_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ProjectStore(tmp_path).delete("gone")


@pytest.mark.parametrize("bad", ["../x", "a/b", "..", ""])
def test_unsafe_names_are_refused(tmp_path, bad):
    s = ProjectStore(tmp_path)
    for call in (s.size, s.delete, lambda n: s.rename(n, "ok"), lambda n: s.rename("ok", n)):
        with pytest.raises(ValueError):
            call(bad)


def test_delete_blocked_default(tmp_path):
    assert ProjectStore(tmp_path).delete_blocked("x") is None
