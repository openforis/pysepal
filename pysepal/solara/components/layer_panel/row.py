"""One layer of the layer panel."""

from typing import Callable, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.message import msg

from .settings import LayerSettings


def _icon_button(icon: str, role: str, layer_id: str, on_click, title: str = "", **kwargs):
    attributes = {"data-role": role, "data-layer-id": layer_id}
    if title:
        attributes["title"] = title
    return solara.Button(
        icon=True,
        text=True,
        on_click=on_click,
        attributes=attributes,
        children=[rv.Icon(size="small", children=[icon])],
        **kwargs,
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
        return solara.Row(classes=["pysepal-layer-row"], children=[])
    spec, view = store.get(layer_id), store.view(layer_id)

    status = view.status
    if status == "pending":
        status_icon = rv.ProgressCircular(indeterminate=True, size=16, width=2)
        tip = msg("layer_panel.preparing")
    elif status == "error":
        status_icon = rv.Icon(color="error", size="small", children=["mdi-alert"])
        tip = view.error or msg("layer_panel.error")
    else:
        status_icon = rv.Icon(
            size="small", style_="visibility: hidden", children=["mdi-circle-small"]
        )
        tip = ""

    children = [
        _icon_button(
            "mdi-eye" if view.visible else "mdi-eye-off",
            "visibility",
            layer_id,
            lambda: store.set_visible(layer_id, not view.visible),
        ),
        solara.Text(
            spec.name,
            style={
                "flex": "1 1 auto",
                "min-width": "0",
                "overflow": "hidden",
                "text-overflow": "ellipsis",
                "white-space": "nowrap",
            },
        ),
        # Always rendered, so the element tree keeps its shape across statuses.
        solara.Tooltip(tip, children=[rv.Html(tag="span", children=[status_icon])]),
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
        children.append(
            solara.Tooltip(
                zoom_tip,
                children=[
                    rv.Html(
                        tag="span",
                        children=[
                            _icon_button(
                                "mdi-crosshairs-gps",
                                "zoom",
                                layer_id,
                                lambda: zoom_task(),
                                disabled=status == "pending" or no_bounds,
                            )
                        ],
                    )
                ],
            )
        )

    if compare:
        side = view.side
        children.append(
            solara.Button(
                icon=True,
                text=True,
                on_click=lambda: store.set_side(layer_id, _NEXT_SIDE[side]),
                attributes={
                    "data-role": "side",
                    "data-layer-id": layer_id,
                    "data-side": side,
                    "title": msg(f"layer_panel.side.{side}"),
                },
                children=[rv.Icon(size="small", children=[_SIDE_ICONS[side]])],
            )
        )

    gear = rv.Html(
        tag="span",
        v_bind="menu.props",
        children=[
            _icon_button(
                "mdi-cog-outline",
                "settings",
                layer_id,
                lambda: None,
                title=msg("layer_panel.settings"),
            )
        ],
    )
    children.append(
        rv.Menu(
            v_model=open_,
            on_v_model=set_open,
            close_on_content_click=False,
            location="bottom end",
            attributes={"data-role": "settings-menu", "data-layer-id": layer_id},
            v_slots=[{"name": "activator", "variable": "menu", "children": [gear]}],
            # Built only while open: the form reads the layer's file on mount.
            children=[LayerSettings(store, layer_id, on_export, is_dark, version)] if open_ else [],
        )
    )
    children.append(
        _icon_button(
            "mdi-close",
            "remove",
            layer_id,
            lambda: store.remove(layer_id),
            title=msg("layer_panel.remove"),
        )
    )
    return solara.Row(
        classes=["pysepal-layer-row", "pysepal-layer-row__header"],
        style={"align-items": "center", "gap": "4px", "flex-wrap": "nowrap"},
        children=children,
    )
