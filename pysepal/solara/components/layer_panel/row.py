"""One layer of the layer panel."""

from typing import Callable, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.message import msg

from .settings import LayerSettings

ICON_SIZE = 18
# A small icon button at comfortable density is 28px square: the width of every action slot.
SLOT_WIDTH = "28px"


def _icon_button(
    icon: str,
    role: str,
    layer_id: str,
    on_click,
    label: str,
    title: bool = True,
    attributes: Optional[dict] = None,
    **kwargs,
):
    """An icon-only button named ``label``; ``title=False`` when a tooltip already shows it."""
    attributes = {
        "data-role": role,
        "data-layer-id": layer_id,
        "aria-label": label,
        **(attributes or {}),
    }
    if title:
        attributes["title"] = label
    return solara.Button(
        icon=True,
        text=True,
        size="small",
        density="comfortable",
        on_click=on_click,
        attributes=attributes,
        children=[rv.Icon(size=ICON_SIZE, children=[icon])],
        **kwargs,
    )


def _slot(name: str, *children):
    """A cell of the row grid; without children it is the placeholder that keeps the column."""
    align = "flex-start" if name == "name" else "center"
    return rv.Html(
        tag="div",
        class_=f"pysepal-layer-row__slot pysepal-layer-row__slot--{name}",
        attributes={"data-slot": name},
        style_=f"display: flex; align-items: center; justify-content: {align}; gap: 4px; min-width: 0",
        children=list(children),
    )


# The side a click moves to, and the icon of each side.
_NEXT_SIDE = {"left": "both", "both": "right", "right": "left"}
_SIDE_ICONS = {
    "left": "mdi-format-horizontal-align-left",
    "both": "mdi-arrow-expand-horizontal",
    "right": "mdi-format-horizontal-align-right",
}


def _published_instance(map_, layer_id: str) -> Optional[int]:
    """The instance the map's widget published for a layer, None when it has none yet."""
    for entry in map_.state.get("layers", ()):
        if entry["id"] == layer_id:
            return entry.get("instance")
    return None


