"""MapView places the map, the legend of what it draws, a loading status and app overlays."""

import asyncio
import dataclasses
import re
from pathlib import Path

import ipyvuetify as v
import pytest
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import LayerSpec, Legend, LegendItem, RenderLayer
from pysepal.mapping import SepalMap
from pysepal.mapping.inspector import Inspection
from pysepal.message import msg
from pysepal.solara.components import map_app, map_view
from pysepal.solara.components.layer_panel.hooks import use_layer_store
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.components.map_view import MapView
from pysepal.solara.theme import ThemeState
from tests.test_solara._harness import wait_until
from tests.test_solara._layer_panel_helpers import _attr, _tree, all_text, role_widgets


def tiles(layer_id: str, **kwargs) -> LayerSpec:
    url = f"https://t.test/{layer_id}/{{z}}/{{x}}/{{y}}.png"
    return LayerSpec.from_tiles(url, name=layer_id, id=layer_id).model_copy(update=kwargs)


def legend_tiles(layer_id: str) -> LayerSpec:
    item = LegendItem(label=layer_id, color="#111111")
    return tiles(layer_id, legend=Legend(title=layer_id.upper(), items=[item]))


def legend_slots(box) -> list:
    """The legend slots of the view, in document order."""
    return [w for w in _tree(box) if "pysepal-map-legend" in (getattr(w, "class_", "") or "")]


def areas(box) -> list:
    return [_attr(w, "data-area") for w in legend_slots(box)]


def card(box, area: str = "all"):
    """The ``Legend.vue`` widget of an area, or None while the area lists nothing."""
    slot = next(w for w in legend_slots(box) if _attr(w, "data-area") == area)
    return next((w for w in _tree(slot) if hasattr(w, "selector_options")), None)


def listed(box, area: str = "all") -> list:
    """The layer ids an area's card offers, top first."""
    shown = card(box, area)
    return [] if shown is None else [o["value"] for o in shown.selector_options]


def picked(box, area: str = "all"):
    return card(box, area).selected


def pick(box, area: str, layer_id: str) -> None:
    """What the card's select does on a change."""
    card(box, area)._handle_custom_msg({"event": "set_selected", "data": layer_id}, [])


def collapse(box, area: str, collapsed: bool = True) -> None:
    """What the card's toggle bar does on a click."""
    card(box, area)._handle_custom_msg({"event": "set_collapsed", "data": collapsed}, [])


def legend_rule(area: str) -> str:
    return map_view.CSS.split(f'.pysepal-map-legend[data-area="{area}"] {{')[1].split("}")[0]


def flat(css: str) -> str:
    """CSS on one line, without the spaces a wrapped ``calc(`` adds."""
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", " ".join(css.split())))


def container_block(query: str) -> str:
    """The rules inside ``@container <query> { ... }``, on one line."""
    body = map_view.CSS.split(f"@container {query} {{")[1]
    depth, end = 1, 0
    while depth:
        depth += {"{": 1, "}": -1}.get(body[end], 0)
        end += 1
    return flat(body[: end - 1])


def corner(box, name: str):
    return next(w for w in _tree(box) if _attr(w, "data-corner") == name)


def fullscreen_root(box):
    return next(w for w in _tree(box) if _attr(w, "data-psm-fullscreen-root") is not None)


def corner_rule(name: str) -> str:
    return map_view.CSS.split(f'.pysepal-map-corner[data-corner="{name}"] {{')[1].split("}")[0]


def corner_text(box, name: str) -> str:
    return all_text(corner(box, name))


def vector_map(fake_vector, mode="light", **kwargs):
    m = SepalMap(gee=False, theme_state=ThemeState(mode=mode), **kwargs)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    return m


def test_legend_lists_drawn_visible_layers_top_first():
    m = SepalMap(gee=False)
    for key in ("a", "b"):
        m.layer_store.add(legend_tiles(key))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["b", "a"]
    assert card(box).selector_options == [{"value": "b", "text": "b"}, {"value": "a", "text": "a"}]
    assert card(box).legend_data["title"] == "B"
    rc.close()


def test_visible_layer_legend_shows_on_the_map(fake_vector):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["v"]
    assert card(box).title == "Vec"
    rc.close()


def test_hiding_a_layer_drops_its_legend(fake_vector):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["v"]
    m.layer_store.set_visible("v", False)
    assert listed(box) == []
    assert card(box) is None
    m.layer_store.set_visible("v", True)
    assert listed(box) == ["v"]
    rc.close()


