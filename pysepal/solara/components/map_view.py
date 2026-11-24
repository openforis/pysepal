"""The map with the Solara overlays that sit over it: legend, loading status, app overlays."""

import re
import weakref
from collections.abc import Mapping, Sequence
from typing import Literal, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import LayerStore, StoreEvent, derive_legend
from pysepal.mapping.sepal_map import _draw_labels
from pysepal.message import msg
from pysepal.solara.components.layer_panel.hooks import use_layer_store
from pysepal.solara.components.legend import LegendComponent
from pysepal.solara.components.map_view_tools import inspector_panel
from pysepal.solara.notifications import use_notifications

Corner = Literal["top-left", "top-right", "bottom-left", "bottom-right"]
CORNERS: tuple[str, ...] = ("top-left", "top-right", "bottom-left", "bottom-right")

_TRAITS = ["state", "theme", "insets", "height"]
_SIDES = ("left", "right", "top", "bottom")

# The legend areas: the whole map, or each half of a compare, with the layer sides each draws.
_AREAS: dict[str, tuple[str, ...]] = {
    "all": ("left", "right", "both"),
    "left": ("left", "both"),
    "right": ("right", "both"),
}
# The left half continues the whole map's pick and collapse, and the whole map the left half's.
_KEEPER = {"all": "left", "left": "left", "right": "right"}

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
/* One legend card per area, centred on it: the whole map, or each half of a compare, whose
   divider the widget publishes as --psm-divider-x. Each slot is its area less 10 px a side; the
   card is no wider than the slot, and its body scrolls in a slot capped at 40 % of the map.
   Every slot clears the taller bottom corner, so the two halves' cards share one baseline. */
