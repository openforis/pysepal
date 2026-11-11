"""Presentational dialogs of the project manager: manage, delete confirmation and name form.

Every action is a callback; nothing here touches the disk. The caller owns the state.
"""

from datetime import datetime
from typing import Callable, Optional

import reacton.ipyvuetify as rv
import solara
from reacton import ipyvue

from pysepal.message import msg

from ._format import relative_time, size_text
from .store import ProjectInfo

_MUTED = "opacity:0.7;"
_META = "display:flex;flex-wrap:wrap;gap:0 12px;align-items:center;"
# Right-aligned with tabular digits, so the sizes line up from row to row.
_SIZE = "font-size:13px;font-weight:500;font-variant-numeric:tabular-nums;min-width:56px;text-align:right;"
_ACTIONS = "justify-content:flex-end;gap:8px;"
_NAME_ERRORS = {
    "empty": "project.name_empty",
    "chars": "project.name_chars",
    "exists": "project.name_exists",
}


def ChipRow(info: ProjectInfo):
    """A project's chips, accented ones in the primary color."""
    with rv.Html(tag="div", style_="display:flex;flex-wrap:wrap;gap:4px;margin:2px 0;"):
        for label, accent in info.chips:
            rv.Chip(
                children=[label],
                x_small=True,
                color="primary" if accent else None,
                text_color="white" if accent else None,
            )


def MetaLine(info: ProjectInfo, now: datetime):
    """A project's subtitle (with its icon) and its age, side by side."""
    with rv.Html(tag="div", style_=_META):
        if not info.readable:
            solara.Text(msg("project.unreadable"))
            return
        if info.subtitle:
            with rv.Html(
                tag="span", style_="display:inline-flex;align-items:center;gap:3px;"
            ):
                if info.subtitle_icon:
                    rv.Icon(x_small=True, children=[info.subtitle_icon])
                solara.Text(info.subtitle)
        if info.updated_at is not None:
            solara.Text(
                msg("project.modified", time_ago=relative_time(info.updated_at, now))
            )


def _icon_button(icon: str, label: str, on_click, color=None, disabled=False):
    solara.Button(
        icon_name=icon,
        icon=True,
        small=True,
        color=color,
        disabled=disabled,
        on_click=on_click,
        attributes={"title": label, "aria-label": label},
    )


