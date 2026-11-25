"""Check in a real browser that each layer's status reaches Python."""

import json

import ipywidgets as widgets
from IPython.display import display

from pysepal_map import (
    GeoJSONSource,
    Layer,
    LayerStatus,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)


def view(page):
    return page.locator(".psm-map").first.element_handle()


def wait_revision(page, revision):
    page.wait_for_function(
        "r => document.querySelector('.psm-map')?.dataset.psmRevision === r",
        arg=str(revision),
    )


def wait_status(page, widget, check, timeout_ms=15_000):
    """Wait until ``check(widget.layer_status)`` holds; status comes over the comm."""
    for _ in range(timeout_ms // 20):
        if check(widget.layer_status):
            return
        page.wait_for_timeout(20)
    raise AssertionError(f"status never matched: {dict(widget.layer_status)}")


def is_(layer_id, status, instance):
    def check(statuses):
        current = statuses.get(layer_id)
        return current is not None and current.status == status and current.instance == instance

    return check


def browser_statuses(el):
    return el.evaluate(
        "async el => { await psmHarness.quiet(el);"
        " return psmHarness.statuses(el).map(s => [s.id, s.instance, s.status]); }"
    )


def point():
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [0, 0]},
    }
    return json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()


def test_a_tile_failing_beside_loaded_ones_leaves_the_layer_ready(tiles, page_session):
    """A transient failure MapLibre does not retry is no error of the layer."""
    widget = MapWidget()
    widget.publish(MapState())
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)

    el.evaluate("el => { psmHarness.gate(el).holding = true; }")
    tiles.fail_one("a")
    widget.publish(MapState(layers=(Layer("r", RasterSource((tiles.url("a"),))),)))
    assert browser_statuses(el) == [["r", 1, "ready"]]
    assert list(tiles.failed) == ["a"] and tiles.served
    held = el.evaluate("el => psmHarness.gate(el).held.map(r => r.status)")
    assert "error" not in held
    el.evaluate("el => psmHarness.gate(el).release()")
    wait_status(page_session, widget, is_("r", "ready", 1))


def test_a_load_whose_tiles_all_fail_reports_error_until_the_layer_is_replaced(tiles, page_session):
    widget = MapWidget()
    widget.publish(MapState())
    box = widgets.Box([widget])
    display(box)
    wait_revision(page_session, 1)
    el = view(page_session)

    # Hold the reports at their origin: Python counts the layer as loading.
    el.evaluate("el => { psmHarness.gate(el).holding = true; }")
    tiles.fail_all("a")
    widget.publish(MapState(layers=(Layer("r", RasterSource((tiles.url("a"),))),)))
    page_session.wait_for_function(
        "el => psmHarness.gate(el).held.some(r => r.status === 'error')", arg=el
    )
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 1)}
    el.evaluate("el => psmHarness.gate(el).release()")
    wait_status(page_session, widget, is_("r", "error", 1))
    assert "500" in widget.layer_status["r"].error

    # The map is idle; the failure still stands.
    assert browser_statuses(el) == [["r", 1, "error"]]
    assert not tiles.served
    assert widget.layer_status["r"].status == "error"

    widget.publish(MapState(layers=(Layer("r", RasterSource((tiles.url("b"),))),)))
    wait_status(page_session, widget, is_("r", "ready", 2))
    assert list(tiles.failed) == ["a"]
    assert browser_statuses(el) == [["r", 2, "ready"]]

    # An unmounted view takes its reports with it.
    box.children = ()
    wait_status(page_session, widget, lambda statuses: statuses == {})


def test_a_rejected_paint_reports_its_revision_and_recovers(harness, page_session):
    widget = MapWidget()
    source = GeoJSONSource(widget.add_payload(point()))

    def draw(color):
        paint = VectorPaint(stroke=color)
        widget.publish(MapState(layers=(Layer("pt", source, paint=paint),)))

    draw("#ff0000")
    display(widget)
    wait_revision(page_session, 1)
    wait_status(page_session, widget, is_("pt", "ready", 1))
    el = view(page_session)
    el.evaluate("el => { psmHarness.attach(el).failPaint = true; }")

    draw("#0000ff")
    wait_status(page_session, widget, is_("pt", "error", 1))
    assert widget.layer_status["pt"].error.startswith("forced failure: psm:pt:1:")

    el.evaluate("el => { psmHarness.attach(el).failPaint = false; }")
    draw("#00ff00")
    wait_revision(page_session, 3)
    wait_status(page_session, widget, is_("pt", "ready", 1))


def test_a_payload_that_is_not_json_reports_error(harness, page_session):
    widget = MapWidget()
    bad = Layer("bad", GeoJSONSource(widget.add_payload(b"\xff not json")))
    widget.publish(MapState(layers=(bad,)))
    display(widget)
    wait_status(page_session, widget, is_("bad", "error", 1))
    assert "not GeoJSON" in widget.layer_status["bad"].error


def test_a_pmtiles_layer_name_the_archive_lacks_reports_error(pmtiles, page_session):
    widget = MapWidget()
    layer = Layer("pm", PMTilesSource(pmtiles.url, "roads"), paint=VectorPaint())
    widget.publish(MapState(layers=(layer,)))
    display(widget)
    wait_status(page_session, widget, is_("pm", "error", 1))
    assert widget.layer_status["pm"].error == (
        'no layer "roads" in the PMTiles archive; it has points'
    )
