"""ProjectPanel: the Project window over a real ProjectStore."""

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import ipyvuetify as v
import reacton
import solara

from pysepal.message import msg
from pysepal.solara.components.project import ProjectInfo, ProjectPanel, ProjectStore
from pysepal.solara.components.project._format import size_text

from ._harness import wait_until, walk


def _store(tmp_path, cls=ProjectStore):
    store = cls(tmp_path)
    for name, age in (("old", 2 * 86400), ("recent", 86400)):
        _make(store, name)
        stamp = time.time() - age
        os.utime(store.manifest_path(name), (stamp, stamp))
    return store


def _make(store, name):
    store.folder(name).mkdir(parents=True)
    store.manifest_path(name).write_text("{}")
    (store.folder(name) / "data.bin").write_bytes(b"x" * 100)


def _texts(widget, skip_dialogs=False):
    out = []
    for w in _walk(widget, skip_dialogs):
        out += [c for c in getattr(w, "children", None) or [] if isinstance(c, str)]
    return out


def _walk(widget, skip_dialogs=False):
    if skip_dialogs:
        if isinstance(widget, v.Dialog):
            return
        yield widget
        for child in getattr(widget, "children", None) or []:
            yield from _walk(child, True)
    else:
        yield from walk(widget)


def _buttons(root, skip_dialogs=False):
    return [w for w in _walk(root, skip_dialogs) if isinstance(w, v.Btn)]


def _button(root, label, skip_dialogs=False):
    found = [b for b in _buttons(root, skip_dialogs) if label in b.children]
    return found[0] if found else None


def _icon(root, title, skip_dialogs=True):
    found = [b for b in _buttons(root, skip_dialogs) if (b.attributes or {}).get("title") == title]
    return found[0] if found else None


def _click(btn):
    btn.fire_event("click", None)


def _dialog(root, title):
    """The open dialog whose card title reads ``title``."""
    for d in walk(root):
        if isinstance(d, v.Dialog) and d.v_model and title in _texts(d):
            return d
    return None


def _field(root, label):
    return next(w for w in walk(root) if isinstance(w, v.TextField) and w.label == label)


def _row(root, name):
    return next(w for w in walk(root) if isinstance(w, v.ListItem) and w.value == name)


def _list_titles(root):
    return [w.children[0] for w in walk(root) if isinstance(w, v.ListItemTitle)]


def _session(store, scenario, current=None, record=(), **props):
    """Render the panel on a live loop and let ``scenario(root, ns)`` drive it.

    ``record``: optional callbacks (``"rename"``, ``"duplicate"``) to pass as recorders.
    """
    ns = SimpleNamespace(calls=[], current=solara.reactive(current), refresh=solara.reactive(0))

    def _record(kind, result=True):
        def fn(*args):
            ns.calls.append((kind, *args))
            return result

        return fn

    props.setdefault("on_open", _record("open"))
    props.setdefault("on_create", _record("create"))
    props.setdefault("on_close", lambda: ns.calls.append(("close",)))
    for kind in record:
        props[f"on_{kind}"] = _record(kind)

    @solara.component
    def Page():
        ProjectPanel(store, current=ns.current.value, refresh=ns.refresh.value, **props)

    async def run():
        root, rc = reacton.render(Page(), handle_error=False)
        try:
            await scenario(root, ns)
        finally:
            rc.close()

    asyncio.run(run())
    return ns


async def _loaded(root, name="old"):
    await wait_until(lambda: name in _texts(root))


async def _open_manage(root):
    await wait_until(lambda: _button(root, msg("project.manage", count=2), True) is not None)
    _click(_button(root, msg("project.manage", count=2), True))
    await wait_until(lambda: _dialog(root, msg("project.title_manage")) is not None)


# --- Continue / current -----------------------------------------------------
def test_continue_card_opens_the_most_recent_then_closes(tmp_path):
    async def scenario(root, ns):
        await _loaded(root, "recent")
        texts = _texts(root, skip_dialogs=True)
        assert msg("project.continue_title") in texts
        assert "recent" in texts and "old" not in texts
        _click(_button(root, msg("project.continue"), True))
        await wait_until(lambda: ("close",) in ns.calls)
        assert ns.calls == [("open", "recent"), ("close",)]

    _session(_store(tmp_path), scenario)


def test_continue_card_compares_aware_and_naive_times(tmp_path):
    class Mixed(ProjectStore):
        def describe(self, name, folder):
            when = datetime.now() - timedelta(days=1)
            # "recent" is timezone-aware and newer; "old" is naive local time.
            if name == "recent":
                return ProjectInfo(name, updated_at=when.astimezone() + timedelta(hours=1))
            return ProjectInfo(name, updated_at=when)

    async def scenario(root, ns):
        await _loaded(root, "recent")
        texts = _texts(root, skip_dialogs=True)
        assert msg("project.continue_title") in texts and "old" not in texts

    _session(_store(tmp_path, Mixed), scenario)


