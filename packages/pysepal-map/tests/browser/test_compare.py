"""Check in a real browser that a compare view draws each side on its own map."""

import json
from dataclasses import replace

import ipywidgets as widgets
import pytest
from IPython.display import display
from pysepal_map import GeoJSONSource, Layer, MapState, MapWidget, VectorPaint

COMPARE_RIGHT = ".psm-map .psm-compare-right"


def collection(lng, lat):
    feature = {
        "type": "Feature",
        "properties": {"at": [lng, lat]},
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
    }
    return json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()


def sided_layers(widget, payloads, sides=(("l", "left"), ("r", "right"), ("b", "both"))):
    """One GeoJSON point layer per ``(id, side)``, each on its own payload."""
    layers = []
    for n, (layer_id, side) in enumerate(sides):
        data = collection(10 * n, 0)
        digest = widget.add_payload(data)
        payloads[digest] = data
        layers.append(Layer(layer_id, GeoJSONSource(digest), side=side, paint=VectorPaint()))
    return tuple(layers)


def drawn(snapshot):
    """The layer ids a map's owned style draws, sorted."""
    return sorted({layer["source"].split(":")[1] for layer in snapshot["layers"]})


def root(page, nth=0):
    page.wait_for_function("n => document.querySelectorAll('.psm-map')[n]?.psmMap", arg=nth)
    return page.locator(".psm-map").nth(nth).element_handle()


