"""Reusable async task button for Solara components.

Provides a single toggle button that switches between action and cancel states
during async task execution. Replaces the two-button pattern (action + separate
cancel) used in earlier pysepal components.

Usage:
    from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

    task = solara.lab.use_task(my_fn, dependencies=None, raise_error=False, prefer_threaded=False)
    btn_props = use_task_button(task, on_start=lambda: task(snapshot))
    TaskButtonComponent(label="Run", **btn_props, small=True, block=True)
"""

from typing import Any, Callable, Optional

import ipyvuetify as v
import solara
from reacton import ipyvue
from reacton import ipyvuetify as rv


def use_task_button(
    task: Any,
    *,
    on_start: Callable[[], None],
    cancel_reason_ref: Optional[Any] = None,
) -> dict:
    """Bridge a solara.lab.use_task result to TaskButtonComponent props.

    Args:
        task: The task object returned by solara.lab.use_task.
        on_start: Callback invoked when the user clicks the button in idle state.
        cancel_reason_ref: Optional solara.use_ref for tracking cancel reason.
            When provided, set to "user" on cancel.

    Returns:
        Dict with running, on_start, on_cancel keys. Spread into TaskButtonComponent.
    """

    def handle_cancel():
        if cancel_reason_ref is not None:
            cancel_reason_ref.current = "user"
        if task.pending:
            try:
                task.cancel()
            except RuntimeError:
                pass

    return {
        "running": task.pending,
        "on_start": on_start,
        "on_cancel": handle_cancel,
    }


@solara.component
def TaskButtonComponent(
    label: str,
    on_start: Callable[[], None],
    on_cancel: Callable[[], None],
    running: bool = False,
    cancel_label: str = "Cancel",
    color: str = "primary",
    cancel_color: str = "error",
    icon: str = "",
    cancel_icon: str = "mdi-close",
    external_busy: bool = False,
    show_loading: bool = True,
    small: bool = False,
    block: bool = False,
    min_width: Optional[str] = None,
):
    """Single toggle button for async task execution.

    Switches between action state (label/color) and cancel state
    (cancel_label/cancel_color + spinner) based on running flag.

    Cancel is never disabled. When running=True, the button is always clickable.
    external_busy only gates the start action.

    Args:
        label: Button text when idle.
        on_start: Called when user clicks to start.
        on_cancel: Called when user clicks to cancel.
        running: Whether the task is currently running.
        cancel_label: Button text when running.
        color: Button color when idle.
        cancel_color: Button color when running.
        icon: Icon name when idle.
        cancel_icon: Icon name when running.
        external_busy: Disables start when True (e.g., child component loading).
            Never disables cancel.
        show_loading: Show spinner when running.
        small: Small button variant.
        block: Full-width button.
        min_width: Explicit CSS min-width (e.g., "150px").
    """
    is_cancel_state = running

    btn_label = cancel_label if is_cancel_state else label
    btn_color = cancel_color if is_cancel_state else color
    btn_icon = cancel_icon if is_cancel_state else icon

    # Cancel is never disabled; external_busy only blocks starting
    disabled = (not is_cancel_state) and external_busy

    def handle_click(*_ignore):
        if is_cancel_state:
            on_cancel()
        else:
            on_start()

    style_ = ""
    if min_width:
        style_ = f"min-width: {min_width};"

    # Build children: spinner (when loading) or icon, plus label text
    children = []
    if is_cancel_state and show_loading:
        spinner_size = 14 if small else 16
        children.append(
            v.ProgressCircular(
                size=spinner_size,
                width=2,
                color="white",
                indeterminate=True,
                class_="mr-2",
            )
        )
    elif btn_icon:
        # The button sizes its icon itself.
        children.append(v.Icon(start=True, children=[btn_icon]))

    children.append(btn_label)

    # Use rv.Btn directly — never Vuetify's native loading prop which
    # disables the button and hides children. Card actions default their buttons
    # to text style, so the filled look is asked for explicitly.
    btn = rv.Btn(
        children=children,
        color=btn_color,
        disabled=disabled,
        block=block,
        **({"size": "small"} if small else {}),
        variant="elevated",
        style_=style_,
    )
    ipyvue.use_event(btn, "click", handle_click)