@solara.component
def LayerRow(
    store: LayerStore,
    layer_id: str,
    map_=None,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
    is_dark: bool = False,
    version: int = 0,
    compare: bool = False,
):
    """A layer on one line: visibility, name, status, zoom, settings and remove.

    The row is a grid of slots: one fixed-width column per action and the name in the
    rest, so the icons of every row line up.

    Args:
        store: The layer store.
        layer_id: Id of the layer shown.
        map_: The ``SepalMap`` the zoom button moves; no zoom button when None.
        on_export: Called with the spec when Export is clicked; no button without it.
        is_dark: Whether the theme is dark.
        version: The panel's store version. A row whose arguments did not change is not
            re-rendered with the panel, so this makes it follow every store event.
        compare: Whether the map is in compare mode; shows the button that sets the layer's side.
    """
    open_, set_open = solara.use_state(False)
    # What the last zoom said: ("no_bounds", instance) or ("failed", None).
    note, set_note = solara.use_state(None)

    async def zoom():
        try:
            result = await map_.zoom_layer_async(layer_id)
            if result == "no_bounds":
                set_note(("no_bounds", _published_instance(map_, layer_id)))
            elif result == "failed":
                set_note(("failed", None))
            elif result == "moved":
                set_note(None)
        except Exception:
            set_note(("failed", None))

    # dependencies=None: the task runs on a click only, not on mount.
    zoom_task = solara.lab.use_task(zoom, dependencies=None, prefer_threaded=False)

    # The panel drops a removed layer's row, but a render can still reach it first.
    if layer_id not in store:
        return solara.Div(classes=["pysepal-layer-row"], children=[])
    spec, view = store.get(layer_id), store.view(layer_id)

    status = view.status
    if status == "pending":
        status_icon = rv.ProgressCircular(indeterminate=True, size=16, width=2)
        tip = msg("layer_panel.preparing")
    elif status == "error":
        status_icon = rv.Icon(color="error", size=ICON_SIZE, children=["mdi-alert"])
        tip = view.error or msg("layer_panel.error")
    else:
        status_icon = rv.Icon(size=ICON_SIZE, children=["mdi-circle-small"])
        tip = ""

    slots = [
        _slot(
            "visibility",
            _icon_button(
                "mdi-eye" if view.visible else "mdi-eye-off",
                "visibility",
                layer_id,
                lambda: store.set_visible(layer_id, not view.visible),
                msg("layer_panel.hide") if view.visible else msg("layer_panel.show"),
            ),
        ),
        _slot(
            "name",
            rv.Html(
                tag="span",
                class_="pysepal-layer-row__name text-body-2",
                attributes={"title": spec.name},
                style_=(
                    "flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis;"
                    f" white-space: nowrap; opacity: {1 if view.visible else 0.6}"
                ),
                children=[spec.name],
            ),
            # Always rendered, so the element tree keeps its shape across statuses.
            solara.Tooltip(
                tip,
                children=[
                    rv.Html(
                        tag="span",
                        style_=f"display: {'flex' if tip else 'none'}",
                        children=[status_icon],
                    )
                ],
            ),
        ),
    ]

    if map_ is not None:
        no_bounds = (
            note is not None
            and note[0] == "no_bounds"
            and note[1] == _published_instance(map_, layer_id)
        )
        if no_bounds:
            zoom_tip = msg("layer_panel.no_bounds")
        elif note is not None and note[0] == "failed":
            zoom_tip = msg("layer_panel.zoom_failed")
        else:
            zoom_tip = msg("layer_panel.zoom")
        zoom_button = _icon_button(
            "mdi-crosshairs-gps",
            "zoom",
            layer_id,
            lambda: zoom_task(),
            zoom_tip,
            title=False,
            disabled=status == "pending" or no_bounds,
        )
        # A disabled button gets no pointer events, so the tooltip hangs on a span around it.
        slots.append(
            _slot(
                "zoom",
                solara.Tooltip(zoom_tip, children=[rv.Html(tag="span", children=[zoom_button])]),
            )
        )

    if compare:
        side = view.side
        slots.append(
            _slot(
                "side",
                _icon_button(
                    _SIDE_ICONS[side],
                    "side",
                    layer_id,
                    lambda: store.set_side(layer_id, _NEXT_SIDE[side]),
                    msg(f"layer_panel.side.{side}"),
                    attributes={"data-side": side},
                ),
            )
        )

    gear = rv.Html(
        tag="span",
        v_bind="menu.props",
        children=[
            _icon_button(
                "mdi-tune", "settings", layer_id, lambda: None, msg("layer_panel.settings")
            )
        ],
    )
    slots.append(
        _slot(
            "settings",
            rv.Menu(
                v_model=open_,
                on_v_model=set_open,
                close_on_content_click=False,
                location="bottom end",
                attributes={"data-role": "settings-menu", "data-layer-id": layer_id},
                v_slots=[{"name": "activator", "variable": "menu", "children": [gear]}],
                # Built only while open: the form reads the layer's file on mount.
                children=(
                    [LayerSettings(store, layer_id, on_export, is_dark, version)] if open_ else []
                ),
            ),
        )
    )
    slots.append(
        _slot(
            "remove",
            _icon_button(
                "mdi-trash-can-outline",
                "remove",
                layer_id,
                lambda: store.remove(layer_id),
                msg("layer_panel.remove"),
            ),
        )
    )

    actions = len(slots) - 2
    return solara.Div(
        classes=["pysepal-layer-row", "pysepal-layer-row__header"],
        style={
            "display": "grid",
            "grid-template-columns": (
                f"{SLOT_WIDTH} minmax(0, 1fr) repeat({actions}, {SLOT_WIDTH})"
            ),
            "align-items": "center",
            "column-gap": "2px",
        },
        children=slots,
    )