def test_open_refused_keeps_the_panel(tmp_path):
    seen = []

    async def on_open(name):
        seen.append(name)
        return False

    async def scenario(root, ns):
        await _loaded(root, "recent")
        _click(_button(root, msg("project.continue"), True))
        await wait_until(lambda: seen == ["recent"])
        await wait_until(lambda: not _button(root, msg("project.continue"), True).disabled)
        assert ("close",) not in ns.calls

    _session(_store(tmp_path), scenario, on_open=on_open)


def test_current_card_and_opening_current_only_closes(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        texts = _texts(root, skip_dialogs=True)
        assert "old" in texts and msg("project.continue_title") not in texts
        await _open_manage(root)
        assert _row(root, "old")  # the list was read
        manage = _dialog(root, msg("project.title_manage"))
        # Manage opens with nothing selected; pick the open project and Open.
        group = next(w for w in walk(manage) if isinstance(w, v.ListItemGroup))
        group.v_model = "old"
        _click(_button(manage, msg("project.open_selected")))
        await wait_until(lambda: ("close",) in ns.calls)
        assert ns.calls == [("close",)]

    _session(_store(tmp_path), scenario, current="old")


def test_no_projects_shows_only_new(tmp_path):
    store = ProjectStore(tmp_path)
    _make(store, "only")

    async def scenario(root, ns):
        await _loaded(root, "only")
        shutil.rmtree(tmp_path / "only")
        ns.refresh.set(1)
        # Its name leaving the screen is the empty read landing.
        await wait_until(lambda: "only" not in _texts(root))
        texts = _texts(root, True)
        assert msg("project.continue_title") not in texts
        assert not [t for t in texts if t.startswith(msg("project.manage", count=0)[:6])]
        assert _button(root, msg("project.new"), True) is not None

    _session(store, scenario)


# --- New ----------------------------------------------------------------------
async def _new_form(root, name):
    await wait_until(lambda: _button(root, msg("project.new"), True) is not None)
    _click(_button(root, msg("project.new"), True))
    await wait_until(lambda: _dialog(root, msg("project.title_new")) is not None)
    _field(root, msg("project.name_label")).v_model = name


def test_create_runs_once_then_closes(tmp_path):
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def on_create(name):
        calls.append(name)
        started.set()
        await release.wait()
        return True

    async def scenario(root, ns):
        await _new_form(root, "x")
        create = _button(root, msg("project.create"))
        _click(create)
        _click(create)
        await asyncio.wait_for(started.wait(), 3)
        _click(_button(root, msg("project.create")))
        assert ("close",) not in ns.calls
        release.set()
        await wait_until(lambda: ("close",) in ns.calls)
        assert calls == ["x"]
        assert _dialog(root, msg("project.title_new")) is None

    _session(_store(tmp_path), scenario, on_create=on_create)


def test_create_refused_keeps_the_form(tmp_path):
    returned = asyncio.Event()

    async def on_create(name):
        returned.set()
        return False

    async def scenario(root, ns):
        await _new_form(root, "x")
        _click(_button(root, msg("project.create")))
        await asyncio.wait_for(returned.wait(), 3)
        await wait_until(lambda: not _button(root, msg("project.create")).loading)
        assert _dialog(root, msg("project.title_new")) is not None
        assert ("close",) not in ns.calls

    _session(_store(tmp_path), scenario, on_create=on_create)


def test_create_error_shows_in_the_form_and_retry_works(tmp_path):
    attempts = []

    def on_create(name):
        attempts.append(name)
        if len(attempts) == 1:
            raise RuntimeError("disk full")
        return True

    async def scenario(root, ns):
        await _new_form(root, "x")
        _click(_button(root, msg("project.create")))
        await wait_until(lambda: "disk full" in _texts(root))
        form = _dialog(root, msg("project.title_new"))
        assert form is not None and "disk full" in _texts(form)
        assert not _button(root, msg("project.create")).loading
        _click(_button(root, msg("project.create")))
        await wait_until(lambda: ("close",) in ns.calls)
        assert attempts == ["x", "x"]

    _session(_store(tmp_path), scenario, on_create=on_create)


# --- Rename -------------------------------------------------------------------
async def _rename_row(root, name, new):
    _click(_icon(_row(root, name), msg("project.rename"), False))
    title = msg("project.title_rename", name=name)
    await wait_until(lambda: _dialog(root, title) is not None)
    _field(root, msg("project.name_label")).v_model = new
    _click(_button(_dialog(root, title), msg("project.rename")))


def test_default_rename_moves_the_folder(tmp_path):
    store = _store(tmp_path)

    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        await _rename_row(root, "recent", "renamed")
        await wait_until(lambda: "renamed" in _list_titles(root))
        assert (tmp_path / "renamed").is_dir() and not (tmp_path / "recent").exists()
        assert "recent" not in _list_titles(root)

    _session(store, scenario, current="old")


def test_current_is_locked_without_callbacks(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        assert _icon(root, msg("project.rename")) is None
        await _open_manage(root)
        assert _icon(_row(root, "old"), msg("project.rename"), False).disabled
        assert not _icon(_row(root, "recent"), msg("project.rename"), False).disabled

    _session(_store(tmp_path), scenario, current="old")


def test_on_rename_given_renames_current_from_the_card(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        _click(_icon(root, msg("project.rename")))
        title = msg("project.title_rename", name="old")
        await wait_until(lambda: _dialog(root, title) is not None)
        _field(root, msg("project.name_label")).v_model = "new"
        _click(_button(_dialog(root, title), msg("project.rename")))
        await wait_until(lambda: _dialog(root, title) is None)
        assert ns.calls == [("rename", "old", "new")]
        assert (tmp_path / "old").is_dir()  # the app's callback, not store.rename

    _session(_store(tmp_path), scenario, current="old", record=("rename",))


# --- Delete -------------------------------------------------------------------
async def _ask_delete(root, name):
    _click(_icon(_row(root, name), msg("project.delete"), False))
    title = msg("project.delete_title", name=name)
    await wait_until(lambda: _dialog(root, title) is not None)
    return title


def test_default_delete_removes_the_folder(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        title = await _ask_delete(root, "recent")
        _field(root, msg("project.delete_type_label", name="recent")).v_model = "recent"
        _click(_button(_dialog(root, title), msg("project.delete")))
        await wait_until(lambda: "recent" not in _list_titles(root))
        assert not (tmp_path / "recent").exists()
        assert _dialog(root, title) is None
        assert _dialog(root, msg("project.title_manage")) is not None

    _session(_store(tmp_path), scenario, current="old")


def test_delete_of_a_vanished_folder_shows_the_error_and_rereads(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        title = await _ask_delete(root, "recent")
        shutil.rmtree(tmp_path / "recent")
        _field(root, msg("project.delete_type_label", name="recent")).v_model = "recent"
        _click(_button(_dialog(root, title), msg("project.delete")))
        await wait_until(lambda: "recent" not in _list_titles(root))
        dialog = _dialog(root, title)  # still open, with the disk's error in it
        assert dialog is not None and any("No such file" in t for t in _texts(dialog))

    _session(_store(tmp_path), scenario, current="old")


def test_delete_blocked_on_open_shows_the_reason_and_no_field(tmp_path):
    class Busy(ProjectStore):
        def delete_blocked(self, name):
            return "writing"

    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        title = await _ask_delete(root, "recent")
        dialog = _dialog(root, title)
        assert "writing" in _texts(dialog)
        assert not [w for w in walk(dialog) if isinstance(w, v.TextField)]
        assert _button(dialog, msg("project.delete")).disabled

    _session(_store(tmp_path, Busy), scenario, current="old")


def test_delete_blocked_since_the_confirmation_opened_never_deletes(tmp_path):
    asked, deleted = [], []

    class Busy(ProjectStore):
        def delete_blocked(self, name):
            asked.append(name)
            return "writing" if len(asked) > 1 else None  # a writer starts after it opened

        def delete(self, name):
            deleted.append(name)

    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        title = await _ask_delete(root, "recent")
        _field(root, msg("project.delete_type_label", name="recent")).v_model = "recent"
        _click(_button(_dialog(root, title), msg("project.delete")))
        # The refusal landing in the still-open confirmation is the press handled.
        await wait_until(lambda: "writing" in _texts(_dialog(root, title) or root))
        assert not _button(_dialog(root, title), msg("project.delete")).loading
        assert deleted == [] and (tmp_path / "recent").is_dir()

    _session(_store(tmp_path, Busy), scenario, current="old")


def test_delete_shows_the_measured_size(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        await _open_manage(root)
        title = await _ask_delete(root, "recent")
        expected = msg("project.delete_size", size=size_text(102))
        await wait_until(lambda: expected in _texts(_dialog(root, title)))

    _session(_store(tmp_path), scenario, current="old")


# --- Refresh, slots, duplicate ------------------------------------------------
def test_refresh_reads_the_list_again(tmp_path):
    store = _store(tmp_path)

    async def scenario(root, ns):
        await _loaded(root, "recent")
        _make(store, "zeta")
        os.utime(store.manifest_path("zeta"))
        ns.refresh.set(1)
        await wait_until(lambda: "zeta" in _texts(root, True))
        assert msg("project.manage", count=3) in _texts(root, True)

    _session(store, scenario)


def test_status_and_extra_actions_render(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        texts = _texts(root, True)
        assert "saved just now" in texts and "Import" in texts

    _session(
        _store(tmp_path),
        scenario,
        current="old",
        status=lambda: solara.Text("saved just now"),
        extra_actions=lambda: solara.Text("Import"),
    )


def test_duplicate_submits_the_new_name(tmp_path):
    async def scenario(root, ns):
        await _loaded(root)
        _click(_icon(root, msg("project.duplicate")))
        title = msg("project.title_duplicate", name="old")
        await wait_until(lambda: _dialog(root, title) is not None)
        _field(root, msg("project.name_label")).v_model = "copy"
        _click(_button(_dialog(root, title), msg("project.create")))
        await wait_until(lambda: ("close",) in ns.calls)
        assert ns.calls == [("duplicate", "copy"), ("close",)]

    _session(_store(tmp_path), scenario, current="old", record=("duplicate",))
