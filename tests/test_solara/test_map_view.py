"""MapView places the map, the legend of what it draws, a loading status and app overlays."""

import pytest
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import LayerSpec, Legend, LegendItem, RenderLayer
from pysepal.mapping import SepalMap
from pysepal.solara.components import map_view
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


def test_map_app_passes_overlays_to_the_map_view():
    m = SepalMap(gee=False)
    box, rc = solara.render(
        MapApp(main_map=m, map_overlays={"bottom-left": [solara.Text("overlay-text")]}),
        handle_error=False,
    )
    assert "overlay-text" in corner_text(box, "bottom-left")
    rc.close()