def test_legend_follows_the_theme_without_a_store_event(fake_vector):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert card(box).legend_data["items"][0]["color"] == THEMES[False]["primary"]
    theme.set_mode("dark")
    assert card(box).legend_data["items"][0]["color"] == THEMES[True]["primary"]
    rc.close()


def test_two_maps_with_opposite_themes(fake_vector):
    light, dark = vector_map(fake_vector, "light"), vector_map(fake_vector, "dark")
    colors = {}
    for name, m in (("light", light), ("dark", dark)):
        box, rc = solara.render(MapView(m), handle_error=False)
        published = next(x for x in m.state["layers"] if x["id"] == "v")["paint"]["stroke"]
        colors[name] = (card(box).legend_data["items"][0]["color"], published)
        rc.close()
    assert colors["light"][0] == colors["light"][1]
    assert colors["dark"][0] == colors["dark"][1]
    assert colors["light"][0] != colors["dark"][0]


def test_first_render_before_any_draw():
    m = SepalMap(gee=False)
    m.layer_engine.close()
    m.layer_store.add(tiles("a", legend=Legend(title="A", items=[])))
    assert m.state in ({}, {"layers": []}) or not m.state.get("layers")
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == []
    rc.close()


def test_removal_before_the_next_draw():
    m = SepalMap(gee=False)
    m.layer_store.add(legend_tiles("a"))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["a"]
    # the engine publishes on the next tick; the state still holds the removed id
    m.layer_engine.close()
    m.layer_store.remove("a")
    assert [x["id"] for x in m.state["layers"]] == ["a"]
    m.set_insets(left=1)  # a render before the next draw
    assert listed(box) == []
    rc.close()


def test_two_maps_that_accepted_different_renders():
    store_spec = tiles("a")
    first, second = SepalMap(gee=False), SepalMap(gee=False)
    first.layer_store.add(store_spec)
    second.layer_store.add(store_spec)
    # each engine keeps its own accepted render, with its own legend
    for m, title in ((first, "First"), (second, "Second")):
        spec, render = m.layer_engine.accepted("a")
        legend = Legend(title=title, items=[LegendItem(label=title, color="#333333")])
        m.layer_engine._accepted["a"].render = RenderLayer(
            **{**render.__dict__, "legend": legend}
            if hasattr(render, "__dict__")
            else {**render.model_dump(), "legend": legend}
        )
    result = {}
    for name, m in (("first", first), ("second", second)):
        box, rc = solara.render(MapView(m), handle_error=False)
        result[name] = card(box).legend_data["title"]
        rc.close()
    assert result == {"first": "First", "second": "Second"}


def test_one_legend_slot_without_compare(fake_vector):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert areas(box) == ["all"]
    (slot,) = legend_slots(box)
    # next to the corner stacks, so it stays over the map in fullscreen
    assert slot in fullscreen_root(box).children
    assert card(box).placement == "map"
    rc.close()


def test_two_legend_slots_with_compare(fake_vector):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    whole = card(box, "all")
    m.compare = True
    assert areas(box) == ["left", "right"]
    assert all(slot in fullscreen_root(box).children for slot in legend_slots(box))
    # keyed by area: no card is reused for another area
    left, right = card(box, "left"), card(box, "right")
    assert len({id(whole), id(left), id(right)}) == 3
    assert listed(box, "left") == listed(box, "right") == ["v"]
    m.compare = False
    assert areas(box) == ["all"]
    rc.close()


def test_lists_follow_the_sides():
    m = SepalMap(gee=False)
    for layer_id, side in (("a", "left"), ("b", "right"), ("c", "both")):
        m.layer_store.add(legend_tiles(layer_id), side=side)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box, "all") == ["c", "b", "a"]
    m.compare = True
    assert listed(box, "left") == ["c", "a"]
    assert listed(box, "right") == ["c", "b"]
    m.layer_store.set_side("a", "right")
    assert listed(box, "left") == ["c"]
    assert listed(box, "right") == ["c", "b", "a"]
    rc.close()


def test_layers_without_legend_are_not_listed():
    m = SepalMap(gee=False)
    m.layer_store.add(legend_tiles("a"))
    m.layer_store.add(tiles("multiband"))
    assert [x["id"] for x in m.state["layers"]] == ["multiband", "a"]
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["a"]
    assert picked(box) == "a"
    assert card(box).title == "a"
    rc.close()