@solara.component
def ManageProjectsDialog(
    open: bool,
    infos: list[ProjectInfo],
    selected: Optional[str],
    on_select,
    on_open,
    on_rename,
    on_delete,
    on_cancel,
    current: Optional[str] = None,
    sizes: Optional[dict[str, int]] = None,
    busy: bool = False,
    covered: bool = False,
    error: Optional[str] = None,
    lock_current: bool = False,
):
    """Search, open, rename and delete the saved projects.

    ``covered``: a dialog opened from this one is on top. Two open dialogs that both retain
    focus pull it back and forth, so this one lets go. Only the list scrolls.
    """
    sizes = sizes or {}
    query, set_query = solara.use_state("")

    # A filter left from the last time would hide rows on this opening.
    def _reset_query():
        if open:
            set_query("")

    solara.use_effect(_reset_query, [open])

    needle = (query or "").strip()
    shown = [i for i in infos if needle.lower() in i.name.lower()]
    now = datetime.now()
    # Open never fires on nothing, on an unreadable project, nor on a selection the search hides.
    target = next((i for i in shown if i.name == selected), None)
    open_disabled = busy or target is None or not target.readable

    with rv.Dialog(
        v_model=open,
        on_v_model=lambda v: None if v else on_cancel(),
        max_width="520px",
        eager=True,
        retain_focus=not covered,
        scrollable=True,
    ):
        with rv.Card():
            rv.CardTitle(children=[msg("project.title_manage")])
            # Outside the card text, which is what a scrollable dialog scrolls.
            with rv.Html(tag="div", class_="px-6 pb-3", style_="flex:0 0 auto;"):
                if infos:
                    rv.TextField(
                        label=msg("project.search"),
                        v_model=query,
                        on_v_model=lambda v: set_query(v or ""),
                        prepend_inner_icon="mdi-magnify",
                        dense=True,
                        outlined=True,
                        clearable=True,
                        hide_details=True,
                    )
                if error:
                    rv.Alert(
                        type="error",
                        dense=True,
                        text=True,
                        class_="mt-3 mb-0",
                        children=[error],
                    )
            rv.Divider()
            with rv.CardText(style_="max-height:60vh;"):
                if not infos:
                    solara.Text(msg("project.list_empty"), style=_MUTED)
                elif not shown:
                    solara.Text(msg("project.no_match", query=needle), style=_MUTED)
                else:
                    with rv.List(three_line=True):
                        with rv.ListItemGroup(
                            v_model=selected, on_v_model=on_select, color="primary"
                        ):
                            for info in shown:
                                locked = lock_current and info.name == current
                                with rv.ListItem(value=info.name):
                                    with rv.ListItemContent():
                                        title = [info.name]
                                        if info.name == current:
                                            title.append(
                                                rv.Chip(
                                                    children=[msg("project.chip_open")],
                                                    x_small=True,
                                                    outlined=True,
                                                    color="primary",
                                                    class_="ml-2",
                                                )
                                            )
                                        rv.ListItemTitle(children=title)
                                        ChipRow(info)
                                        with rv.ListItemSubtitle():
                                            MetaLine(info, now)
                                    with rv.ListItemAction(
                                        style_="flex-direction:row;align-items:center;gap:2px;"
                                    ):
                                        size = sizes.get(info.name)
                                        rv.Html(
                                            tag="span",
                                            children=[size_text(size)],
                                            style_=_SIZE
                                            + ("opacity:0.5;" if size is None else ""),
                                            attributes={
                                                "title": msg("project.size_on_disk")
                                            },
                                        )
                                        _icon_button(
                                            "mdi-pencil-outline",
                                            msg("project.rename"),
                                            lambda n=info.name: on_rename(n),
                                            disabled=locked,
                                        )
                                        _icon_button(
                                            "mdi-delete-outline",
                                            msg("project.delete"),
                                            lambda n=info.name: on_delete(n),
                                            color="error",
                                            disabled=locked,
                                        )
            rv.Divider()
            with rv.CardActions(style_=_ACTIONS):
                solara.Button(
                    msg("project.cancel"), text=True, small=True, on_click=on_cancel
                )
                solara.Button(
                    msg("project.open_selected"),
                    icon_name="mdi-folder-open-outline",
                    color="primary",
                    small=True,
                    disabled=open_disabled,
                    on_click=on_open,
                )


@solara.component
def _TypeField(name, typed, set_typed, on_enter):
    field = rv.TextField(
        label=msg("project.delete_type_label", name=name),
        v_model=typed,
        on_v_model=lambda v: set_typed(v or ""),
        dense=True,
        outlined=True,
        autofocus=True,
        hide_details=True,
        class_="mt-6",
    )
    ipyvue.use_event(field, "keyup.enter", lambda *_: on_enter())


@solara.component
def ConfirmDeleteDialog(
    open: bool,
    name: Optional[str],
    size_bytes: Optional[int],
    on_cancel,
    on_confirm,
    is_open_project: bool = False,
    blocked: Optional[str] = None,
    busy: bool = False,
    error: Optional[str] = None,
):
    """Type-the-name confirmation for deleting a project's whole folder.

    ``blocked``: why the delete is refused (shown instead of the name field).
    ``busy``: the delete runs, so the dialog cannot be dismissed.
    """
    typed, set_typed = solara.use_state("")

    # Never carry a name typed for one target into the next confirmation.
    def _reset_typed():
        if open:
            set_typed("")

    solara.use_effect(_reset_typed, [open, name])

    # Exact and case-sensitive (the folder goes); only blanks around it are forgiven.
    can_delete = (
        bool(name) and (typed or "").strip() == name and not blocked and not busy
    )

    def _confirm_if_typed():
        # A press sent before the last keystroke reached the kernel still lands here.
        if can_delete:
            on_confirm()

    size = (
        msg("project.size_counting")
        if size_bytes is None
        else msg("project.delete_size", size=size_text(max(size_bytes, 1)))
    )

    with rv.Dialog(
        v_model=open,
        on_v_model=lambda v: None if v else on_cancel(),
        max_width="420px",
        eager=True,
        # ESC or a click outside must not dismiss a delete that is running.
        persistent=busy,
    ):
        with rv.Card():
            rv.CardTitle(children=[msg("project.delete_title", name=name or "")])
            with rv.CardText():
                solara.Text(size)
                if blocked:
                    rv.Alert(
                        type="error",
                        dense=True,
                        text=True,
                        class_="mt-4 mb-0",
                        children=[blocked],
                    )
                elif is_open_project:
                    rv.Alert(
                        type="warning",
                        dense=True,
                        text=True,
                        class_="mt-4 mb-0",
                        children=[msg("project.delete_open_warning")],
                    )
                if error:
                    rv.Alert(
                        type="error",
                        dense=True,
                        text=True,
                        class_="mt-4 mb-0",
                        children=[error],
                    )
                if not blocked:
                    _TypeField(name or "", typed, set_typed, _confirm_if_typed)
                if busy:
                    rv.ProgressLinear(indeterminate=True, class_="mt-4")
            with rv.CardActions(style_=_ACTIONS):
                solara.Button(
                    msg("project.cancel"),
                    text=True,
                    small=True,
                    disabled=busy,
                    on_click=on_cancel,
                )
                solara.Button(
                    msg("project.delete"),
                    color="error",
                    small=True,
                    disabled=not can_delete,
                    loading=busy,
                    on_click=_confirm_if_typed,
                )


