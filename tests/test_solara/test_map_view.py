"""MapView places the map, the legend of what it draws, a loading status and app overlays."""

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
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.components.map_view import MapView
from pysepal.solara.theme import ThemeState
from tests.test_solara._layer_panel_helpers import _attr, _tree, all_text, role_widgets


@pytest.fixture
def shown(monkeypatch):
    """Record each LegendComponent render as ``(legend_data, inline)``, newest render last."""
    calls = []

    @solara.component
    def Stub(legend_data, inline=False):
        calls.append((legend_data, inline))
        return solara.Text("legend:" + legend_data["title"])

    monkeypatch.setattr(map_view, "LegendComponent", Stub)
    return calls


def tiles(layer_id: str, **kwargs) -> LayerSpec:
    url = f"https://t.test/{layer_id}/{{z}}/{{x}}/{{y}}.png"
    return LayerSpec.from_tiles(url, name=layer_id, id=layer_id).model_copy(update=kwargs)


def legend_titles(box) -> list:
    """The titles of the legends rendered in the map-legend wrapper, top first."""
    wrappers = role_widgets(box, "map-legend")
    if not wrappers:
        return []
    texts = [
        child
        for w in _tree(wrappers[0])
        for child in getattr(w, "children", ()) or ()
        if isinstance(child, str)
    ]
    return [t.removeprefix("legend:") for t in texts]


def corner(box, name: str):
    return next(w for w in _tree(box) if _attr(w, "data-corner") == name)


def corner_text(box, name: str) -> str:
    return all_text(corner(box, name))


def vector_map(fake_vector, mode="light", **kwargs):
    m = SepalMap(gee=False, theme_state=ThemeState(mode=mode), **kwargs)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    return m


def test_legend_lists_drawn_visible_layers_top_first(shown):
    m = SepalMap(gee=False)
    legends = {
        "a": Legend(title="A", items=[LegendItem(label="a", color="#111111")]),
        "b": Legend(title="B", items=[LegendItem(label="b", color="#222222")]),
    }
    for key in ("a", "b"):
        m.layer_store.add(tiles(key, legend=legends[key]))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == ["B", "A"]
    rc.close()


def test_visible_layer_legend_shows_on_the_map(fake_vector, shown):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == ["Vec"]
    rc.close()


def test_hiding_a_layer_drops_its_legend(fake_vector, shown):
    m = vector_map(fake_vector)
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == ["Vec"]
    m.layer_store.set_visible("v", False)
    assert legend_titles(box) == []
    m.layer_store.set_visible("v", True)
    assert legend_titles(box) == ["Vec"]
    rc.close()


def test_legend_follows_the_theme_without_a_store_event(fake_vector, shown):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert shown[-1][0]["items"][0]["color"] == THEMES[False]["primary"]
    theme.set_mode("dark")
    assert shown[-1][0]["items"][0]["color"] == THEMES[True]["primary"]
    rc.close()


def test_two_maps_with_opposite_themes(fake_vector, shown):
    light, dark = vector_map(fake_vector, "light"), vector_map(fake_vector, "dark")
    colors = {}
    for name, m in (("light", light), ("dark", dark)):
        del shown[:]
        box, rc = solara.render(MapView(m), handle_error=False)
        published = next(x for x in m.state["layers"] if x["id"] == "v")["paint"]["stroke"]
        colors[name] = (shown[-1][0]["items"][0]["color"], published)
        rc.close()
    assert colors["light"][0] == colors["light"][1]
    assert colors["dark"][0] == colors["dark"][1]
    assert colors["light"][0] != colors["dark"][0]


def test_first_render_before_any_draw(shown):
    m = SepalMap(gee=False)
    m.layer_engine.close()
    m.layer_store.add(tiles("a", legend=Legend(title="A", items=[])))
    assert m.state in ({}, {"layers": []}) or not m.state.get("layers")
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == []
    rc.close()


def test_removal_before_the_next_draw(shown):
    m = SepalMap(gee=False)
    legend = Legend(title="A", items=[LegendItem(label="a", color="#111111")])
    m.layer_store.add(tiles("a", legend=legend))
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == ["A"]
    # the engine publishes on the next tick; the state still holds the removed id
    m.layer_engine.close()
    m.layer_store.remove("a")
    assert [x["id"] for x in m.state["layers"]] == ["a"]
    m.set_insets(left=1)  # a render before the next draw
    assert legend_titles(box) == []
    rc.close()


def test_two_maps_that_accepted_different_renders(shown):
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
        result[name] = legend_titles(box)
        rc.close()
    assert result == {"first": ["First"], "second": ["Second"]}


def test_stacks_use_zero_insets_in_fullscreen():
    assert "[data-psm-fullscreen-root][data-psm-fullscreen]" in map_view.CSS
    rule = map_view.CSS.split("[data-psm-fullscreen-root][data-psm-fullscreen] {")[1].split("}")[0]
    for side in ("left", "right", "top", "bottom"):
        assert f"--pysepal-inset-{side}: 0px !important" in rule