def test_default_is_the_top_layer():
    m = SepalMap(gee=False)
    for layer_id, side in (("a", "both"), ("b", "right"), ("c", "left")):
        m.layer_store.add(legend_tiles(layer_id), side=side)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert picked(box) == "c"
    assert card(box).title == "c"
    assert card(box).legend_data["title"] == "C"
    m.compare = True
    assert picked(box, "left") == "c"
    assert picked(box, "right") == "b"
    # the default follows the top until the user picks
    m.compare = False
    m.layer_store.move("a", 0)
    assert picked(box) == "a"
    rc.close()


@pytest.mark.parametrize("arrival", [("b", "a"), ("a", "b")])
def test_the_card_starts_on_the_top_layer_whatever_draws_last(arrival):
    m = SepalMap(gee=False)
    for layer_id in ("a", "b"):
        m.layer_store.add(legend_tiles(layer_id))
    # as while the layers prepare: the store holds them, the map draws neither yet
    held = {layer_id: m.layer_engine._accepted.pop(layer_id) for layer_id in ("a", "b")}
    m.layer_engine.flush()
    assert m.state["layers"] == []
    box, rc = solara.render(MapView(m), handle_error=False)
    for layer_id in arrival:
        m.layer_engine._accepted[layer_id] = held[layer_id]
        m.layer_engine.flush()
    assert listed(box) == ["b", "a"]
    assert picked(box) == "b"
    rc.close()


def test_a_new_layer_is_shown_at_once():
    m = SepalMap(gee=False)
    for layer_id in ("a", "b"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "a")
    assert picked(box) == "a"
    m.layer_store.add(legend_tiles("c"), index=2)  # at the bottom, still new
    assert listed(box) == ["b", "a", "c"]
    assert picked(box) == "c"
    assert card(box).legend_data["title"] == "C"
    # two at once, as in one tick on a loop: the topmost new one
    with m.layer_engine._batch():
        m.layer_store.add(legend_tiles("d"), index=1)
        m.layer_store.add(legend_tiles("e"), index=3)
    assert listed(box) == ["b", "d", "a", "e", "c"]
    assert picked(box) == "d"
    # a layer shown again is not new
    pick(box, "all", "a")
    m.layer_store.set_visible("b", False)
    m.layer_store.set_visible("b", True)
    assert picked(box) == "a"
    rc.close()


def test_a_legend_added_from_a_pool_worker_is_built_in_the_kernel(kernel_contexts, kernel_comms):
    """A pool worker has no kernel context: a legend built there would never reach the browser."""
    context = kernel_contexts()

    def orphans(box) -> list:
        return [w for w in _tree(box) if w.comm is None or w.comm.kernel is not context.kernel]

    async def page():
        m = SepalMap(gee=False)
        m._handle_custom_msg({"type": "view_open", "view_id": "a", "side": "main"}, [])
        box, rc = solara.render(MapView(m), handle_error=False)
        await asyncio.to_thread(m.layer_store.add, legend_tiles("a"))
        await m.layer_engine.wait_idle()
        assert "Loading layers (1)" in corner_text(box, "top-right")  # until the view draws it
        await wait_until(lambda: listed(box) == ["a"])
        assert card(box).comm.kernel is context.kernel
        assert orphans(box) == []
        rc.close()
        m.close()

    with context:
        asyncio.run(page())


def test_fallback_when_the_selected_layer_hides():
    m = SepalMap(gee=False)
    for layer_id in ("a", "b", "c"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "b")
    m.layer_store.set_visible("b", False)
    assert picked(box) == "c"
    # the user's pick comes back with the layer
    m.layer_store.set_visible("b", True)
    assert picked(box) == "b"
    # and survives an empty list
    for layer_id in ("a", "b", "c"):
        m.layer_store.set_visible(layer_id, False)
    assert card(box) is None
    for layer_id in ("a", "b", "c"):
        m.layer_store.set_visible(layer_id, True)
    assert picked(box) == "b"
    m.layer_store.remove("b")
    assert picked(box) == "c"
    rc.close()


