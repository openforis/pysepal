"""The map with the Solara overlays that sit over it: legend, loading status, app overlays."""

from collections.abc import Mapping, Sequence
from typing import Literal, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import derive_legend
from pysepal.mapping.sepal_map import _draw_labels
from pysepal.message import msg
from pysepal.solara.components.layer_panel.hooks import use_layer_store
from pysepal.solara.components.legend import LegendComponent
from pysepal.solara.components.map_view_tools import inspector_panel

Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]
CORNERS: tuple[str, ...] = ("top-left", "top-right", "bottom-left", "bottom-right")

_TRAITS = ["state", "theme", "insets", "height", "cursor"]
_SIDES = ("left", "right", "top", "bottom")

# The view takes the map's height and the root fills it; the map fills the root through the
# wrapper ipyvue puts around a widget (``height: 100%``), in fullscreen too.
CSS = """
.pysepal-map-view { position: relative; width: 100%; overflow: hidden; }
.pysepal-map-root { position: relative; width: 100%; height: 100%; }
.pysepal-map-view .psm-map { height: 100% !important; }
/* The view sets the insets inline; in fullscreen the camera uses none, so neither do the stacks. */
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
.pysepal-map-corner > [data-idle] { display: none; }
/* The widget sets --psm-controls-* on the root, each corner's height, once it has measured. */
.pysepal-map-root:not([data-psm-controls]) > .pysepal-map-corner { visibility: hidden; }
/* Each stack sits 10 px past the map's controls in its corner. The top-left cap ends above the
   bottom-left controls, scale and coordinates, which a card must not cover. */
.pysepal-map-corner[data-corner="top-left"] {
  top: calc(var(--pysepal-inset-top) + var(--psm-controls-top-left, 0px) + 10px);
  left: calc(var(--pysepal-inset-left) + 10px);
  align-items: flex-start;
  /* The cap is the corner's: the inspector card shrinks first and scrolls its body, and an
     overlay after it that still overflows scrolls the corner instead of being cut. */
  max-height: calc(
    100% - var(--pysepal-inset-top) - var(--psm-controls-top-left, 0px) - 10px
      - var(--pysepal-inset-bottom) - var(--psm-controls-bottom-left, 0px) - 10px
  );
  overflow-y: auto;
}
.pysepal-map-corner[data-corner="top-left"] > [data-role="map-inspector"]:not([data-idle]) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}
.pysepal-map-corner[data-corner="top-right"] {
  top: calc(var(--pysepal-inset-top) + var(--psm-controls-top-right, 0px) + 10px);
  right: calc(var(--pysepal-inset-right) + 10px);
  align-items: flex-end;
}
.pysepal-map-corner[data-corner="bottom-left"] {
  bottom: calc(var(--pysepal-inset-bottom) + var(--psm-controls-bottom-left, 0px) + 10px);
  left: calc(var(--pysepal-inset-left) + 10px);
  align-items: flex-start;
}
.pysepal-map-corner[data-corner="bottom-right"] {
  bottom: calc(var(--pysepal-inset-bottom) + var(--psm-controls-bottom-right, 0px) + 10px);
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
    """The legends of the data layers the map draws: visible layers it accepted, top first."""
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
        if spec.zone == "overlay":
            continue
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

    Each corner's overlays sit 10 px past the map's controls there, whose heights the widget
    measures; they stay hidden until it has. The root that holds the map and the overlays is
    the target of the widget's fullscreen control, so the overlays stay over the map in
    fullscreen, where the insets are zero.

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

    # Only follows the inspector; a view that unmounts leaves it as it is.
    inspector = map_.inspector

    def follow_inspector():
        if inspector is None:
            return None

        def on_change(_change):
            set_version(lambda v: v + 1)

        inspector.observe(on_change, names=["active", "inspection"])
        return lambda: inspector.unobserve(on_change, names=["active", "inspection"])

    solara.use_effect(follow_inspector, [inspector])

    # Again on a language switch, which renders the view again with new messages.
    labels = _draw_labels()
    solara.use_effect(lambda: map_.draw.set_labels(labels), [map_, tuple(labels.items())])

    insets = map_.insets or {}
    variables = {f"--pysepal-inset-{side}": f"{int(insets.get(side, 0))}px" for side in _SIDES}
    variables["height"] = map_.height
    style = "; ".join(f"{name}: {value}" for name, value in variables.items())
    overlays = overlays or {}

    # The built-in slots stay mounted, empty while idle: one coming or going would
    # otherwise shift the app overlays after it, and reacton would remount them.
    stacks = {corner: [] for corner in CORNERS}
    pending = sum(store.view(i).status == "pending" for i in store.ids) if status else 0
    loading = []
    if pending:
        spinner = rv.ProgressCircular(indeterminate=True, size=16, width=2)
        loading = [spinner, f"{msg('map_view.loading')} ({pending})"]
    stacks["top-right"].append(_slot("map-status", loading, "pysepal-map-status").key("status"))
    legends = _legends(map_) if legend else []
    legend_elements = [LegendComponent(legend_data=data, inline=True) for data in legends]
    stacks["bottom-right"].append(_slot("map-legend", legend_elements).key("legend"))
    stacks["top-left"].append(_slot("map-inspector", inspector_panel(map_)).key("inspector"))
    for corner in CORNERS:
        stacks[corner].extend(overlays.get(corner, ()))

    # The widget sets the corner heights inline on the fullscreen root, so the root binds no
    # style: Vue would then rewrite it.
    root = rv.Html(
        tag="div",
        class_="pysepal-map-root",
        attributes={"data-psm-fullscreen-root": ""},
        children=[
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
    return rv.Html(
        tag="div", class_="pysepal-map-view", style_=style, children=[solara.Style(CSS), root]
    )


def _slot(role: str, children: list, class_: str = ""):
    """A built-in slot of a corner stack, hidden while it has nothing to show."""
    attributes = {"data-role": role}
    if not children:
        attributes["data-idle"] = ""
    return rv.Html(tag="div", class_=class_, attributes=attributes, children=children)
