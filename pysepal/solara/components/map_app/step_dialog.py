"""The dialog that shows the ``display="dialog"`` steps of the MapApp shell."""

from typing import Callable, Mapping, Optional, Sequence, Union

import reacton.ipyvue as ipyvue
import reacton.ipyvuetify as rv
import solara

from ._ui import IconButton, as_children


def clamp(target: Union[int, str, None], viewport: int, cap: int, default: Optional[int]):
    """Return a dialog size in px, or None for none.

    Args:
        target: The size asked for, in px or as ``"NN%"`` of ``viewport``.
        viewport: The window size along that axis; 0 until it is measured,
            which caps nothing.
        cap: The largest size that fits.
        default: The size when ``target`` is empty.
    """
    if isinstance(target, str) and target.endswith("%"):
        value = viewport * int(target[:-1]) / 100 if viewport > 0 else default
    else:
        value = target or default
    if value is None:
        return None
    if viewport > 0:
        value = min(cap, value)
    return int(value)


@solara.component
def ActionButton(action: Mapping, on_click: Callable[[Mapping], None]):
    """Render one footer button of a dialog step: outlined to cancel, filled otherwise."""
    btn = rv.Btn(
        color="primary",
        outlined=bool(action.get("cancel")),
        small=True,
        children=[action.get("label", "")],
    )
    ipyvue.use_event(btn, "click", lambda *_: on_click(action))
    return btn


@solara.component
def StepDialog(
    open: bool,
    step: Optional[Mapping],
    dialog_steps: Sequence[Mapping],
    width: Optional[int],
    height: Optional[int],
    fullscreen: bool,
    on_close: Callable[[], None],
    on_action: Callable[[Mapping], None],
):
    """Render the step dialog.

    Every dialog step's content stays mounted and only the active one shows, so
    a form keeps what the user typed when the dialog closes and reopens.
    """
    actions = list(step.get("actions") or []) if step else []
    active_id = step.get("id") if step else None

    def on_v_model(value):
        if not value:
            on_close()

    with rv.Dialog(
        v_model=open,
        on_v_model=on_v_model,
        width=width,
        fullscreen=fullscreen,
        content_class="dialog-container sepal-mapapp__dialog",
    ) as main:
        card_style = f"height: {height}px" if height else ""
        with rv.Card(class_="dialog-card", style_=card_style):
            with rv.CardTitle(class_="headline d-flex justify-space-between"):
                rv.Html(tag="span", children=[step.get("name", "") if step else ""])
                IconButton(icon="mdi-close", on_click=on_close)
            rv.Divider()
            with rv.CardText(class_="dialog-content pt-4"):
                for item in dialog_steps:
                    hidden = "" if item.get("id") == active_id else "display: none"
                    rv.Html(
                        tag="div",
                        class_="jupyter-widget-container",
                        style_=hidden,
                        children=as_children(item.get("content")),
                    ).key(f"dialog-step-{item.get('id')}")
            if actions:
                rv.Divider()
                with rv.CardActions():
                    rv.Spacer()
                    for i, action in enumerate(actions):
                        ActionButton(action, on_click=on_action).key(f"action-{i}")
    return main