def test_a_pick_outside_the_left_half_survives_compare():
    m = SepalMap(gee=False)
    for layer_id, side in (("a", "both"), ("r", "right")):
        m.layer_store.add(legend_tiles(layer_id), side=side)
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "a")
    pick(box, "all", "r")
    m.compare = True
    # the left half does not draw it, so it shows its top layer meanwhile
    assert listed(box, "left") == ["a"]
    assert picked(box, "left") == "a"
    m.compare = False
    assert picked(box) == "r"
    rc.close()


def test_collapse_is_per_area():
    m = SepalMap(gee=False)
    m.layer_store.add(legend_tiles("a"))
    m.compare = True
    box, rc = solara.render(MapView(m), handle_error=False)
    assert card(box, "left").collapsed is card(box, "right").collapsed is False
    collapse(box, "left")
    assert card(box, "left").collapsed is True
    assert card(box, "right").collapsed is False
    collapse(box, "right")
    collapse(box, "left", False)
    assert card(box, "left").collapsed is False
    assert card(box, "right").collapsed is True
    rc.close()


def test_compare_toggle_keeps_the_pick():
    m = SepalMap(gee=False)
    for layer_id in ("a", "b", "c"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "b")
    collapse(box, "all")
    m.compare = True
    # the left half continues the whole map's card
    assert (picked(box, "left"), card(box, "left").collapsed) == ("b", True)
    assert (picked(box, "right"), card(box, "right").collapsed) == ("c", False)
    pick(box, "right", "a")
    m.compare = False
    assert (picked(box), card(box).collapsed) == ("b", True)
    m.compare = True
    assert picked(box, "left") == "b"
    assert picked(box, "right") == "a"
    rc.close()


def test_turning_compare_off_keeps_the_left_pick():
    m = SepalMap(gee=False)
    for layer_id, side in (("a", "left"), ("b", "both"), ("r", "right")):
        m.layer_store.add(legend_tiles(layer_id), side=side)
    m.compare = True
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "left", "a")
    m.compare = False
    # the right-only layer was drawn all along: the whole map's card is not new to it
    assert listed(box) == ["r", "b", "a"]
    assert picked(box) == "a"
    m.compare = True
    assert picked(box, "left") == "a"
    # a right-only layer added meanwhile is new to the right half only
    m.layer_store.add(legend_tiles("s"), side="right")
    assert picked(box, "right") == "s"
    m.compare = False
    assert picked(box) == "a"
    rc.close()


def test_an_empty_legend_is_not_listed_and_keeps_the_pick(fake_vector):
    m = SepalMap(gee=False)
    for layer_id in ("a", "b"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "a")
    m.layer_store.add(tiles("muted", legend=Legend()))
    assert listed(box) == ["b", "a"]
    assert picked(box) == "a"
    # an empty legend wins over the one the style would give
    vector = LayerSpec.from_vector(fake_vector, id="v", name="Vec")
    m.layer_store.add(vector.model_copy(update={"legend": Legend()}))
    assert listed(box) == ["b", "a"]
    assert picked(box) == "a"
    # the next layer that has a legend is still new
    m.layer_store.add(legend_tiles("c"))
    assert picked(box) == "c"
    rc.close()


def test_an_empty_legend_wins_over_the_render_one():
    m = SepalMap(gee=False)
    m.layer_store.add(tiles("asset"))
    m.layer_store.add(tiles("muted", legend=Legend()))
    # as an Earth Engine asset's visualization gives its render a legend
    asset = Legend(title="Asset", items=[LegendItem(label="x", color="#333333")])
    for layer_id in ("asset", "muted"):
        accepted = m.layer_engine._accepted[layer_id]
        accepted.render = dataclasses.replace(accepted.render, legend=asset)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["asset"]
    rc.close()


def test_a_local_raster_lists_the_stretch_its_tiles_use(ramp):
    m = SepalMap(gee=False)
    m.add_raster(ramp, layer_name="Ramp", key="ramp", colormap="viridis")
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["ramp"]
    (gradient,) = card(box).legend_data["gradients"]
    assert gradient["labels"] == ["10", "90"]
    # an explicit legend still wins, and an empty one shows none
    m.find_layer("ramp").legend = legend_tiles("x").legend
    assert card(box).legend_data["title"] == "X"
    m.find_layer("ramp").legend = Legend()
    assert listed(box) == []
    rc.close()