def wait_for(page, check, what, timeout_ms=15_000):
    """Wait until ``check()`` holds; reports come over the comm."""
    for _ in range(timeout_ms // 20):
        if check():
            return
        page.wait_for_timeout(20)
    raise AssertionError(what)


def is_(widget, layer_id, status):
    def check():
        current = widget.layer_status.get(layer_id)
        return current is not None and current.status == status

    return check


def cameras(el):
    """Each map's center and zoom, once the main map stopped moving."""
    return el.evaluate(
        """async el => {
            const main = el.psmMap;
            for (let i = 0; i < 250 && main.isMoving(); i++) {
                await new Promise((resolve) => setTimeout(resolve, 20));
            }
            const of = (map) => {
                const c = map.getCenter();
                return [c.lng, c.lat, map.getZoom()];
            };
            return [of(main), of(el.psmCompare.map)];
        }"""
    )


def middle(page, el):
    """The middle of a view, once nothing covers its main map there."""
    el.evaluate("el => psmHarness.quiet(el)")
    box = el.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.wait_for_function(
        "([el, x, y]) => document.elementFromPoint(x, y)?.closest('.psm-map') === el",
        arg=[el, x, y],
    )
    return x, y


def test_compare_draws_each_side(
    harness, page_session, wait_settled, owned_snapshot, expected_snapshot
):
    widget = MapWidget()
    payloads = {}
    layers = sided_layers(widget, payloads)
    widget.publish(MapState(layers=layers, compare=True))
    display(widget)
    wait_settled(page_session, 1)
    [main] = owned_snapshot(page_session)
    [right] = owned_snapshot(page_session, "right")
    assert drawn(main) == ["b", "l"]
    assert drawn(right) == ["b", "r"]
    assert main == expected_snapshot(widget.state, payloads)
    assert right == expected_snapshot(widget.state, payloads, "right")
    # Stacked right after the main canvas, under the markers and popups.
    assert root(page_session).evaluate(
        "el => el.psmMap.getCanvas().nextElementSibling === el.psmCompare.map.getContainer()"
    )

    widget.publish(MapState(layers=layers))
    wait_settled(page_session, 2)
    [main] = owned_snapshot(page_session)
    assert drawn(main) == ["b", "l", "r"]
    assert main == expected_snapshot(widget.state, payloads)
    assert owned_snapshot(page_session, "right") == [None]
    assert page_session.locator(COMPARE_RIGHT).count() == 0


def test_compare_status_counts_both_sides(harness, page_session, wait_settled):
    widget = MapWidget()
    layers = sided_layers(widget, {})
    widget.publish(MapState(layers=layers))
    display(widget)
    wait_settled(page_session, 1)
    wait_for(page_session, is_(widget, "b", "ready"), "b never got ready")
    view_id = root(page_session).evaluate("el => psmHarness.viewId(el)")
    snapshots = []
    widget.on_status(lambda status: snapshots.append(dict(status)))

    widget.publish(MapState(layers=layers, compare=True))
    wait_settled(page_session, 2)
    wait_for(
        page_session,
        lambda: all(s.status == "ready" for s in widget.layer_status.values()),
        f"the layers never got ready: {dict(widget.layer_status)}",
    )
    of_b = [snapshot["b"].status for snapshot in snapshots if "b" in snapshot]
    # The right view counts in as it opens, before it reports.
    assert "loading" in of_b
    assert of_b[-1] == "ready"
    assert (view_id, "right") in widget._views

    widget.publish(MapState(layers=layers))
    wait_settled(page_session, 3)
    wait_for(
        page_session,
        lambda: (view_id, "right") not in widget._views,
        "the right view never closed",
    )
    assert (view_id, "main") in widget._views
    assert widget.layer_status["b"].status == "ready"


def test_compare_on_pulls_nothing_new(harness, page_session, wait_settled):
    widget = MapWidget()
    layers = sided_layers(widget, {}, sides=(("l", "left"), ("b", "both")))
    digest = layers[1].source.digest
    widget.publish(MapState(layers=layers))
    display(widget)
    wait_settled(page_session, 1)
    pulls = []
    widget.on_msg(
        lambda _, content, __: pulls.append(content) if content.get("type") == "pull" else None
    )

    widget.publish(MapState(layers=layers, compare=True))
    wait_settled(page_session, 2)
    el = root(page_session)
    held = el.evaluate("el => psmHarness.inspect(el, 'right').payloads")
    assert held == [digest]
    assert [pull for pull in pulls if digest in pull["digests"]] == []


def test_right_map_follows_the_camera(harness, page_session, wait_settled):
    widget = MapWidget()
    widget.set_insets(left=120)
    widget.publish(MapState(compare=True))
    display(widget)
    wait_settled(page_session, 1)
    el = root(page_session)

    widget.set_center(30, 10, zoom=4)
    page_session.wait_for_function(
        "el => el.psmCamera.inspect().applied === 2 && !el.psmMap.isMoving()", arg=el
    )
    main, right = cameras(el)
    assert main == pytest.approx([30, 10, 4], abs=1e-6)
    assert right == pytest.approx(main, abs=1e-9)
    padding = el.evaluate("el => [el.psmMap.getPadding(), el.psmCompare.map.getPadding()]")
    assert padding[0] == padding[1] and padding[0]["left"] == 120

    x, y = middle(page_session, el)
    page_session.mouse.move(x, y)
    page_session.mouse.down()
    page_session.mouse.move(x - 150, y + 80, steps=10)
    page_session.mouse.up()
    page_session.wait_for_function("el => el.psmMap.getCenter().lng > 31", arg=el)
    main, right = cameras(el)
    assert main[0] > 31
    assert right == pytest.approx(main, abs=1e-9)


def test_redisplay_keeps_compare(
    harness, page_session, wait_settled, owned_snapshot, expected_snapshot
):
    widget = MapWidget()
    payloads = {}
    widget.publish(MapState(layers=sided_layers(widget, payloads), compare=True))
    box = widgets.VBox([widgets.VBox([widget])])
    display(box)
    wait_settled(page_session, 1)
    first = root(page_session).evaluate("el => psmHarness.viewId(el)")

    box.children = ()
    wait_for(page_session, lambda: not widget._views, f"views left: {widget._views}")
    box.children = (widgets.VBox([widget]),)
    wait_settled(page_session, 1)
    second = root(page_session).evaluate("el => psmHarness.viewId(el)")
    assert second != first
    [main] = owned_snapshot(page_session)
    [right] = owned_snapshot(page_session, "right")
    assert main == expected_snapshot(widget.state, payloads)
    assert right == expected_snapshot(widget.state, payloads, "right")
    wait_for(
        page_session,
        lambda: set(widget._views) == {(second, "main"), (second, "right")},
        f"views: {widget._views}",
    )


def test_right_error_wins(harness, page_session, wait_settled):
    widget = MapWidget()
    [b] = sided_layers(widget, {}, sides=(("b", "both"),))
    widget.publish(MapState(layers=(b,), compare=True))
    display(widget)
    wait_settled(page_session, 1)
    wait_for(page_session, is_(widget, "b", "ready"), "b never got ready")
    el = root(page_session)

    el.evaluate("el => { psmHarness.attach(el, 'right').failPaint = true; }")
    widget.publish(MapState(layers=(replace(b, opacity=0.5),), compare=True))
    wait_for(page_session, is_(widget, "b", "error"), "b never failed")
    assert widget.layer_status["b"].error.startswith("forced failure: psm:b:1:")
    assert widget.layer_status["b"].instance == 1
    assert {s["status"] for s in el.evaluate("el => psmHarness.statuses(el)")} == {"ready"}

    el.evaluate("el => { psmHarness.attach(el, 'right').failPaint = false; }")
    widget.publish(MapState(layers=(replace(b, opacity=0.8),), compare=True))
    wait_settled(page_session, 3)
    wait_for(page_session, is_(widget, "b", "ready"), "b never recovered")


def test_root_mark_survives_compare_off(harness, page_session, wait_settled):
    widget = MapWidget()
    seen = []
    widget.on_click(seen.append)
    # Both draw on the main map in and out of compare: it changes nothing there.
    layers = sided_layers(widget, {}, sides=(("l", "left"), ("b", "both")))
    widget.publish(MapState(layers=layers, compare=True))
    display(widget)
    wait_settled(page_session, 1)
    el = root(page_session)
    mutations = el.evaluate("el => psmHarness.attach(el).mutations")

    widget.publish(MapState(layers=layers))
    wait_settled(page_session, 2)
    page_session.locator(COMPARE_RIGHT).wait_for(state="detached")
    assert el.evaluate("el => psmHarness.attach(el).mutations") == mutations
    assert el.evaluate("el => el.dataset.psmRevision") == "2"

    page_session.mouse.click(*middle(page_session, el))
    wait_for(page_session, lambda: seen, "no click arrived")
    assert seen[0].settled is True
