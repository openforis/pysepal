"""A layer's interaction opens a popup on click and a tooltip on hover."""

import json
from dataclasses import replace

from IPython.display import display

from mapframe import GeoJSONSource, Interaction, Layer, MapState, MapWidget
from test_pointer import canvas_point

POINT = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "<b>alpha</b>", "kind": "tree"},
            "geometry": {"type": "Point", "coordinates": [0, 0]},
        }
    ],
}


def publish(page, widget, layer):
    widget.publish(MapState(layers=(layer,)))
    revision = widget.state["revision"]
    page.wait_for_function(
        "r => document.querySelector('.mapframe-map')?.dataset.mapframeRevision === String(r)",
        arg=revision,
    )
    page.evaluate(
        "() => new Promise(r => { const m = document.querySelector('.mapframe-map').mapframeMap;"
        " m.once('idle', r); m.triggerRepaint(); })"
    )


def test_click_opens_a_popup_and_hiding_the_layer_closes_it(harness, page_session):
    widget = MapWidget()
    digest = widget.add_payload(json.dumps(POINT).encode())
    layer = Layer("pts", GeoJSONSource(digest), interaction=Interaction(popup=("name",)))
    display(widget)
    publish(page_session, widget, layer)

    page_session.mouse.click(*canvas_point(page_session, 0, 0))
    popup = page_session.locator(".mapframe-popup")
    popup.wait_for()
    assert "<b>alpha</b>" in popup.inner_text()
    assert "kind" not in popup.inner_text()
    assert popup.locator("b").count() == 0

    publish(page_session, widget, replace(layer, visible=False))
    popup.wait_for(state="detached")


def test_popup_shows_labels(harness, page_session):
    widget = MapWidget()
    digest = widget.add_payload(json.dumps(POINT).encode())
    layer = Layer(
        "pts", GeoJSONSource(digest), interaction=Interaction(popup={"kind": "Kind of tree"})
    )
    display(widget)
    publish(page_session, widget, layer)

    page_session.mouse.click(*canvas_point(page_session, 0, 0))
    popup = page_session.locator(".mapframe-popup")
    popup.wait_for()
    assert popup.locator("th").inner_text() == "Kind of tree"
    assert popup.locator("td").inner_text() == "tree"


def test_hover_shows_a_tooltip_that_follows_the_pointer_off(harness, page_session):
    widget = MapWidget()
    digest = widget.add_payload(json.dumps(POINT).encode())
    layer = Layer("pts", GeoJSONSource(digest), interaction=Interaction(tooltip=("kind",)))
    display(widget)
    publish(page_session, widget, layer)

    page_session.mouse.move(*canvas_point(page_session, 0, 0))
    tooltip = page_session.locator(".mapframe-tooltip")
    tooltip.wait_for()
    assert tooltip.inner_text() == "tree"

    page_session.mouse.move(-5, -5)
    tooltip.wait_for(state="detached")