def test_a_renamed_raster_never_shows_another_layers_name(ramp):
    # the engine caches renders by data and style, so both layers share one render
    m = SepalMap(gee=False)
    m.add_raster(ramp, layer_name="First", key="a", colormap="viridis")
    m.add_raster(ramp, layer_name="Second", key="b", colormap="viridis")
    m.layer_store.update("a", m.layer_store.get("a").model_copy(update={"name": "Renamed"}))
    box, rc = solara.render(MapView(m), handle_error=False)
    pick(box, "all", "a")
    assert card(box).title == "Renamed"
    shown = card(box).legend_data
    assert {shown["title"], *(g["title"] for g in shown["gradients"])} <= {"", "Renamed"}
    rc.close()


def test_a_layer_removed_and_added_again_is_new():
    m = SepalMap(gee=False)
    for layer_id in ("a", "b"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    m.layer_store.add(legend_tiles("result"))
    assert picked(box) == "result"
    pick(box, "all", "a")
    # as a process run again: its result goes, and comes back under the same id
    m.layer_store.remove("result")
    assert picked(box) == "a"
    m.layer_store.add(legend_tiles("result"))
    assert picked(box) == "result"
    rc.close()


def test_what_the_whole_map_lists_is_not_new_to_the_right_half():
    m = SepalMap(gee=False)
    for layer_id in ("a", "b", "c"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(MapView(m), handle_error=False)
    m.compare = True
    pick(box, "right", "a")
    m.compare = False
    m.layer_store.add(legend_tiles("x"))
    assert picked(box) == "x"
    pick(box, "all", "b")
    m.compare = True
    assert picked(box, "left") == "b"
    assert picked(box, "right") == "a"
    rc.close()


def test_a_new_layer_survives_a_second_render_before_the_effects():
    """Reacton renders again before the effects when a component sets state while rendering."""

    @solara.component
    def Count(store, set_count):
        use_layer_store(store)
        set_count(len(store.ids))
        return solara.Text("")

    @solara.component
    def Page(m):
        count, set_count = solara.use_state(0)
        with solara.Column() as main:
            Count(m.layer_store, set_count)
            # a new dict each render: the view renders again with its parent
            MapView(m, overlays={"top-left": [solara.Text(str(count))]})
        return main

    m = SepalMap(gee=False)
    for layer_id in ("a", "b"):
        m.layer_store.add(legend_tiles(layer_id))
    box, rc = solara.render(Page(m), handle_error=False)
    pick(box, "all", "a")
    with rc:  # one batch, as in an event handler
        m.layer_store.add(legend_tiles("c"))
    assert listed(box) == ["c", "b", "a"]
    assert picked(box) == "c"
    rc.close()


def test_placement_css_centres_each_area():
    base = map_view.CSS.split(".pysepal-map-legend {")[1].split("}")[0]
    for declaration in ("position: absolute", "transform: translateX(-50%)", "z-index: 3"):
        assert declaration in base
    centre = {
        "all": "calc(var(--pysepal-inset-left) + (100% - var(--pysepal-inset-left)"
        " - var(--pysepal-inset-right)) / 2)",
        "left": "calc((var(--pysepal-inset-left) + var(--psm-divider-x, 50%)) / 2)",
        "right": "calc((var(--psm-divider-x, 50%) + 100% - var(--pysepal-inset-right)) / 2)",
    }
    for area in ("all", "left", "right"):
        rule = flat(legend_rule(area))
        assert f"left: {centre[area]};" in rule
        assert "bottom:" not in rule
    # every card clears the taller bottom corner, so the two halves' cards share one baseline
    clear = "max(var(--psm-controls-bottom-left, 0px), var(--psm-controls-bottom-right, 0px))"
    assert f"bottom: calc(var(--pysepal-inset-bottom) + {clear} + 10px);" in flat(base)
    # a long legend scrolls inside the card, which the slot caps
    assert "flex-direction: column" in base
    assert "max-height: 40%" in base


def test_a_card_hides_when_its_area_has_no_room():
    # each slot is its area less 10 px a side, so the queries read 140 and 60 px areas
    width = {
        "all": "calc(100% - var(--pysepal-inset-left) - var(--pysepal-inset-right) - 20px)",
        "left": "calc(var(--psm-divider-x, 50%) - var(--pysepal-inset-left) - 20px)",
        "right": "calc(100% - var(--pysepal-inset-right) - var(--psm-divider-x, 50%) - 20px)",
    }
    for area in ("all", "left", "right"):
        assert f"width: {width[area]};" in flat(legend_rule(area))
    base = map_view.CSS.split(".pysepal-map-legend {")[1].split("}")[0]
    assert "container: pysepal-legend / inline-size" in base
    # three classes: Legend.vue's scoped rules are a class and an attribute, and come later
    slot = ".pysepal-map-root > .pysepal-map-legend"
    narrow = container_block("pysepal-legend (width < 120px)")
    assert f"{slot} .sepal-legend__body {{ display: none; }}" in narrow
    assert f"{slot} .sepal-legend {{ pointer-events: none; }}" in narrow
    # the pill: the icon and the shown layer's name, without the chevron
    assert f"{slot} .sepal-legend__chevron {{ display: none; }}" in narrow
    assert f"{slot} .sepal-legend__bar-title {{ display: inline; }}" in narrow
    assert ":last-child" not in narrow
    gone = container_block("pysepal-legend (width < 40px)")
    assert f"{slot} .sepal-legend {{ display: none; }}" in gone


def test_no_legend_slot_when_legend_is_off(fake_vector):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m, legend=False), handle_error=False)
    assert legend_slots(box) == []
    m.compare = True
    assert legend_slots(box) == []
    rc.close()


