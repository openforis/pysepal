"""A click reaches Python with the features under it; the readout and the marker follow."""

import json

from IPython.display import display

from pysepal_map import Controls, GeoJSONSource, Layer, MapState, MapWidget

SQUARE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "a"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-10, -10], [10, -10], [10, 10], [-10, 10], [-10, -10]]],
            },
        }
    ],
}


def show(page, widget, **state):
    layer = Layer("sq", GeoJSONSource(widget.add_payload(json.dumps(SQUARE).encode())))
    display(widget)
    widget.publish(MapState(layers=(layer,), **state))
    revision = widget.state["revision"]
    page.wait_for_function(
        "r => document.querySelector('.psm-map')?.dataset.psmRevision === String(r)", arg=revision
    )
    # The polygon is drawn once the map has rendered it.
    page.evaluate(
        "() => new Promise(r => { const m = document.querySelector('.psm-map').psmMap;"
        " m.once('idle', r); m.triggerRepaint(); })"
    )


def canvas_point(page, lng, lat):
    """The page position of a coordinate, once the map holds still."""
    el = page.locator(".psm-map").element_handle()
    el.evaluate("el => psmHarness.quiet(el)")
    x, y = el.evaluate(
        "(el, c) => { const p = el.psmMap.project(c); return [p.x, p.y]; }", [lng, lat]
    )
    box = el.bounding_box()
    x, y = box["x"] + x, box["y"] + y
    # Solara can briefly lay a progress spinner over the page as a test starts.
    page.wait_for_function(
        "([el, x, y]) => document.elementFromPoint(x, y)?.closest('.psm-map') === el",
        arg=[el, x, y],
    )
    return x, y


def wait_for(page, check, what, timeout_ms=10_000):
    for _ in range(timeout_ms // 20):
        if check():
            return
        page.wait_for_timeout(20)
    raise AssertionError(what)


def test_click_reaches_python_with_the_feature(harness, page_session):
    widget = MapWidget()
    seen = []
    widget.on_click(seen.append)
    show(page_session, widget)

    page_session.mouse.click(*canvas_point(page_session, 0, 0))
    wait_for(page_session, lambda: seen, "no click arrived")
    event = seen[0]
    assert [f.properties for f in event.features] == [{"name": "a"}]
    assert event.hits("sq") == ({"name": "a"},)
    assert event.settled is True
    assert abs(event.lng) < 1 and abs(event.lat) < 1

    page_session.mouse.click(*canvas_point(page_session, 40, 0))
    wait_for(page_session, lambda: len(seen) == 2, "no second click arrived")
    assert seen[1].features == ()


def test_cursor_marker_and_readout_follow_the_widget(harness, page_session):
    widget = MapWidget()
    show(page_session, widget, controls=Controls(coordinates=True))
    cursor = "document.querySelector('.psm-map canvas').style.cursor"
    widget.cursor = "crosshair"
    page_session.wait_for_function(f"() => {cursor} === 'crosshair'")
    widget.cursor = ""
    page_session.wait_for_function(f"() => {cursor} === ''")

    marker = ".psm-map .maplibregl-marker"
    widget.set_marker(5, 6, color="#ff0000")
    page_session.locator(marker).wait_for()
    widget.clear_marker()
    page_session.locator(marker).wait_for(state="detached")

    readout = page_session.locator(".psm-coordinates")
    page_session.mouse.move(*canvas_point(page_session, 0, 0))
    page_session.wait_for_function(
        "() => /^-?\\d+\\.\\d{5}, -?\\d+\\.\\d{5}$/.test("
        "document.querySelector('.psm-coordinates')?.textContent ?? '')"
    )
    assert readout.count() == 1
    page_session.mouse.move(-5, -5)
    page_session.wait_for_function(
        "() => document.querySelector('.psm-coordinates')?.textContent === ''"
    )
