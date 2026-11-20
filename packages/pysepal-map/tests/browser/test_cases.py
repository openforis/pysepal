"""Deterministic browser cases of what the views show and report."""

import io
import json
from dataclasses import replace

import ipywidgets as widgets
from IPython.display import display
from PIL import Image
from pysepal_map import (
    Basemap,
    GeoJSONSource,
    Layer,
    LayerStatus,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)

RED, BLUE = (255, 0, 0), (0, 0, 255)


def hex_color(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def solid(rgb):
    color = hex_color(rgb)
    return VectorPaint(stroke=color, fill=color, fill_opacity=1.0, point_radius=6)


def collection(*geometries):
    features = [
        {"type": "Feature", "properties": {}, "geometry": geometry} for geometry in geometries
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def point(lng, lat):
    return {"type": "Point", "coordinates": [lng, lat]}


def square(west, south, east, north):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def view(page, nth=0):
    return page.locator(".psm-map").nth(nth).element_handle()


def wait_status(page, widget, check, timeout_ms=15_000):
    """Wait until ``check(widget.layer_status)`` holds; status comes over the comm."""
    for _ in range(timeout_ms // 20):
        if check(widget.layer_status):
            return
        page.wait_for_timeout(20)
    raise AssertionError(f"status never matched: {dict(widget.layer_status)}")


def wait_messages(page, received, check, timeout_ms=15_000):
    """Wait until Python handled a message that ``check`` accepts."""
    for _ in range(timeout_ms // 20):
        if any(check(m) for m in received):
            return
        page.wait_for_timeout(20)
    raise AssertionError(f"no such message among {received}")


def close(rgb, expected, tolerance=8):
    return all(abs(a - b) <= tolerance for a, b in zip(rgb, expected))


def wait_color(page, el, lng_lat, rgb):
    """Wait for a rendered frame with ``rgb`` at ``lng_lat``."""
    page.wait_for_function(
        """async ([el, at, rgb]) => {
            const {x, y} = el.psmMap.project(at);
            const pixel = await psmHarness.pixel(el, x, y);
            return rgb.every((v, i) => Math.abs(pixel[i] - v) <= 8);
        }""",
        arg=[el, lng_lat, list(rgb)],
    )


def screen_color(page, el, lng_lat):
    """The colour a screenshot shows at ``lng_lat`` once the map is idle."""
    x, y = el.evaluate(
        "async (el, at) => { await psmHarness.quiet(el);"
        " const p = el.psmMap.project(at); return [p.x, p.y]; }",
        lng_lat,
    )
    box = el.bounding_box()
    clip = {"x": box["x"] + x - 1, "y": box["y"] + y - 1, "width": 3, "height": 3}
    image = Image.open(io.BytesIO(page.screenshot(clip=clip))).convert("RGB")
    return image.getpixel((1, 1))


# Rendered features of every owned circle layer within a few px of a place.
CIRCLES_AT = """async (el, at) => {
    await psmHarness.quiet(el);
    const circles = el.psmMap.getLayersOrder().filter(
        (id) => id.startsWith('psm:') && id.endsWith(':circle'));
    return psmHarness.featuresAt(el, at, circles);
}"""


def test_reorder_changes_top_pixel(harness, page_session, wait_settled):
    widget = MapWidget(center=(0, 0), zoom=3)

    def area(layer_id, bounds, rgb):
        source = GeoJSONSource(widget.add_payload(collection(square(*bounds))))
        return Layer(layer_id, source, paint=solid(rgb))

    red = area("red", (-20, -10, 10, 10), RED)
    blue = area("blue", (-10, -10, 20, 10), BLUE)
    overlap = [0, 0]
    frames = [
        ((red, blue), RED),
        ((blue, red), BLUE),
        ((replace(blue, visible=False), red), RED),
    ]
    display(widget)
    for revision, (layers, top) in enumerate(frames, start=1):
        widget.draw(MapState(layers=layers))
        wait_settled(page_session, revision)
        el = view(page_session)
        wait_color(page_session, el, overlap, top)
        assert close(screen_color(page_session, el, overlap), top), revision


def test_overwritten_payload_shows_new_coordinates(harness, page_session, wait_settled, tmp_path):
    a, b = [-10, 0], [10, 0]
    path = tmp_path / "point.geojson"
    widget = MapWidget(center=(0, 0), zoom=3)

    def publish():
        source = GeoJSONSource(widget.add_payload(path.read_bytes()))
        widget.draw(MapState(layers=(Layer("pt", source, token=7, paint=solid(RED)),)))
        return source.digest, widget.state["layers"][0]["instance"]

    path.write_bytes(collection(point(*a)))
    before = publish()
    display(widget)
    wait_settled(page_session, 1)
    el = view(page_session)
    assert [el.evaluate(CIRCLES_AT, at) for at in (a, b)] == [1, 0]

    path.write_bytes(collection(point(*b)))
    after = publish()
    wait_settled(page_session, 2)
    assert [el.evaluate(CIRCLES_AT, at) for at in (a, b)] == [0, 1]
    assert after[0] != before[0] and after[1] != before[1]
    assert el.evaluate(
        "(el, ids) => ids.map((id) => !!el.psmMap.getSource(id))",
        [f"psm:pt:{before[1]}", f"psm:pt:{after[1]}"],
    ) == [False, True]


def test_reorder_while_drawing_polygon(harness, page_session, wait_settled):
    widget = MapWidget(center=(0, 0), zoom=3)
    south = GeoJSONSource(widget.add_payload(collection(square(-40, -20, -30, -10))))
    north = GeoJSONSource(widget.add_payload(collection(square(30, 10, 40, 20))))
    south, north = Layer("south", south), Layer("north", north)
    widget.draw(MapState(layers=(south, north)))
    display(widget)
    wait_settled(page_session, 1)
    el = view(page_session)
    el.evaluate("el => psmHarness.startDrawing(el)")
    order = el.evaluate("el => el.psmMap.getLayersOrder()")
    foreign = [id for id in order if not id.startswith("psm:")]
    assert foreign and order[-len(foreign) :] == foreign

    box = el.bounding_box()
    width = box["width"]
    # Whole pixels, as the pointer events carry them.
    clicks = [
        (round(0.3 * width), 120),
        (round(0.55 * width), 100),
        (round(0.45 * width), 280),
    ]

    def vertex(at):
        return el.evaluate("(el, at) => el.psmMap.unproject(at).toArray()", list(at))

    def click(at, committed):
        x, y = box["x"] + at[0], box["y"] + at[1]
        # Solara can briefly lay a progress spinner over the page.
        page_session.wait_for_function(
            "([el, x, y]) => document.elementFromPoint(x, y) === el.psmMap.getCanvas()",
            arg=[el, x, y],
        )
        page_session.mouse.click(x, y)
        page_session.wait_for_function(
            "([el, n]) => psmHarness.drawnPolygons(el)[0]"
            "?.properties.committedCoordinateCount === n",
            arg=[el, committed],
        )

    vertices = [vertex(at) for at in clicks]
    click(clicks[0], 1)
    click(clicks[1], 2)
    started = el.evaluate("el => psmHarness.drawnPolygons(el)[0].geometry.coordinates[0]")

    widget.draw(MapState(layers=(north, south)))
    wait_settled(page_session, 2)
    click(clicks[2], 3)
    # A click on the first vertex closes the polygon.
    page_session.mouse.click(box["x"] + clicks[0][0], box["y"] + clicks[0][1])
    page_session.wait_for_function(
        "el => psmHarness.drawnPolygons(el).length === 1"
        " && !psmHarness.drawnPolygons(el)[0].properties.currentlyDrawing",
        arg=el,
    )
    [polygon] = el.evaluate("el => psmHarness.drawnPolygons(el)")
    ring = polygon["geometry"]["coordinates"][0]
    assert len(ring) == 4 and ring[0] == ring[-1]
    # Terra Draw may wind the finished ring either way.
    corners = ring[:3]
    assert started[0] in corners and started[1] in corners
    for want in vertices:
        assert any(all(abs(g - w) < 1e-6 for g, w in zip(got, want)) for got in corners)

    order = el.evaluate("el => el.psmMap.getLayersOrder()")
    assert [id for id in order if not id.startswith("psm:")] == foreign
    assert order[-len(foreign) :] == foreign
    assert [id for id in order if id.startswith("psm:")] == [
        "psm:south:1:fill",
        "psm:south:1:line",
        "psm:south:1:circle",
        "psm:north:2:fill",
        "psm:north:2:line",
        "psm:north:2:circle",
    ]


class SidedWidget(MapWidget):
    """A widget that draws the layer ``cmp`` on both sides of a compare view."""

    def _sides_of(self, layer_id):
        return ("left", "right") if layer_id == "cmp" else ("main",)


def test_late_status_and_side_aggregation(harness, page_session, wait_settled):
    widget = SidedWidget()
    received = []
    widget.on_msg(lambda _, content, __: received.append(content))
    widget.draw(MapState())
    display(widget)
    wait_settled(page_session, 1)
    el = view(page_session)
    data = collection(point(0, 0))
    pt = Layer("pt", GeoJSONSource(widget.add_payload(data)))

    # Hold every report on the first instance of pt until its source is ready.
    el.evaluate(
        "el => { const gate = psmHarness.gate(el);"
        " gate.only = (m) => m.id === 'pt' && m.instance === 1;"
        " gate.holding = true; }"
    )
    widget.draw(MapState(layers=(pt,)))
    page_session.wait_for_function(
        "el => psmHarness.gate(el).held.some((m) => m.status === 'ready')", arg=el
    )
    assert widget.layer_status == {"pt": LayerStatus("loading", None, 0, 1)}

    # Removed, with its bytes, then added again under the same default token.
    widget.draw(MapState())
    widget.add_payload(data)
    widget.draw(MapState(layers=(pt,)))
    assert widget.state["layers"][0]["instance"] == 2
    wait_status(page_session, widget, lambda s: s.get("pt") == LayerStatus("ready", None, 0, 2))

    held = el.evaluate("el => psmHarness.gate(el).held.map((m) => m.status)")
    assert held[0] == "loading"
    received.clear()
    el.evaluate("el => psmHarness.gate(el).release()")
    wait_messages(
        page_session,
        received,
        lambda m: m.get("instance") == 1 and m.get("status") == "ready",
    )
    assert widget.layer_status == {"pt": LayerStatus("ready", None, 0, 2)}

    # cmp draws on a left and a right view, registered as the browser would.
    cmp = Layer("cmp", GeoJSONSource(widget.add_payload(collection(point(5, 5)))))
    widget.draw(MapState(layers=(pt, cmp)))
    instance = widget.state["layers"][1]["instance"]

    def post(message):
        el.evaluate("(el, message) => psmHarness.post(el, message)", message)

    def status(view_id, side, value, error=None):
        post(
            {
                "type": "status",
                "view_id": view_id,
                "side": side,
                "id": "cmp",
                "token": 0,
                "instance": instance,
                "status": value,
                "error": error,
            }
        )

    def handled(kind, view_id):
        wait_messages(
            page_session,
            received,
            lambda m: m.get("type") == kind and m.get("view_id") == view_id,
        )

    received.clear()
    for view_id, side in (("test-left", "left"), ("test-right", "right")):
        post({"type": "view_open", "view_id": view_id, "side": side})
    handled("view_open", "test-right")
    assert widget.layer_status["cmp"] == LayerStatus("loading", None, 0, instance)

    status("test-left", "left", "error", "left failed")
    status("test-right", "right", "ready")
    handled("status", "test-right")
    assert widget.layer_status["cmp"] == LayerStatus("error", "left failed", 0, instance)
    assert widget.layer_status["pt"] == LayerStatus("ready", None, 0, 2)

    post({"type": "view_close", "view_id": "test-left", "side": "left"})
    wait_status(
        page_session,
        widget,
        lambda s: s.get("cmp") == LayerStatus("ready", None, 0, instance),
    )


def test_two_views_converge(tiles, page_session, wait_settled, owned_snapshot, expected_snapshot):
    widget = MapWidget()
    payloads = {}

    def geojson(layer_id, data, rgb):
        digest = widget.add_payload(data)
        payloads[digest] = data
        return Layer(layer_id, GeoJSONSource(digest), paint=solid(rgb))

    basemap = Basemap((tiles.url("base"),), "© Test base")
    points = geojson("points", collection(point(0, 0), point(10, 5)), RED)
    area = geojson("area", collection(square(-10, -10, 0, 0)), BLUE)
    raster = Layer("raster", RasterSource((tiles.url("r"),)), opacity=0.5)
    widget.draw(MapState(layers=(points, area, raster), basemap=basemap))
    first, second = widgets.VBox([widget]), widgets.VBox([widget])
    display(widgets.VBox([first, second]))
    wait_settled(page_session, 1, expected_views=2)
    one, two = owned_snapshot(page_session)
    assert one == two == expected_snapshot(widget.state, payloads)

    first.children = ()
    moved = geojson("points", collection(point(-5, 5)), RED)
    widget.draw(MapState(layers=(raster, replace(area, zone="overlay"), moved), theme="dark"))
    wait_settled(page_session, 2, expected_views=1)
    [survivor] = owned_snapshot(page_session)
    assert survivor == expected_snapshot(widget.state, payloads)
    assert survivor["theme"] == "dark"


def test_large_payload_travels_as_a_buffer(harness, page_session, wait_settled, monkeypatch):
    widget = MapWidget()
    count = 50_000
    payload = collection(*(point(-180 + i * 0.0072, (i % 170) - 85) for i in range(count)))
    replies = []
    send = widget.send

    def record(content, buffers=None):
        if content.get("type") == "data":
            replies.append((content, buffers))
        send(content, buffers)

    monkeypatch.setattr(widget, "send", record)
    widget.draw(MapState(layers=(Layer("many", GeoJSONSource(widget.add_payload(payload))),)))
    assert len(json.dumps(widget.state)) < 10_000
    display(widget)
    wait_settled(page_session, 1)

    assert replies
    for content, buffers in replies:
        assert len(buffers) == 1 and bytes(buffers[0]) == payload
        message = json.dumps(content)
        assert "coordinates" not in message and len(message) < 200
    features = view(page_session).evaluate(
        "async el => (await el.psmMap.getSource('psm:many:1').getData()).features.length"
    )
    assert features == count


def test_raster_overzooms_at_map_limit(tiles, page_session, wait_settled):
    color = (200, 40, 160)
    tiles.color("solid", color)
    widget = MapWidget(center=(10, 10), zoom=24)
    source = RasterSource((tiles.url("solid"),), max_native_zoom=20)
    widget.draw(MapState(layers=(Layer("r", source, attribution="© Solid tiles"),)))
    display(widget)
    wait_settled(page_session, 1)
    el = view(page_session)
    assert el.evaluate("el => el.psmMap.getZoom()") == 24

    wait_color(page_session, el, [10, 10], color)
    attribution = page_session.locator(".psm-map .maplibregl-ctrl-attrib-inner")
    assert "© Solid tiles" in attribution.inner_text()
    assert attribution.is_visible()
    zooms = tiles.zooms("solid")
    assert zooms and max(zooms) == 20


def test_pmtiles_layer_draws(pmtiles, page_session, wait_settled):
    widget = MapWidget()
    paint = VectorPaint(stroke="#ff00ff", fill="#ff00ff", fill_opacity=1.0, point_radius=6)
    layer = Layer("pm", PMTilesSource(pmtiles.url, "points"), paint=paint)
    widget.draw(MapState(layers=(layer,)))
    widget.fit_bounds(pmtiles.bounds, padding=40)
    display(widget)
    wait_settled(page_session, 1)
    el = view(page_session)
    page_session.wait_for_function(
        "el => el.psmCamera.inspect().applied === 2 && el.psmMap.isSourceLoaded('psm:pm:1')",
        arg=el,
    )
    # Over the whole canvas, in screen pixels; a point on a tile boundary is
    # rendered by each tile it touches, so compare the ids, not a count.
    ids = el.evaluate(
        """async el => {
            await psmHarness.quiet(el);
            const map = el.psmMap;
            const canvas = map.getCanvas();
            const box = [[0, 0], [canvas.clientWidth, canvas.clientHeight]];
            return map.queryRenderedFeatures(box, {layers: ['psm:pm:1:circle']})
                .map((feature) => feature.id);
        }"""
    )
    assert set(ids) == set(pmtiles.points)
    # Each point is drawn where the fixture puts it.
    for feature_id, lng_lat in pmtiles.points.items():
        hits = el.evaluate(
            """(el, at) => {
                const {x, y} = el.psmMap.project(at);
                const box = [[x - 4, y - 4], [x + 4, y + 4]];
                return el.psmMap.queryRenderedFeatures(box, {layers: ['psm:pm:1:circle']})
                    .map((feature) => feature.id);
            }""",
            list(lng_lat),
        )
        assert set(hits) == {feature_id}
    assert pmtiles.ranges
