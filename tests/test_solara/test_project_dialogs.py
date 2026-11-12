"""The project manager's dialogs, rendered on their own."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import ipyvuetify as v
import solara

from pysepal.message import msg
from pysepal.solara.components.project.dialogs import (
    ConfirmDeleteDialog,
    ManageProjectsDialog,
    NameForm,
)
from pysepal.solara.components.project.store import ProjectInfo


def _texts(widget):
    if isinstance(widget, str):
        return [widget]
    out = []
    for child in getattr(widget, "children", None) or []:
        out += _texts(child)
    return out


def _button(finder, label):
    return next(w for w in finder.find(v.Btn).widgets if label in w.children)


def _icon_buttons(rc, icon):
    return [
        b
        for b in rc.find(v.Btn).widgets
        if any(isinstance(c, v.Icon) and c.children == [icon] for c in b.children)
    ]


def _titles(rc):
    return [w.children[0] for w in rc.find(v.ListItemTitle).widgets]


def _info(name, **kw):
    return ProjectInfo(name, updated_at=datetime.now() - timedelta(minutes=5), **kw)


def _manage(infos, selected=None, **kw):
    def props(ns):
        return dict(
            infos=infos,
            selected=selected,
            on_select=lambda n: ns.calls.append(("select", n)),
            on_open=lambda: ns.calls.append("open"),
            on_rename=lambda n: ns.calls.append(("rename", n)),
            on_delete=lambda n: ns.calls.append(("delete", n)),
            on_cancel=lambda: ns.calls.append("cancel"),
            **kw,
        )

    return _render_with(ManageProjectsDialog, props)


def _render_with(component, props):
    ns = SimpleNamespace(calls=[], open=solara.reactive(True), name=solara.reactive(None))

    @solara.component
    def Page():
        component(open=ns.open.value, **props(ns))

    ns.rc = solara.render(Page(), handle_error=False)[1]
    return ns


def _confirm(name="north", **kw):
    def props(ns):
        ns.name.set(ns.name.value or name)
        return dict(
            name=ns.name.value,
            size_bytes=5_400_000,
            on_cancel=lambda: ns.calls.append("cancel"),
            on_confirm=lambda: ns.calls.append("confirm"),
            **kw,
        )

    return _render_with(ConfirmDeleteDialog, props)


def _name_form(validate=None, **kw):
    def props(ns):
        return dict(
            title="New project",
            validate=validate or (lambda t: "empty" if not t.strip() else None),
            on_submit=lambda n: ns.calls.append(("submit", n)),
            on_cancel=lambda: ns.calls.append("cancel"),
            **kw,
        )

    return _render_with(NameForm, props)


def _open_btn(ns):
    return _button(ns.rc, msg("project.open_selected"))


# --- Manage -----------------------------------------------------------------
def test_manage_empty_shows_text_and_no_search():
    ns = _manage([])
    assert msg("project.list_empty") in _texts(ns.rc.find(v.Dialog).widget)
    assert not ns.rc.find(v.TextField).widgets
    ns.rc.close()


def test_manage_search_filters_ignoring_case_and_reports_no_match():
    ns = _manage([_info("North"), _info("south")])
    search = ns.rc.find(v.TextField, label=msg("project.search")).widget
    search.v_model = "NOR"
    assert _titles(ns.rc) == ["North"]
    search.v_model = "zz"
    assert msg("project.no_match", query="zz") in _texts(ns.rc.find(v.Dialog).widget)
    ns.rc.close()


def test_manage_open_gate():
    infos = [_info("a"), ProjectInfo("bad", readable=False)]
    ns = _manage(infos)
    assert _open_btn(ns).disabled  # nothing selected
    ns.rc.close()
    ns = _manage(infos, selected="a")
    assert not _open_btn(ns).disabled
    ns.rc.find(v.TextField, label=msg("project.search")).widget.v_model = "zz"
    assert _open_btn(ns).disabled  # filtered out
    ns.rc.close()
    assert _open_btn(_manage(infos, selected="bad")).disabled
    assert _open_btn(_manage(infos, selected="a", busy=True)).disabled


def _locks(ns):
    pencils = _icon_buttons(ns.rc, "mdi-pencil-outline")
    trashes = _icon_buttons(ns.rc, "mdi-delete-outline")
    return [b.disabled for b in pencils + trashes]


def test_manage_current_badge_and_lock():
    infos = [_info("a"), _info("b")]
    ns = _manage(infos, current="a", lock_rename=True, lock_delete=True)
    badges = [c for c in ns.rc.find(v.Chip).widgets if c.children == [msg("project.chip_open")]]
    assert len(badges) == 1
    assert _locks(ns) == [True, False, True, False]
    ns.rc.close()
    # Each flag locks only its own action on the open project.
    ns = _manage(infos, current="a", lock_rename=True)
    assert _locks(ns) == [True, False, False, False]
    ns.rc.close()
    ns = _manage(infos, current="a", lock_delete=True)
    assert _locks(ns) == [False, False, True, False]
    ns.rc.close()
    ns = _manage([_info("a")], current="a")
    assert _locks(ns) == [False, False]
    ns.rc.close()


def test_manage_busy_cannot_be_dismissed():
    ns = _manage([_info("a")], busy=True)
    assert ns.rc.find(v.Dialog).widget.persistent is True
    assert _button(ns.rc, msg("project.cancel")).disabled
    ns.rc.close()


def test_manage_search_is_cleared_on_reopen():
    ns = _manage([_info("North"), _info("south")])
    ns.rc.find(v.TextField, label=msg("project.search")).widget.v_model = "nor"
    assert _titles(ns.rc) == ["North"]
    ns.open.set(False)
    ns.open.set(True)
    assert ns.rc.find(v.TextField, label=msg("project.search")).widget.v_model == ""
    assert _titles(ns.rc) == ["North", "south"]
    ns.rc.close()


def test_manage_chips_subtitle_and_sizes():
    infos = [
        _info("a", chips=(("2 x", False), ("1 y", True)), subtitle="Peru"),
        _info("b"),
    ]
    ns = _manage(infos, sizes={"a": 1_400_000_000})
    chips = [c for c in ns.rc.find(v.Chip).widgets]
    assert [(c.children[0], c.color) for c in chips[:2]] == [
        ("2 x", None),
        ("1 y", "primary"),
    ]
    texts = _texts(ns.rc.find(v.Dialog).widget)
    assert "Peru" in texts and "1.4 GB" in texts and "…" in texts
    ns.rc.close()


def test_manage_retain_focus_follows_covered():
    ns = _manage([_info("a")])
    assert ns.rc.find(v.Dialog).widget.retain_focus is True
    ns.rc.close()
    ns = _manage([_info("a")], covered=True)
    assert ns.rc.find(v.Dialog).widget.retain_focus is False
    ns.rc.close()


def test_manage_closing_cancels_and_error_is_shown():
    ns = _manage([_info("a")], error="disk full")
    assert "disk full" in _texts(ns.rc.find(v.Dialog).widget)
    ns.rc.find(v.Dialog).widget.v_model = False
    assert ns.calls == ["cancel"]
    ns.rc.close()


# --- Delete -----------------------------------------------------------------
def _delete_btn(ns):
    return _button(ns.rc, msg("project.delete"))


def test_delete_waits_for_the_exact_name():
    ns = _confirm()
    field = ns.rc.find(v.TextField).widget
    assert _delete_btn(ns).disabled
    field.v_model = "North"
    assert _delete_btn(ns).disabled
    _delete_btn(ns).fire_event("click", None)
    assert ns.calls == []
    field.v_model = " north "
    assert not _delete_btn(ns).disabled
    _delete_btn(ns).fire_event("click", None)
    assert ns.calls == ["confirm"]
    ns.rc.close()


def test_delete_enter_confirms_only_the_matching_name():
    ns = _confirm()
    field = ns.rc.find(v.TextField).widget
    field.v_model = "south"
    field.fire_event("keyup.enter", None)
    assert ns.calls == []
    field.v_model = "north"
    field.fire_event("keyup.enter", None)
    assert ns.calls == ["confirm"]
    ns.rc.close()


def test_delete_blocked_shows_reason_without_field():
    ns = _confirm(blocked="busy writing")
    assert "busy writing" in _texts(ns.rc.find(v.Dialog).widget)
    assert not ns.rc.find(v.TextField).widgets and _delete_btn(ns).disabled
    ns.rc.close()


def test_delete_open_warning_and_busy_hold():
    ns = _confirm(is_open_project=True)
    assert msg("project.delete_open_warning") in _texts(ns.rc.find(v.Dialog).widget)
    ns.rc.close()
    ns = _confirm(busy=True)
    assert ns.rc.find(v.Dialog).widget.persistent is True
    assert _button(ns.rc, msg("project.cancel")).disabled
    ns.rc.close()


def test_delete_new_target_clears_typed_text():
    ns = _confirm()
    field = ns.rc.find(v.TextField).widget
    field.v_model = "north"
    ns.name.set("south")
    assert field.v_model == ""
    ns.rc.close()


# --- Name -------------------------------------------------------------------
def _field(ns):
    return ns.rc.find(v.TextField, label=msg("project.name_label")).widget


def _create_btn(ns):
    return _button(ns.rc, msg("project.create"))


def test_name_live_validation_and_unchanged_initial():
    ns = _name_form(validate=lambda t: "chars" if "!" in t else None)
    assert not _field(ns).error_messages and _create_btn(ns).disabled is False
    _field(ns).v_model = "a!"
    assert _field(ns).error_messages == [msg("project.name_chars")] and _create_btn(ns).disabled
    ns.rc.close()
    ns = _name_form(initial="old")
    assert _create_btn(ns).disabled
    _field(ns).v_model = "new"
    assert not _create_btn(ns).disabled
    ns.rc.close()


def test_name_empty_field_shows_no_error():
    ns = _name_form()
    assert not _field(ns).error_messages
    ns.rc.close()


def test_name_submit_revalidates_and_strips():
    state = {"bad": False}
    ns = _name_form(validate=lambda t: "exists" if state["bad"] else None)
    _field(ns).v_model = "  fresh "
    state["bad"] = True  # taken since the last keystroke
    _create_btn(ns).fire_event("click", None)
    assert ns.calls == []
    state["bad"] = False
    _create_btn(ns).fire_event("click", None)
    assert ns.calls == [("submit", "fresh")]
    ns.rc.close()


def test_name_match_offers_open_existing():
    opened = []
    ns = _name_form(match=lambda t: "Alpha" if t else None, on_open_existing=opened.append)
    _field(ns).v_model = "alpha"
    _button(ns.rc, msg("project.open_instead", name="Alpha")).fire_event("click", None)
    assert opened == ["Alpha"]
    ns.rc.close()


def test_name_enter_submits():
    ns = _name_form()
    _field(ns).v_model = "fresh"
    _field(ns).fire_event("keyup.enter", None)
    assert ns.calls == [("submit", "fresh")]
    ns.rc.close()
