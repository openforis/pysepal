"""The inspector toggle and card that ``MapView`` shows over the map."""

import math

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg


def _tool_button(icon: str, tip: str, role: str, on_click, active: bool = False):
    button = solara.Button(
        icon=True,
        on_click=on_click,
        color="primary" if active else None,
        text=not active,
        attributes={"data-role": role, "data-active": "true" if active else "false"},
        children=[rv.Icon(size="small", children=[icon])],
    )
    return solara.Tooltip(tip, children=[rv.Html(tag="span", children=[button])])


def _layer_section(layer) -> object:
    if layer.status == "ready":
        rows = [rv.Html(tag="div", children=[f"{label}: {value}"]) for label, value in layer.values]
    elif layer.status == "error":
        rows = [rv.Html(tag="div", children=[layer.error or msg("map_view.inspector.error")])]
    else:
        rows = [rv.Html(tag="div", children=[msg(f"map_view.inspector.{layer.status}")])]
    return rv.Html(
        tag="div",
        style_="margin-top: 6px",
        attributes={"data-role": "inspector-layer", "data-layer-id": layer.layer_id},
        children=[rv.Html(tag="div", style_="font-weight: 500", children=[layer.name]), *rows],
    )


def inspector_panel(map_) -> list:
    """The inspector toggle and, while an inspection is set, its card; empty without an inspector."""
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
        elements.append(_card(result))
    return elements


def _metres(scale: float) -> str:
    """``scale`` with two significant digits below 100 (``0.29``, ``1.2``, ``38``), else whole, grouped."""
    if scale >= 100 or scale <= 0:
        return f"{max(scale, 0):,.0f}"
    return f"{scale:.{max(0, 1 - math.floor(math.log10(scale)))}f}"


def _card(result):
    header = f"{result.lat:.5f}, {result.lng:.5f}"
    head = rv.Html(
        tag="div",
        style_="padding: 6px 10px; flex: none; font-weight: 500",
        children=[
            header,
            rv.Html(
                tag="div",
                style_="font-weight: 400; font-size: 12px",
                children=[f"{msg('map_view.inspector.scale')}: {_metres(result.scale)} m"],
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
        " flex: 1 1 auto; min-height: 0"
    )
    return rv.Html(
        tag="div",
        style_=style,
        attributes={"data-role": "inspector-card"},
        children=[head, body],
    )