@solara.component
def _NameFields(
    title,
    validate,
    on_submit,
    on_cancel,
    action_label,
    action_icon,
    initial,
    hint,
    match,
    on_open_existing,
    busy,
    error,
):
    """The name form's card. Mounted only while the form is open, so every opening starts from ``initial``."""
    name, set_name = solara.use_state(initial)
    submit_error, set_submit_error = solara.use_state(None)
    typed = name.strip()
    live = validate(name)
    unchanged = bool(initial) and typed == initial
    found = match(typed) if typed else None

    def _type(value):
        set_name(value or "")
        set_submit_error(None)

    def _submit():
        if unchanged or busy:
            return
        problem = validate(name)
        if problem:
            set_submit_error(msg(_NAME_ERRORS[problem]))
            return
        on_submit(typed)

    with rv.Card():
        rv.CardTitle(children=[title])
        with rv.CardText():
            field = rv.TextField(
                label=msg("project.name_label"),
                v_model=name,
                on_v_model=_type,
                dense=True,
                outlined=True,
                autofocus=True,
                hint=hint or msg("project.name_hint"),
                persistent_hint=True,
                # Live, but not before anything is typed: an empty form is not wrong yet.
                error_messages=[msg(_NAME_ERRORS[live])] if name and live else [],
            )
            ipyvue.use_event(field, "keyup.enter", lambda *_: _submit())
            if found:
                with rv.Html(tag="div"):
                    solara.Button(
                        msg("project.open_instead", name=found),
                        icon_name="mdi-folder-open-outline",
                        color="primary",
                        text=True,
                        small=True,
                        on_click=lambda: on_open_existing(found),
                    )
            shown_error = error or submit_error
            if shown_error:
                rv.Alert(
                    type="error",
                    dense=True,
                    text=True,
                    class_="mt-4 mb-0",
                    children=[shown_error],
                )
        with rv.CardActions(style_=_ACTIONS):
            solara.Button(
                msg("project.cancel"), text=True, small=True, on_click=on_cancel
            )
            solara.Button(
                action_label or msg("project.create"),
                icon_name=action_icon,
                color="primary",
                small=True,
                disabled=live is not None or unchanged or busy,
                loading=busy,
                on_click=_submit,
            )


@solara.component
def NameForm(
    open: bool,
    title: str,
    validate: Callable[[str], Optional[str]],
    on_submit: Callable[[str], None],
    on_cancel,
    action_label: Optional[str] = None,
    action_icon: str = "mdi-plus",
    initial: str = "",
    hint: Optional[str] = None,
    match: Callable[[str], Optional[str]] = lambda typed: None,
    on_open_existing: Callable[[str], None] = lambda name: None,
    busy: bool = False,
    error: Optional[str] = None,
):
    """New, Duplicate and Rename's name form (420px).

    ``validate(typed)`` returns "empty", "chars", "exists" or None, on every keystroke and again
    on submit. ``match(typed)`` names a listed project to offer "open X instead".
    """
    with rv.Dialog(
        v_model=open,
        on_v_model=lambda v: None if v else on_cancel(),
        max_width="420px",
        persistent=busy,
    ):
        if open:
            _NameFields(
                title,
                validate,
                on_submit,
                on_cancel,
                action_label,
                action_icon,
                initial,
                hint,
                match,
                on_open_existing,
                busy,
                error,
            )
