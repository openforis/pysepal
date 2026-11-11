"""The Project window's content: the open project or Continue, New, Manage, and their dialogs.

Callbacks may be plain or ``async``; the panel awaits them on the kernel's event loop (one
action at a time) and shows a raised error inside the window that started it. The project list,
the folder sizes and the default rename and delete run in worker threads.
"""

import asyncio
import inspect
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional, TypeVar, Union

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg

from .dialogs import (
    ChipRow,
    ConfirmDeleteDialog,
    ManageProjectsDialog,
    MetaLine,
    NameForm,
    _icon_button,
)
from .store import ProjectStore

T = TypeVar("T")
MaybeAwaitable = Union[T, Awaitable[T]]

_CARD = "position:relative;overflow:hidden;border-radius:6px;padding:12px 10px 12px 14px;"
_TINT = "position:absolute;top:0;right:0;bottom:0;left:0;opacity:0.12;pointer-events:none;"
_EDGE = (
    "position:absolute;top:0;right:0;bottom:0;left:0;border:thin solid currentColor;"
    "border-radius:inherit;pointer-events:none;"
)
_GRID = (
    "position:relative;display:grid;grid-template-columns:minmax(0, 1fr) auto;gap:6px 12px;"
    "align-items:center;"
)
_FULL = "grid-column:1 / -1;"
_NAME = "font-weight:700;font-size:1.1rem;overflow-wrap:anywhere;"
_META = "font-size:12px;opacity:0.7;"


async def _call(fn: Callable[..., Any], *args) -> bool:
    """Call ``fn``, awaiting its result when it is awaitable."""
    result = fn(*args)
    if inspect.isawaitable(result):
        result = await result
    return bool(result)


@contextmanager
def _tinted_card():
    with rv.Html(tag="div", style_=_CARD):
        rv.Html(tag="span", class_="primary", style_=_TINT)
        rv.Html(tag="span", class_="primary--text", style_=_EDGE)
        yield


