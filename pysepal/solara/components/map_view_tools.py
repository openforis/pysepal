"""The draw toolbar and the inspector toggle and card that ``MapView`` shows over the map."""

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg

_MODE_ICONS = {
    "polygon": "mdi-vector-polygon",
    "rectangle": "mdi-vector-rectangle",
    "circle": "mdi-circle-outline",
    "linestring": "mdi-vector-polyline",
    "point": "mdi-map-marker-outline",
    "select": "mdi-cursor-default-click-outline",
}
# A button is 36 px tall and the stack gap 8 px.
BUTTON = 36
GAP = 8


def _tool_button(icon: str, tip: str, role: str, on_click, active: bool = False, **attrs):
    button = solara.Button(
        icon=True,
        on_click=on_click,
        color="primary" if active else None,
        text=not active,
        attributes={"data-role": role, "data-active": "true" if active else "false", **attrs},
        children=[rv.Icon(size="small", children=[icon])],
    )
    return solara.Tooltip(tip, children=[rv.Html(tag="span", children=[button])])


def draw_toolbar(map_) -> list:
    """One toggle per drawing mode and a clear button; empty while drawing is off."""
    draw = map_.draw
    if not draw.modes:
        return []

    def toggle(mode: str):
        return lambda: draw.stop() if draw.mode == mode else draw.start(mode)

    buttons = [
        _tool_button(
            _MODE_ICONS[mode],
            msg(f"map_view.draw.{mode}"),
            "draw-mode",
            toggle(mode),
            active=draw.mode == mode,
            **{"data-mode": mode},
        )
        for mode in draw.modes
    ]
    buttons.append(
        _tool_button("mdi-delete-outline", msg("map_view.draw.clear"), "draw-clear", draw.clear)
    )
    return [
        rv.Html(
            tag="div",
            class_="pysepal-map-toolbar",
            style_="display: flex; background: rgba(var(--v-theme-surface, 255, 255, 255), 0.9);"
            " border-radius: 4px",
            children=buttons,
        )
    ]


def toolbar_height(map_) -> int:
    """The height the draw toolbar takes in the stack, 0 while it is hidden."""
    return BUTTON + GAP if map_.draw.modes else 0


def _layer_section(layer) -> object:
    if layer.status == "ready":
        rows = [rv.Html(tag="div", children=[f"{label}: {value}"]) for label, value in layer.values]
    elif layer.status == "error":
        rows = [rv.Html(tag="div", children=[layer.error])]
    else:
        rows = [rv.Html(tag="div", children=[msg(f"map_view.inspector.{layer.status}")])]
    return rv.Html(
        tag="div",
        style_="margin-top: 6px",
        attributes={"data-role": "inspector-layer", "data-layer-id": layer.layer_id},
        children=[rv.Html(tag="div", style_="font-weight: 500", children=[layer.name]), *rows],
    )


def inspector_panel(map_, reserved: int) -> list:
    """The inspector toggle and, while an inspection is set, its card; empty without an inspector.

    ``reserved`` is the height in px the stack leaves to other things, which the card's
    height cap subtracts from the map's.
    """
    inspector = map_.inspector
    if inspector is None:
        return []
    active = bool(inspector.active)
    elements = [
        _tool_button(
            "mdi-crosshairs-gps",
            msg("map_view.inspector.toggle"),
            "inspector-toggle",
            inspector.deactivate if active else inspector.activate,
            active=active,
        )
    ]
    result = inspector.inspection
    if result is not None:
        elements.append(_card(result, reserved + BUTTON + GAP))
    return elements


def _card(result, reserved: int):
    header = f"{result.lat:.5f}, {result.lng:.5f}"
    head = rv.Html(
        tag="div",
        style_="padding: 6px 10px; flex: none; font-weight: 500",
        children=[
            header,
            rv.Html(
                tag="div",
                style_="font-weight: 400; font-size: 12px",
                children=[f"{msg('map_view.inspector.scale')}: {result.scale:.0f} m"],
            ),
        ],
    )
    sections = [_layer_section(layer) for layer in result.layers]
    if result.pending:
        sections.append(
            rv.ProgressCircular(
                indeterminate=True,
                size=16,
                width=2,
                attributes={"data-role": "inspector-pending"},
            )
        )
    body = rv.Html(
        tag="div",
        style_="overflow-y: auto; flex: 1 1 auto; min-height: 0; padding: 0 10px 8px",
        attributes={"data-role": "inspector-body"},
        children=sections,
    )
    style = (
        "display: flex; flex-direction: column; min-width: 180px; font-size: 13px;"
        " border-radius: 4px; overflow: hidden;"
        " background: rgba(var(--v-theme-surface, 255, 255, 255), 0.95);"
        f" max-height: calc(var(--pysepal-map-height) - var(--pysepal-inset-top)"
        f" - var(--pysepal-inset-bottom) - var(--pysepal-controls-top-left)"
        f" - var(--pysepal-controls-bottom-left) - {reserved}px)"
    )
    return rv.Html(
        tag="div",
        style_=style,
        attributes={"data-role": "inspector-card"},
        children=[head, body],
    )