def test_the_legends_follow_the_publishes_only(fake_vector, monkeypatch):
    derived, renders = [], []
    real_legends, real_labels = map_view._legends, map_view._draw_labels
    monkeypatch.setattr(map_view, "_legends", lambda m: derived.append(1) or real_legends(m))
    monkeypatch.setattr(map_view, "_draw_labels", lambda: renders.append(1) or real_labels())
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert len(derived) == 1
    mounted = len(renders)
    m.set_insets(left=10)  # renders, publishes nothing
    assert len(renders) == mounted + 1 and len(derived) == 1
    m.cursor = "pointer"  # nothing in the view reads it
    assert len(renders) == mounted + 1
    m.layer_store.set_opacity("v", 0.5)
    assert len(derived) == 2
    rc.close()


def test_stacks_use_zero_insets_in_fullscreen():
    assert "[data-psm-fullscreen-root][data-psm-fullscreen]" in map_view.CSS
    rule = map_view.CSS.split("[data-psm-fullscreen-root][data-psm-fullscreen] {")[1].split("}")[0]
    for side in ("left", "right", "top", "bottom"):
        assert f"--pysepal-inset-{side}: 0px !important" in rule


def test_overlays_render_in_their_corner():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m, overlays={"top-right": [solara.Text("hi")]}))
    assert "hi" in corner_text(box, "top-right")
    assert "hi" not in corner_text(box, "top-left")
    rc.close()


def test_stacks_follow_the_insets():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    view = box.children[0]
    assert "--pysepal-inset-left: 0px" in view.style_
    m.set_insets(left=320, right=380, top=48, bottom=10)
    assert "--pysepal-inset-left: 320px" in view.style_
    assert "--pysepal-inset-right: 380px" in view.style_
    assert "--pysepal-inset-top: 48px" in view.style_
    assert "--pysepal-inset-bottom: 10px" in view.style_
    rc.close()


def test_status_counts_pending_layers():
    m = SepalMap(gee=False)
    m.layer_engine.close()
    m.layer_store.add(tiles("a"))
    m.layer_store.add(tiles("b"))
    m.layer_store.set_status("a", "pending")
    m.layer_store.set_status("b", "pending")
    box, rc = solara.render(MapView(m), handle_error=False)
    assert "Loading layers (2)" in corner_text(box, "top-right")
    m.layer_store.set_status("a", "ready")
    assert "Loading layers (1)" in corner_text(box, "top-right")
    m.layer_store.set_status("b", "ready")
    assert corner_text(box, "top-right").strip() == ""
    rc.close()


def test_root_is_the_fullscreen_target():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    root = fullscreen_root(box)
    # The overlays are siblings of the map, so they stay over it in fullscreen.
    assert root.children[0] is m
    assert [_attr(w, "data-corner") for w in root.children[1:5]] == list(map_view.CORNERS)
    assert root.children[5:] == legend_slots(box)
    rc.close()


def test_the_fullscreen_root_binds_no_style():
    m = SepalMap(gee=False)
    m.set_insets(left=320)
    box, rc = solara.render(MapView(m), handle_error=False)
    view, root = box.children[0], fullscreen_root(box)
    assert view.class_ == "pysepal-map-view"
    assert root in view.children
    assert root.class_ == "pysepal-map-root"
    assert root.style_ is None
    assert "--pysepal-inset-left: 320px" in view.style_
    assert "height: 400px" in view.style_
    m.set_insets(left=0)
    m.height = "100%"
    assert root.style_ is None
    rc.close()


