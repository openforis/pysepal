"""The inspector toggle and the inspector card of MapView."""

import pytest
import solara

from pysepal.mapping import SepalMap
from pysepal.mapping.inspector import InspectedLayer, Inspection
from pysepal.solara.components import map_view
from pysepal.solara.components.map_view import MapView
from tests.test_solara._layer_panel_helpers import _attr, all_text, click, role_widgets


def render(m):
    return solara.render(MapView(m), handle_error=False)


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


@pytest.mark.parametrize("height", ["400px", "100%"])
def test_card_height_is_capped_and_scrolls(height):
    m = SepalMap(gee=False, inspector=True, height=height)
    m.inspector.inspection = inspection(InspectedLayer("a", "A", "ready", (("x", "1"),)))
    box, rc = render(m)
    (card,) = role_widgets(box, "inspector-card")
    # the cap is the corner's, which resolves against the map root whatever its height
    assert "max-height" not in card.style_ and "min-height: 0" in card.style_
    assert "max-height: calc(" in map_view.CSS and "100% - var(--pysepal-inset-top)" in map_view.CSS
    (body,) = role_widgets(box, "inspector-body")
    assert "overflow-y: auto" in body.style_ and "min-height: 0" in body.style_
    rc.close()


@pytest.mark.parametrize("error", ["", None])
def test_error_without_text_shows_a_fallback(error):
    m = SepalMap(gee=False, inspector=True)
    m.inspector.inspection = inspection(InspectedLayer("a", "A", "error", error=error))
    box, rc = render(m)
    assert "could not be read" in all_text(role_widgets(box, "inspector-card")[0])
    rc.close()


def test_idle_inspector_slot_is_not_made_visible_by_its_flex_rule():
    m = SepalMap(gee=False)
    box, rc = render(m)
    assert _attr(role_widgets(box, "map-inspector")[0], "data-idle") is not None
    rules = [r for r in map_view.CSS.split("}") if "display: flex" in r and "map-inspector" in r]
    assert rules and all(":not([data-idle])" in r for r in rules)
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


@pytest.mark.parametrize(
    ("scale", "text"),
    [(0.29, "0.29 m"), (1.23, "1.2 m"), (38.4, "38 m"), (99.9, "100 m"), (1234.0, "1,234 m")],
)
def test_card_scale_keeps_two_significant_digits(scale, text):
    m = SepalMap(gee=False, inspector=True)
    box, rc = render(m)
    m.inspector.inspection = Inspection(-1.5, 2.1, scale, (), False)
    assert text in all_text(role_widgets(box, "inspector-card")[0])
    rc.close()