@solara.component
def ProjectPanel(
    store: ProjectStore,
    current: Optional[str] = None,
    *,
    on_open: Callable[[str], MaybeAwaitable[bool]],
    on_create: Callable[[str], MaybeAwaitable[bool]],
    on_duplicate: Optional[Callable[[str], MaybeAwaitable[bool]]] = None,
    on_rename: Optional[Callable[[str, str], MaybeAwaitable[bool]]] = None,
    on_delete: Optional[Callable[[str], MaybeAwaitable[bool]]] = None,
    on_close: Callable[[], None] = lambda: None,
    status: Optional[Callable[[], None]] = None,
    extra_actions: Optional[Callable[[], None]] = None,
    refresh: Any = None,
):
    """The Project window's content, hosted in the app's own dialog.

    Each callback returns True (done: the panel's window closes, and after open, create and
    duplicate ``on_close()`` runs) or False (refused: everything stays as it is); it may raise,
    and its text then shows in the window that started it. Without ``on_rename`` / ``on_delete``
    the panel moves or deletes the folder itself and the open project is locked against both.
    ``status`` renders into the open project's card, ``extra_actions`` under Manage; a change
    of ``refresh`` reads the list again.
    """
    bump, set_bump = solara.use_state(0)
    # The name form: None, or (kind, target) with kind "new", "duplicate" or "rename".
    form, set_form = solara.use_state(None)
    manage_open, set_manage_open = solara.use_state(False)
    # A reactive, not state: Manage's Open reads it right after the row click that set it.
    selected = solara.use_reactive(None)
    # (name, blocked reason) while the delete confirmation is open.
    deleting, set_deleting = solara.use_state(None)
    # (window, text): "panel", "form", "manage" or "delete".
    error, set_error = solara.use_state(None)
    sizes, set_sizes = solara.use_state({})
    # Set by the click that starts an action, before any re-render: Enter and a click can
    # both arrive, and calling the task again would cancel the running callback.
    running = solara.use_ref(False)

    def _again():
        set_bump(lambda n: n + 1)

    # State, not the task's value: that empties while the next read runs.
    infos, set_infos = solara.use_state([])

    # A newer read cancels the one it overtakes, so an older list never lands.
    async def _read():
        set_infos(await asyncio.to_thread(store.infos))

    solara.lab.use_task(
        _read, dependencies=[refresh, current, bump], prefer_threaded=False, raise_error=False
    )
    names = tuple(i.name for i in infos)

    async def _measure():
        if not manage_open:
            return
        for name in names:
            try:
                total = await asyncio.to_thread(store.size, name)
            except OSError:  # removed while counted: its size stays unknown
                continue
            set_sizes(lambda d, name=name, total=total: {**d, name: total})

    solara.lab.use_task(
        _measure, dependencies=[manage_open, names], prefer_threaded=False, raise_error=False
    )

    async def _act(window, fn, args, done):
        try:
            ok = await _call(fn, *args)
        except Exception as exc:
            set_error((window, str(exc)))
            _again()
            return
        finally:
            running.current = False
        if ok:
            done()

    action = solara.lab.use_task(_act, dependencies=None, prefer_threaded=False, raise_error=False)
    busy = action.pending

    def _start(window, fn, args, done):
        if running.current:
            return
        running.current = True
        set_error(None)
        action(window, fn, args, done)

    async def _store_rename(old, new):
        await asyncio.to_thread(store.rename, old, new)
        return True

    async def _store_delete(name):
        await asyncio.to_thread(store.delete, name)
        return True

    def _leave():
        set_form(None)
        set_deleting(None)
        set_manage_open(False)
        on_close()

    def _created():
        _again()
        _leave()

    def _open(name, window):
        if not name:
            return
        if name == current:  # not read again: the app holds it, maybe newer than its disk
            _leave()
            return
        _start(window, on_open, (name,), _leave)

    def _show_form(kind, target=None):
        set_error(None)
        set_form((kind, target))

    def _submit(name):
        kind, target = form
        if kind == "rename":

            def _renamed():
                if selected.peek() == target:
                    selected.set(name)
                set_form(None)
                _again()

            _start("form", on_rename or _store_rename, (target, name), _renamed)
        else:
            _start("form", on_create if kind == "new" else on_duplicate, (name,), _created)

    def _match(typed):
        key = typed.casefold()
        return next(
            (
                i.name
                for i in infos
                if i.readable and i.name != current and i.name.casefold() == key
            ),
            None,
        )

    def _open_manage():
        selected.set(current)
        set_error(None)
        _again()  # another tab may have made or removed a project
        set_manage_open(True)

    def _ask_delete(name):
        if busy:
            return
        set_error(None)
        set_deleting((name, store.delete_blocked(name)))

    def _confirm_delete():
        name = deleting[0]

        def _deleted():
            if selected.peek() == name:
                selected.set(None)
            set_deleting(None)
            _again()

        _start("delete", on_delete or _store_delete, (name,), _deleted)

    def _cancel(close):
        def run():
            if not busy:
                set_error(None)
                close()

        return run

    def _error(window):
        return error[1] if error and error[0] == window else None

    def _alert(text):
        rv.Alert(type="error", dense=True, text=True, class_="mb-0", children=[text])

    mine = next((i for i in infos if i.name == current), None)
    recent = (
        None
        if current
        else max(
            (i for i in infos if i.readable),
            key=lambda i: i.updated_at or datetime.min,
            default=None,
        )
    )
    now = datetime.now()

    with solara.Column(style="gap:8px;padding:8px;"):
        # The dialogs first: a card or button appearing above them would remount them (typed text lost).
        kind, target = form or (None, None)
        NameForm(
            open=form is not None,
            title={
                "new": msg("project.title_new"),
                "duplicate": msg("project.title_duplicate", name=target or ""),
                "rename": msg("project.title_rename", name=target or ""),
            }.get(kind, ""),
            validate=lambda typed: store.validate_name(
                typed, exclude=target if kind == "rename" else None
            ),
            on_submit=_submit,
            on_cancel=_cancel(lambda: set_form(None)),
            action_label=msg("project.rename") if kind == "rename" else None,
            action_icon={"rename": "mdi-pencil-outline", "duplicate": "mdi-content-copy"}.get(
                kind, "mdi-plus"
            ),
            initial=target if kind == "rename" else "",
            # A rename is not a search for a project to open.
            match=(lambda typed: None) if kind == "rename" else _match,
            on_open_existing=lambda name: _open(name, "form"),
            busy=busy,
            error=_error("form"),
        )
        ManageProjectsDialog(
            open=manage_open,
            infos=infos,
            selected=selected.value,
            on_select=selected.set,
            on_open=lambda: _open(selected.peek(), "manage"),
            on_rename=lambda name: _show_form("rename", name),
            on_delete=_ask_delete,
            on_cancel=_cancel(lambda: set_manage_open(False)),
            current=current,
            sizes=sizes,
            busy=busy,
            covered=form is not None or deleting is not None,
            error=_error("manage"),
            lock_current=on_rename is None or on_delete is None,
        )
        delete_name, blocked = deleting or (None, None)
        ConfirmDeleteDialog(
            open=deleting is not None,
            name=delete_name,
            size_bytes=sizes.get(delete_name),
            on_cancel=_cancel(lambda: set_deleting(None)),
            on_confirm=_confirm_delete,
            is_open_project=delete_name is not None and delete_name == current,
            blocked=blocked,
            busy=busy,
            error=_error("delete"),
        )
        if mine is not None:
            with _tinted_card():
                with rv.Html(tag="div", style_=_GRID):
                    solara.Text(mine.name, style=_NAME)
                    with rv.Html(tag="div", style_="display:flex;"):
                        if on_rename is not None:
                            _icon_button(
                                "mdi-pencil-outline",
                                msg("project.rename"),
                                lambda: _show_form("rename", current),
                            )
                        if on_duplicate is not None:
                            _icon_button(
                                "mdi-content-copy",
                                msg("project.duplicate"),
                                lambda: _show_form("duplicate", current),
                            )
                    with rv.Html(tag="div", style_=_FULL):
                        ChipRow(mine)
                    with rv.Html(tag="div", style_=_FULL + _META):
                        MetaLine(mine, now)
                    if status is not None:
                        with rv.Html(tag="div", style_=_FULL):
                            status()
        elif recent is not None:
            with _tinted_card():
                with rv.Html(tag="div", style_=_GRID):
                    with rv.Html(tag="div", style_="display:grid;gap:4px;min-width:0;"):
                        rv.Html(
                            tag="div",
                            class_="primary--text",
                            style_="font-size:12.5px;font-weight:500;",
                            children=[msg("project.continue_title")],
                        )
                        solara.Text(recent.name, style=_NAME)
                        ChipRow(recent)
                        with rv.Html(tag="div", style_=_META):
                            MetaLine(recent, now)
                    solara.Button(
                        msg("project.continue"),
                        icon_name="mdi-folder-open-outline",
                        color="primary",
                        small=True,
                        disabled=busy,
                        on_click=lambda: _open(recent.name, "panel"),
                    )
        if _error("panel"):
            _alert(_error("panel"))
        # New is the filled button only when there is nothing to continue.
        solara.Button(
            msg("project.new"),
            icon_name="mdi-plus",
            color="primary",
            small=True,
            block=True,
            outlined=mine is not None or recent is not None,
            on_click=lambda: _show_form("new"),
        )
        if infos:
            solara.Button(
                msg("project.manage", count=len(infos)),
                icon_name="mdi-folder-multiple-outline",
                color="primary",
                outlined=True,
                small=True,
                block=True,
                on_click=_open_manage,
            )
        if extra_actions is not None:
            extra_actions()