def test_stacks_clear_the_measured_corners():
    m = SepalMap(gee=False, coordinates=True)
    m.layer_engine.flush()
    m.draw.begin(["polygon"])
    box, rc = solara.render(MapView(m), handle_error=False)
    for name in map_view.CORNERS:
        side = name.split("-")[0]
        offset = f"var(--pysepal-inset-{side}) + var(--psm-controls-{name}, 0px) + 10px"
        assert f"{side}: calc({offset})" in corner_rule(name)
    cap = corner_rule("top-left").split("max-height:")[1].split(";")[0]
    for name in ("top-left", "bottom-left"):
        assert f"- var(--psm-controls-{name}, 0px) - 10px" in cap
    styles = [w.style_ for w in _tree(box) if getattr(w, "style_", None)]
    assert styles and not [s for s in styles if "--pysepal-controls-" in s]
    assert "--pysepal-controls-" not in map_view.CSS
    rc.close()


def test_stacks_wait_for_the_measure():
    hidden = ".pysepal-map-root:not([data-psm-controls]) > .pysepal-map-corner"
    assert f"{hidden} {{ visibility: hidden; }}" in map_view.CSS
    hidden = ".pysepal-map-root:not([data-psm-controls]) > .pysepal-map-legend"
    assert f"{hidden} {{ visibility: hidden; }}" in map_view.CSS
    root_rule = map_view.CSS.split(".pysepal-map-root {")[1].split("}")[0]
    assert "position: relative" in root_rule


def test_view_takes_the_map_height():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    view = box.children[0]
    # an auto-height parent (a notebook output) then gets the map's own 400 px, not 0
    assert "height: 400px" in view.style_
    m.height = "100%"
    assert "height: 100%" in view.style_
    view_rule = map_view.CSS.split(".pysepal-map-view {")[1].split("}")[0]
    assert "height" not in view_rule
    rc.close()


def test_map_app_fills_the_window_whatever_the_map_height():
    css = (Path(map_app.__file__).parent / "map_app.css").read_text()
    rule = css.split(".sepal-mapapp__map .pysepal-map-view,")[1].split("}")[0]
    assert ".sepal-mapapp__map .psm-map" in rule
    assert "height: 100% !important" in rule


def test_legend_skips_overlay_layers(fake_vector):
    m = vector_map(fake_vector)
    aoi = LayerSpec.from_vector(fake_vector, id="aoi", name="AOI").model_copy(
        update={"zone": "overlay"}
    )
    m.layer_store.add(aoi)
    assert "aoi" in [x["id"] for x in m.state["layers"]]
    box, rc = solara.render(MapView(m), handle_error=False)
    assert listed(box) == ["v"]
    rc.close()


def counter(mounts: list):
    """An overlay with its own state; ``mounts`` logs each mount and unmount."""

    @solara.component
    def Counter():
        count, set_count = solara.use_state(0)

        def effect():
            mounts.append("mount")
            return lambda: mounts.append("unmount")

        solara.use_effect(effect, [])
        return solara.Button(f"count {count}", on_click=lambda: set_count(count + 1))

    return Counter()


def test_app_overlay_keeps_its_state_when_the_legend_comes_and_goes(fake_vector):
    mounts = []
    m = SepalMap(gee=False)
    box, rc = solara.render(
        MapView(m, overlays={"bottom-right": [counter(mounts)]}), handle_error=False
    )
    rc.find(v.Btn, children=["count 0"]).widget.click()
    assert "count 1" in corner_text(box, "bottom-right")
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    assert listed(box) == ["v"]
    m.compare = True
    assert listed(box, "right") == ["v"]
    m.compare = False
    m.layer_store.set_visible("v", False)
    assert listed(box) == []
    assert "count 1" in corner_text(box, "bottom-right")
    assert mounts == ["mount"]
    rc.close()


