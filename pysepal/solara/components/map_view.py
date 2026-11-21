"""The map with the Solara overlays that sit over it: legend, loading status, app overlays."""

from collections.abc import Mapping, Sequence
from typing import Literal, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import derive_legend
from pysepal.message import msg
from pysepal.solara.components.layer_panel.hooks import use_layer_store
from pysepal.solara.components.legend import LegendComponent

Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]
CORNERS: tuple[str, ...] = ("top-left", "top-right", "bottom-left", "bottom-right")

_TRAITS = ["state", "theme", "insets"]
_SIDES = ("left", "right", "top", "bottom")

CSS = """
.pysepal-map-view { position: relative; width: 100%; height: 100%; overflow: hidden; }
.pysepal-map-view .psm-map { height: 100% !important; }
/* The root sets the variables inline; in fullscreen the camera uses no insets, so neither do the stacks. */
[data-psm-fullscreen-root][data-psm-fullscreen] {
  --pysepal-inset-left: 0px !important;
  --pysepal-inset-right: 0px !important;
  --pysepal-inset-top: 0px !important;
  --pysepal-inset-bottom: 0px !important;
}
.pysepal-map-corner {
  position: absolute;
  z-index: 3;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  max-width: 50%;
}
.pysepal-map-corner > * { pointer-events: auto; }
/* The offsets clear the controls: zoom and fullscreen, scale, attribution. */
.pysepal-map-corner[data-corner="top-left"] {
  top: calc(var(--pysepal-inset-top) + 76px);
  left: calc(var(--pysepal-inset-left) + 10px);
  align-items: flex-start;
}
.pysepal-map-corner[data-corner="top-right"] {
  top: calc(var(--pysepal-inset-top) + 10px);
  right: calc(var(--pysepal-inset-right) + 10px);
  align-items: flex-end;
}
.pysepal-map-corner[data-corner="bottom-left"] {
  bottom: calc(var(--pysepal-inset-bottom) + 36px);
  left: calc(var(--pysepal-inset-left) + 10px);
  align-items: flex-start;
}
.pysepal-map-corner[data-corner="bottom-right"] {
  bottom: calc(var(--pysepal-inset-bottom) + 30px);
  right: calc(var(--pysepal-inset-right) + 10px);
  align-items: flex-end;
}
.pysepal-map-status {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  background: rgba(var(--v-theme-surface, 255, 255, 255), 0.9);
}
"""


def _legends(map_) -> list[dict]:
    """The legends of what the map draws: visible layers it accepted, top first."""
    store, engine = map_.layer_store, map_.layer_engine
    if engine is None:
        return []
    primary = THEMES[map_.theme == "dark"]["primary"]
    legends = []
    for drawn in map_.state.get("layers", ()):
        layer_id = drawn.get("id")
        if not drawn.get("visible") or layer_id not in store:
            continue
        accepted = engine.accepted(layer_id)
        if accepted is None:
            continue
        spec, render = accepted
        legend = spec.legend or render.legend
        if legend is None:
            legend = derive_legend(spec.style, title=spec.name, default_color=primary)
        if legend is not None:
            legends.append(legend.model_dump())
    return legends


@solara.component
def MapView(
    map_,
    overlays: Optional[Mapping[Corner, Sequence]] = None,
    legend: bool = True,
    status: bool = True,
):
    """Place a ``SepalMap`` and the overlays over it, in the corners inside its insets.

    The root is the target of the widget's fullscreen control, so the overlays stay
    over the map in fullscreen, where the insets are zero.

    Args:
        map_: The ``SepalMap``.
        overlays: Elements or widgets to stack in each corner, after the built-in ones.
        legend: Show the legend of the visible drawn layers, bottom-right.
        status: Show a loading status while layers are pending, top-right.
    """
    store = map_.layer_store
    use_layer_store(store)
    _, set_version = solara.use_state(0)

    def follow_map():
        def on_change(_change):
            set_version(lambda v: v + 1)

        map_.observe(on_change, names=_TRAITS)
        return lambda: map_.unobserve(on_change, names=_TRAITS)

    solara.use_effect(follow_map, [map_])

    insets = map_.insets or {}
    style = "; ".join(f"--pysepal-inset-{side}: {int(insets.get(side, 0))}px" for side in _SIDES)
    overlays = overlays or {}

    stacks = {corner: [] for corner in CORNERS}
    if status:
        pending = sum(store.view(i).status == "pending" for i in store.ids)
        if pending:
            stacks["top-right"].append(
                rv.Html(
                    tag="div",
                    class_="pysepal-map-status",
                    attributes={"data-role": "map-status"},
                    children=[
                        rv.ProgressCircular(indeterminate=True, size=16, width=2),
                        f"{msg('map_view.loading')} ({pending})",
                    ],
                ).key("status")
            )
    if legend:
        legends = _legends(map_)
        if legends:
            stacks["bottom-right"].append(
                rv.Html(
                    tag="div",
                    attributes={"data-role": "map-legend"},
                    children=[LegendComponent(legend_data=data, inline=True) for data in legends],
                ).key("legend")
            )
    for corner in CORNERS:
        stacks[corner].extend(overlays.get(corner, ()))

    return rv.Html(
        tag="div",
        class_="pysepal-map-view",
        style_=style,
        attributes={"data-psm-fullscreen-root": ""},
        children=[
            solara.Style(CSS),
            map_,
            *[
                rv.Html(
                    tag="div",
                    class_="pysepal-map-corner",
                    attributes={"data-corner": corner},
                    children=stacks[corner],
                ).key(corner)
                for corner in CORNERS
            ],
        ],
    )
