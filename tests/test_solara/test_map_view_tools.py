"""The draw toolbar, the inspector toggle and the inspector card of MapView."""

import solara

from pysepal.mapping import SepalMap
from pysepal.mapping.inspector import InspectedLayer, Inspection
from pysepal.solara.components.map_view import MapView
from tests.test_solara._layer_panel_helpers import _attr, all_text, click, role_widgets


def render(m):
    return solara.render(MapView(m), handle_error=False)


def mode_buttons(box):
    return role_widgets(box, "draw-mode")


def test_toolbar_hidden_until_enabled():
    m = SepalMap(gee=False)
    box, rc = render(m)
    assert mode_buttons(box) == []
    assert _attr(role_widgets(box, "map-draw")[0], "data-idle") is not None
    m.draw.enable(["polygon", "point"])
    assert [_attr(b, "data-mode") for b in mode_buttons(box)] == ["polygon", "point", "select"]
    assert _attr(role_widgets(box, "map-draw")[0], "data-idle") is None
    m.draw.disable()
    assert mode_buttons(box) == []
    rc.close()


def test_toolbar_starts_and_stops_modes():
    m = SepalMap(gee=False)
    m.draw.enable(["polygon", "circle"], edit=False)
    box, rc = render(m)
    click(mode_buttons(box)[0])
    assert m.draw.mode == "polygon"
    assert [_attr(b, "data-active") for b in mode_buttons(box)] == ["true", "false"]
    click(mode_buttons(box)[1])
    assert m.draw.mode == "circle"
    click(mode_buttons(box)[1])
    assert m.draw.mode == "static"
    assert [_attr(b, "data-active") for b in mode_buttons(box)] == ["false", "false"]
    rc.close()


def test_clear_button_clears():
    m = SepalMap(gee=False)
    m.draw.enable(["polygon"])
    seq = m.draw_request["seq"]
    box, rc = render(m)
    click(role_widgets(box, "draw-clear")[0])
    assert m.draw_request["seq"] == seq + 1
    assert m.draw_request["features"] == []
    rc.close()


def test_inspector_toggle_calls_activate_and_deactivate():
    m = SepalMap(gee=False, inspector=True)
    box, rc = render(m)
    click(role_widgets(box, "inspector-toggle")[0])
    assert m.inspector.active and m.cursor == "crosshair"
    assert _attr(role_widgets(box, "inspector-toggle")[0], "data-active") == "true"
    click(role_widgets(box, "inspector-toggle")[0])
    assert not m.inspector.active
    rc.close()


def inspection(*layers, pending=False):
    return Inspection(-1.5, 2.123456, 30.0, tuple(layers), pending)


def test_card_shows_rows_errors_and_pending():
    m = SepalMap(gee=False, inspector=True)
    box, rc = render(m)
    assert role_widgets(box, "inspector-card") == []
    m.inspector.inspection = inspection(
        InspectedLayer("a", "Alpha", "ready", (("b1", "12"), ("b2", "7"))),
        InspectedLayer("b", "Beta", "empty"),
        InspectedLayer("c", "Gamma", "error", error="boom"),
        InspectedLayer("d", "Delta", "changed"),
        InspectedLayer("e", "Eps", "unsupported"),
        pending=True,
    )
    text = all_text(role_widgets(box, "inspector-card")[0])
    for expected in (
        "2.12346, -1.50000",
        "Alpha",
        "b1: 12",
        "b2: 7",
        "No data at this point",
        "boom",
        "This layer changed, click again",
        "This layer cannot be inspected",
    ):
        assert expected in text
    assert len(role_widgets(box, "inspector-pending")) == 1
    m.inspector.inspection = inspection(pending=False)
    assert role_widgets(box, "inspector-pending") == []
    m.inspector.inspection = None
    assert role_widgets(box, "inspector-card") == []
    rc.close()


def test_inspector_hidden_without_inspector():
    m = SepalMap(gee=False)
    box, rc = render(m)
    assert role_widgets(box, "inspector-toggle") == []
    assert _attr(role_widgets(box, "map-inspector")[0], "data-idle") is not None
    rc.close()


def test_card_height_is_capped_and_scrolls():
    m = SepalMap(gee=False, inspector=True, height="400px")
    m.inspector.inspection = inspection(InspectedLayer("a", "A", "ready", (("x", "1"),)))
    box, rc = render(m)
    (card,) = role_widgets(box, "inspector-card")
    assert "max-height: calc(var(--pysepal-map-height)" in card.style_
    assert "--pysepal-map-height: 400px" in box.children[0].style_
    (body,) = role_widgets(box, "inspector-body")
    assert "overflow-y: auto" in body.style_
    rc.close()


def test_two_views_share_the_inspector():
    m = SepalMap(gee=False, inspector=True)
    first, rc1 = render(m)
    second, rc2 = render(m)
    click(role_widgets(first, "inspector-toggle")[0])
    m.inspector.inspection = inspection(InspectedLayer("a", "Alpha", "ready", (("x", "1"),)))
    for box in (first, second):
        assert _attr(role_widgets(box, "inspector-toggle")[0], "data-active") == "true"
        assert "Alpha" in all_text(role_widgets(box, "inspector-card")[0])
    rc1.close()
    assert m.cursor == "crosshair" and m.inspector.active
    assert "Alpha" in all_text(role_widgets(second, "inspector-card")[0])
    rc2.close()