.pysepal-map-legend {
  position: absolute;
  z-index: 3;
  bottom: calc(
    var(--pysepal-inset-bottom)
      + max(var(--psm-controls-bottom-left, 0px), var(--psm-controls-bottom-right, 0px)) + 10px
  );
  transform: translateX(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  max-height: 40%;
  pointer-events: none;
  container: pysepal-legend / inline-size;
}
.pysepal-map-legend > * { pointer-events: auto; }
.pysepal-map-root:not([data-psm-controls]) > .pysepal-map-legend { visibility: hidden; }
.pysepal-map-legend[data-area="all"] {
  left: calc(
    var(--pysepal-inset-left) + (100% - var(--pysepal-inset-left) - var(--pysepal-inset-right)) / 2
  );
  width: calc(100% - var(--pysepal-inset-left) - var(--pysepal-inset-right) - 20px);
}
.pysepal-map-legend[data-area="left"] {
  left: calc((var(--pysepal-inset-left) + var(--psm-divider-x, 50%)) / 2);
  width: calc(var(--psm-divider-x, 50%) - var(--pysepal-inset-left) - 20px);
}
.pysepal-map-legend[data-area="right"] {
  left: calc((var(--psm-divider-x, 50%) + 100% - var(--pysepal-inset-right)) / 2);
  width: calc(100% - var(--pysepal-inset-right) - var(--psm-divider-x, 50%) - 20px);
}
/* An area under 140 px shows the card's bar only, with the layer's name, and the bar cannot
   open there; one under 60 px,
   e.g. a half the divider has pushed to the edge, shows nothing. The root in each selector
   outranks Legend.vue's scoped rules, which ipyvue suffixes with an attribute. */
@container pysepal-legend (width < 120px) {
  .pysepal-map-root > .pysepal-map-legend .sepal-legend__body { display: none; }
  .pysepal-map-root > .pysepal-map-legend .sepal-legend__chevron { display: none; }
  .pysepal-map-root > .pysepal-map-legend .sepal-legend__bar-title { display: inline; }
  .pysepal-map-root > .pysepal-map-legend .sepal-legend { pointer-events: none; }
}
@container pysepal-legend (width < 40px) {
  .pysepal-map-root > .pysepal-map-legend .sepal-legend { display: none; }
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


# A tile error ends with the tile's URL, which only clutters a toast.
_TRAILING_URL = re.compile(r":\s*(?:https?://|/)\S*$")

# Per store, so two views of one store toast an error once: the render hash each id was
# toasted for.
_toasted: "weakref.WeakKeyDictionary[LayerStore, dict[str, str]]" = weakref.WeakKeyDictionary()


def _use_layer_error_toasts(store: LayerStore) -> None:
    """Toast a layer's error once per instance of the layer.

    A failing layer reports again with each tile, so a repeat waits for a new style or for
    the layer to be added again.
    """
    notifications = use_notifications(required=False)

    def follow():
        toasted = _toasted.setdefault(store, {})

        def on_event(event: StoreEvent) -> None:
            layer_id = event.layer_id
            if layer_id not in store:
                toasted.pop(layer_id, None)
                return
            view = store.view(layer_id)
            if view.status != "error":
                return
            spec = store.get(layer_id)
            if toasted.get(layer_id) == spec.render_hash:
                return
            toasted[layer_id] = spec.render_hash
            error = _TRAILING_URL.sub("", view.error)
            notifications.error(msg("map_view.layer_error", name=spec.name, error=error))

        return store.subscribe(on_event)

    solara.use_effect(follow, [store, notifications])


def _legends(map_) -> dict[str, list[dict]]:
    """Each area's legends: ``{id, name, legend}`` per visible data layer it draws, top first.

    A layer without a legend, e.g. a multiband raster, or with an empty one, is left out.
    """
    lists: dict[str, list[dict]] = {area: [] for area in _AREAS}
    store, engine = map_.layer_store, map_.layer_engine
    if engine is None:
        return lists
    primary = THEMES[map_.theme == "dark"]["primary"]
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
        # An empty Legend() is the app's "none": it must not fall through to the others.
        legend = spec.legend if spec.legend is not None else render.legend
        if legend is None:
            legend = derive_legend(spec.style, title=spec.name, default_color=primary)
        if legend is None or not (legend.gradients or legend.items):
            continue
        entry = {"id": layer_id, "name": spec.name, "legend": legend.model_dump()}
        for area, sides in _AREAS.items():
            if drawn.get("side", "both") in sides:
                lists[area].append(entry)
    return lists


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

    Under a ``NotificationProvider``, a layer that fails to load is reported once as an error
    toast; its row in the layer panel keeps the full message.

    Args:
        map_: The ``SepalMap``.
        overlays: Elements or widgets to stack in each corner, after the built-in ones.
        legend: Show a legend card centred at the bottom of each area: the whole map, or each
            half of a compare. A card lists the visible layers its area draws that have a
            legend, and shows one: the user's pick, or a layer added after the view mounted,
            while it is listed, else the top one.
        status: Show a loading status while layers are pending, top-right.
    """
    store = map_.layer_store
    use_layer_store(store)
    _use_layer_error_toasts(store)
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
    stacks["top-left"].append(_slot("map-inspector", inspector_panel(map_)).key("inspector"))
    for corner in CORNERS:
        stacks[corner].extend(overlays.get(corner, ()))

    # The published state changes only with a publish; the theme recolours derived legends.
    lists = solara.use_memo(
        lambda: _legends(map_) if legend else None,
        [map_, legend, map_.state.get("revision"), map_.theme],
    )
    # The user's picks and the new layers'; the top and the fallback are derived each render.
    selected, set_selected = solara.use_state({})
    collapsed, set_collapsed = solara.use_state({})
    # The layers the store holds at mount are not new: the card starts on the top one,
    # whichever the engine draws last.
    seen = solara.use_ref({"left": frozenset(store.ids), "right": frozenset(store.ids)})
    compare = bool(map_.state.get("compare"))
    areas = (("left", "right") if compare else ("all",)) if lists else ()
    fresh, slots = {}, []
    # The memo predates a removal the engine has not drawn yet.
    drawn = {
        area: [e for e in entries if e["id"] in store] for area, entries in (lists or {}).items()
    }
    listed = {area: {e["id"] for e in entries} for area, entries in drawn.items()}
    # What each keeper has seen once this render shows, committed by the effect: reacton can
    # render twice before the effects, and both renders must find the same layers new. A
    # removed layer is forgotten; a hidden one stays seen. The whole map's card lists both
    # halves' layers, so none is new to the left half, nor, while it shows, to the right one.
    in_store = set(store.ids)
    next_seen = {
        "left": frozenset((seen.current["left"] & in_store) | listed.get("all", set())),
        "right": frozenset(
            (seen.current["right"] & in_store) | listed.get("right" if compare else "all", set())
        ),
    }
    for area in areas:
        keeper = _KEEPER[area]
        entries = drawn[area]
        ids = [entry["id"] for entry in entries]
        new = [layer_id for layer_id in ids if layer_id not in seen.current[keeper]]
        if new:
            fresh[keeper] = new[0]
        current = selected.get(keeper)
        pick = new[0] if new else current if current in ids else next(iter(ids), None)
        children = []
        if pick is not None:
            shown = entries[ids.index(pick)]
            children.append(
                LegendComponent(
                    legend_data=shown["legend"],
                    placement="map",
                    title=shown["name"],
                    selector_options=[{"value": e["id"], "text": e["name"]} for e in entries],
                    selected=pick,
                    event_set_selected=_setter(set_selected, keeper),
                    collapsed=collapsed.get(keeper, False),
                    event_set_collapsed=_setter(set_collapsed, keeper),
                ).key(area)
            )
        slots.append(
            rv.Html(
                tag="div",
                class_="pysepal-map-legend",
                attributes={"data-area": area},
                children=children,
            ).key(f"legend-{area}")
        )

    # A new layer stays the area's pick once it is no longer new, as if the user picked it.
    def keep_fresh():
        seen.current = next_seen
        if fresh:
            set_selected(lambda previous: {**previous, **fresh})

    solara.use_effect(keep_fresh, [tuple(fresh.items()), next_seen["left"], next_seen["right"]])

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
            *slots,
        ],
    )
    return rv.Html(
        tag="div", class_="pysepal-map-view", style_=style, children=[solara.Style(CSS), root]
    )


def _setter(set_state, keeper: str):
    """A callback that stores one area's value in a per-area state."""
    return lambda value: set_state(lambda previous: {**previous, keeper: value})


def _slot(role: str, children: list, class_: str = ""):
    """A built-in slot of a corner stack, hidden while it has nothing to show."""
    attributes = {"data-role": role}
    if not children:
        attributes["data-idle"] = ""
    return rv.Html(tag="div", class_=class_, attributes=attributes, children=children)