def test_app_overlay_keeps_its_state_when_the_status_comes_and_goes():
    mounts = []
    m = SepalMap(gee=False)
    m.layer_engine.close()
    m.layer_store.add(tiles("a"))
    box, rc = solara.render(
        MapView(m, overlays={"top-right": [counter(mounts)]}), handle_error=False
    )
    rc.find(v.Btn, children=["count 0"]).widget.click()
    m.layer_store.set_status("a", "pending")
    assert "Loading layers (1)" in corner_text(box, "top-right")
    m.layer_store.set_status("a", "ready")
    assert "count 1" in corner_text(box, "top-right")
    assert mounts == ["mount"]
    rc.close()


def test_idle_slots_are_hidden():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    (slot,) = role_widgets(box, "map-status")
    assert _attr(slot, "data-idle") is not None
    assert role_widgets(box, "map-legend") == []
    assert ".pysepal-map-corner > [data-idle] { display: none; }" in map_view.CSS
    rc.close()


def test_map_app_passes_overlays_to_the_map_view():
    m = SepalMap(gee=False)
    box, rc = solara.render(
        MapApp(main_map=m, map_overlays={"bottom-left": [solara.Text("overlay-text")]}),
        handle_error=False,
    )
    assert "overlay-text" in corner_text(box, "bottom-left")
    rc.close()


def test_slot_keys_stay_stable_when_the_toolbar_and_inspector_come_and_go():
    mounts = []
    m = SepalMap(gee=False, inspector=True)
    box, rc = solara.render(
        MapView(m, overlays={"top-left": [counter(mounts)]}), handle_error=False
    )
    rc.find(v.Btn, children=["count 0"]).widget.click()
    session = m.draw.begin(["polygon"])
    m.inspector.activate()
    m.inspector.inspection = Inspection(0.0, 0.0, 1.0, (), False)
    session.end()
    m.inspector.deactivate()
    assert "count 1" in corner_text(box, "top-left")
    assert mounts == ["mount"]
    assert len(role_widgets(box, "map-inspector")) == 1
    rc.close()


def test_map_view_has_no_draw_slot():
    m = SepalMap(gee=False)
    m.draw.begin(["polygon"])
    box, rc = solara.render(MapView(m), handle_error=False)
    assert role_widgets(box, "map-draw") == []
    assert role_widgets(box, "draw-mode") == role_widgets(box, "draw-clear") == []
    assert [
        w for w in _tree(box) if "pysepal-map-toolbar" in (getattr(w, "class_", "") or "")
    ] == []
    rc.close()


def test_map_view_sets_the_draw_labels():
    m = SepalMap(gee=False)
    keys = ("polygon", "rectangle", "circle", "linestring", "point", "select")
    want = {**{k: msg(f"map_view.draw.{k}") for k in keys}, "clear": msg("map_view.draw.clear_all")}
    assert m.drawing["labels"] == want
    m.draw.set_labels({"clear": "x"})
    box, rc = solara.render(MapView(m), handle_error=False)
    assert m.drawing["labels"]["clear"] == msg("map_view.draw.clear_all")
    assert m.drawing["labels"] == want
    rc.close()


class _Toasts:
    """Stands in for the notifier: records the error toasts."""

    def __init__(self):
        self.errors = []

    def error(self, message, **kwargs):
        self.errors.append(message)


def test_a_layer_error_is_toasted_once_per_layer_instance(monkeypatch):
    toasts = _Toasts()
    monkeypatch.setattr(map_view, "use_notifications", lambda required=True: toasts)
    m = SepalMap(gee=False)
    m.layer_engine.close()
    store = m.layer_store
    store.add(tiles("a"))
    _, rc = solara.render(MapView(m), handle_error=False)
    _, rc2 = solara.render(MapView(m), handle_error=False)  # a second view of the store

    # the tile URL stays in the row's tooltip and the console
    store.set_status("a", "error", error="AJAXError: Failed to fetch (0): http://h:1/8/1/2.png?a=b")
    assert toasts.errors == [
        msg("map_view.layer_error", name="a", error="AJAXError: Failed to fetch (0)")
    ]

    # its tiles keep failing, each with its own message
    store.set_status("a", "pending")
    store.set_status("a", "error", error="AJAXError: Not Found (404): /_pysepal/tiles/1/8/1/3.png")
    store.set_visible("a", False)
    assert len(toasts.errors) == 1

    # a new style is a new instance, and so is the layer added again
    store.restyle("a", colormap="magma")
    store.set_status("a", "error", error="boom")
    store.remove("a")
    store.add(tiles("a"))
    store.set_status("a", "error", error="boom")
    assert len(toasts.errors) == 3
    rc.close()
    rc2.close()