def test_legends_render_inline(fake_vector, shown):
    box, rc = solara.render(MapView(vector_map(fake_vector)), handle_error=False)
    assert shown and all(inline is True for _, inline in shown)
    rc.close()


def test_overlays_render_in_their_corner():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m, overlays={"top-right": [solara.Text("hi")]}))
    assert "hi" in corner_text(box, "top-right")
    assert "hi" not in corner_text(box, "top-left")
    rc.close()


def test_stacks_follow_the_insets():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    root = box.children[0]
    assert "--pysepal-inset-left: 0px" in root.style_
    m.set_insets(left=320, right=380, top=48, bottom=10)
    assert "--pysepal-inset-left: 320px" in root.style_
    assert "--pysepal-inset-right: 380px" in root.style_
    assert "--pysepal-inset-top: 48px" in root.style_
    assert "--pysepal-inset-bottom: 10px" in root.style_
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
    assert _attr(box.children[0], "data-psm-fullscreen-root") is not None
    assert m in list(_tree(box))
    rc.close()


def test_root_takes_the_map_height():
    m = SepalMap(gee=False)
    box, rc = solara.render(MapView(m), handle_error=False)
    root = box.children[0]
    # an auto-height parent (a notebook output) then gets the map's own 400 px, not 0
    assert "height: 400px" in root.style_
    m.height = "100%"
    assert "height: 100%" in root.style_
    root_rule = map_view.CSS.split(".pysepal-map-view {")[1].split("}")[0]
    assert "height" not in root_rule
    rc.close()


def test_map_app_fills_the_window_whatever_the_map_height():
    css = (Path(map_app.__file__).parent / "map_app.css").read_text()
    rule = css.split(".sepal-mapapp__map .pysepal-map-view,")[1].split("}")[0]
    assert ".sepal-mapapp__map .psm-map" in rule
    assert "height: 100% !important" in rule


def test_legend_skips_overlay_layers(fake_vector, shown):
    m = vector_map(fake_vector)
    aoi = LayerSpec.from_vector(fake_vector, id="aoi", name="AOI").model_copy(
        update={"zone": "overlay"}
    )
    m.layer_store.add(aoi)
    assert "aoi" in [x["id"] for x in m.state["layers"]]
    box, rc = solara.render(MapView(m), handle_error=False)
    assert legend_titles(box) == ["Vec"]
    rc.close()


@pytest.mark.parametrize(("fullscreen_control", "offset"), [(False, "78px"), (True, "117px")])
def test_top_left_stack_clears_the_controls(fullscreen_control, offset):
    m = SepalMap(gee=False, fullscreen_control=fullscreen_control)
    m.layer_engine.flush()
    assert m.state["controls"]["fullscreen"] is fullscreen_control
    box, rc = solara.render(MapView(m), handle_error=False)
    assert f"--pysepal-controls-top-left: {offset}" in box.children[0].style_
    assert "var(--pysepal-controls-top-left)" in map_view.CSS
    cap = map_view.CSS.split('[data-corner="top-left"] {')[1].split("}")[0]
    assert "- var(--pysepal-controls-bottom-left)" in cap
    assert "10px\n  );" not in cap
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


def test_app_overlay_keeps_its_state_when_the_legend_comes_and_goes(fake_vector, shown):
    mounts = []
    m = SepalMap(gee=False)
    box, rc = solara.render(
        MapView(m, overlays={"bottom-right": [counter(mounts)]}), handle_error=False
    )
    rc.find(v.Btn, children=["count 0"]).widget.click()
    assert "count 1" in corner_text(box, "bottom-right")
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v", name="Vec"))
    assert legend_titles(box) == ["Vec"]
    m.layer_store.set_visible("v", False)
    assert legend_titles(box) == []
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
    for role in ("map-status", "map-legend"):
        (slot,) = role_widgets(box, role)
        assert _attr(slot, "data-idle") is not None
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


def test_top_left_stack_clears_the_draw_toolbar():
    m = SepalMap(gee=False)
    m.layer_engine.flush()
    box, rc = solara.render(MapView(m), handle_error=False)
    assert "--pysepal-controls-top-left: 78px" in box.children[0].style_
    # Two tools and select, then the clear button: four 29 px buttons and a 10 px margin.
    session = m.draw.begin(["polygon", "point"])
    assert "--pysepal-controls-top-left: 204px" in box.children[0].style_
    session.end()
    assert "--pysepal-controls-top-left: 78px" in box.children[0].style_
    rc.close()


@pytest.mark.parametrize(("coordinates", "offset"), [(False, "36px"), (True, "64px")])
def test_bottom_left_stack_clears_the_coordinates_readout(coordinates, offset):
    m = SepalMap(gee=False, coordinates=coordinates)
    m.layer_engine.flush()
    assert bool(m.state["controls"].get("coordinates")) is coordinates
    box, rc = solara.render(MapView(m), handle_error=False)
    assert f"--pysepal-controls-bottom-left: {offset}" in box.children[0].style_
    assert "var(--pysepal-controls-bottom-left)" in map_view.CSS
    rc.close()
