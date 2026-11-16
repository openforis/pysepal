"""The dialog that shows the ``display="dialog"`` steps of the MapApp shell."""

from typing import Callable, Mapping, Optional, Sequence, Union

import reacton.ipyvuetify as rv
import solara

from ._ui import Slot, to_px


def clamp(targets: Sequence[Union[int, str, None]], viewport: int, cap: int) -> Optional[int]:
    """Return the first of ``targets`` that reads as a size, in px, or None if none does.

    Args:
        targets: Sizes in order of preference: px as a number, ``"600"`` or
            ``"600px"``, or ``"NN%"`` of ``viewport``.
        viewport: The window size along that axis; 0 until it is measured,
            which caps nothing.
        cap: The largest size that fits.
    """
    value = next((px for px in (to_px(t, viewport) for t in targets) if px), None)
    if value is None:
        return None
    if viewport > 0:
        value = min(cap, value)
    return int(value)


@solara.component
def StepDialog(
    open: bool,
    active_key: Optional[str],
    dialog_steps: Mapping[str, Mapping],
    width: Optional[int],
    height: Optional[int],
    fullscreen: bool,
    on_close: Callable[[], None],
    on_action: Callable[[Mapping], None],
):
    """Render the step dialog.

    Every dialog step's content stays mounted and only the active one shows, so
    a form keeps what the user typed when the dialog closes and reopens.

    Args:
        open: Whether the dialog shows.
        active_key: The key of the active step, from ``step_keys``.
        dialog_steps: The dialog steps with content, by key.
        width: The dialog width in px.
        height: The card height in px, or None to fit the content.
        fullscreen: Show the dialog full screen.
        on_close: Called when the user closes the dialog.
        on_action: Called with the footer action the user clicks.
    """
    step = dialog_steps.get(active_key) if active_key is not None else None
    actions = list(step.get("actions") or []) if step else []

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
            with rv.CardTitle(class_="text-h5 d-flex justify-space-between"):
                rv.Html(tag="span", children=[step.get("name", "") if step else ""])
                solara.Button(
                    icon=True,
                    text=True,
                    children=[rv.Icon(children=["mdi-close"], size="small")],
                    on_click=on_close,
                )
            rv.Divider()
            with rv.CardText(class_="dialog-content pt-4"):
                for key, item in dialog_steps.items():
                    Slot(
                        item.get("content"),
                        class_="jupyter-widget-container",
                        style_="" if key == active_key else "display: none",
                    ).key(f"step:{key}")
            if actions:
                rv.Divider()
                with rv.CardActions():
                    rv.Spacer()
                    for i, action in enumerate(actions):
                        solara.Button(
                            action.get("label", ""),
                            color="primary",
                            outlined=bool(action.get("cancel")),
                            size="small",
                            on_click=lambda action=action: on_action(action),
                        ).key(f"action-{i}")
    return main
