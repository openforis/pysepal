"""Render the widget in a real browser and check what each view shows."""

import base64
import json
import struct
import zlib
from urllib.parse import urlsplit

import ipywidgets as widgets
from IPython.display import display

from mapframe import (
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    RasterSource,
    VectorPaint,
)

LOCAL = ("127.0.0.1", "localhost", "::1")


def wait_async(page, script, arg, what, timeout_ms=15_000):
    """Poll an async ``script``: Playwright's ``wait_for_function`` does not await a promise."""
    for _ in range(timeout_ms // 50):
        if page.evaluate(script, arg):
            return
        page.wait_for_timeout(50)
    raise AssertionError(what)


def is_external(url):
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and parts.hostname not in LOCAL


def points(*coordinates):
    features = [
        {
            "type": "Feature",
            "properties": {},
            "geometry": {"type": "Point", "coordinates": list(xy)},
        }
        for xy in coordinates
    ]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def solid_tile(rgb, size=256):
    """A data URL of a one-colour PNG, so raster tests stay offline."""

    def chunk(kind, body):
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


RED_TILE = solid_tile((255, 0, 0))


def view(page, nth=0):
    return page.locator(".mapframe-map").nth(nth).element_handle()


def wait_revision(page, revision, nth=0):
    page.wait_for_function(
        "([n, r]) => document.querySelectorAll('.mapframe-map')[n]?.dataset.mapframeRevision"
        " === r",
        arg=[nth, str(revision)],
    )


def revision_of(el):
    return el.evaluate("el => el.dataset.mapframeRevision ?? null")


def wait_feature(page, el, lng_lat, layers):
    page.wait_for_function(
        "([el, at, layers]) => mapframeHarness.featuresAt(el, at, layers) > 0",
        arg=[el, lng_lat, layers],
    )


def features_at(el, lng_lat, layers):
    return el.evaluate(
        "async (el, [at, layers]) => { await mapframeHarness.quiet(el);"
        " return mapframeHarness.featuresAt(el, at, layers); }",
        [lng_lat, layers],
    )


def test_map_canvas_appears(solara_test, page_session):
    display(MapWidget(height="300px"))
    page_session.locator(".mapframe-map canvas.maplibregl-canvas").wait_for()
    assert page_session.locator(".mapframe-map").bounding_box()["height"] == 300


def test_no_request_leaves_the_machine(solara_test, page_session):
    urls = []
    page_session.on("request", lambda r: urls.append(r.url))
    display(MapWidget())
    page_session.locator(".mapframe-map canvas.maplibregl-canvas").wait_for()
    assert [u for u in urls if is_external(u)] == []


def test_map_fills_a_box_that_grows(solara_test, page_session):
    box = widgets.Box([MapWidget(height="100%")], layout=widgets.Layout(height="0px"))
    display(box)
    page_session.locator(".mapframe-map").wait_for(state="attached")
    box.layout.height = "250px"
    page_session.wait_for_function(
        "document.querySelector('.mapframe-map canvas')?.clientHeight === 250"
    )


def test_geojson_layer_draws_its_features(solara_test, page_session):
    widget = MapWidget()
    payload = points([10, 5])
    source = GeoJSONSource(widget.add_payload(payload))
    widget.publish(MapState(layers=(Layer("v1", source),)))
    display(widget)
    wait_revision(page_session, 1)
    features = view(page_session).evaluate(
        "async el => (await el.mapframeMap.getSource('mapframe:v1:1').getData()).features"
    )
    assert features == json.loads(payload)["features"]


def test_bundled_worker_renders_offline(harness, page_session):
    attempts = []

    def guard(route):
        if is_external(route.request.url):
            attempts.append(route.request.url)
            route.abort()
        else:
            route.continue_()

    page_session.context.route("**/*", guard)
    try:
        widget = MapWidget()
        source = GeoJSONSource(widget.add_payload(points([0, 0])))
        widget.publish(MapState(layers=(Layer("pt", source),)))
        display(widget)
        wait_revision(page_session, 1)
        wait_feature(page_session, view(page_session), [0, 0], ["mapframe:pt:1:circle"])
    finally:
        page_session.context.unroute("**/*", guard)
    assert attempts == []


def test_state_drawn_before_display_shows(solara_test, page_session):
    widget = MapWidget()
    for x, color in enumerate(("#ff0000", "#00ff00", "#0000ff")):
        source = GeoJSONSource(widget.add_payload(points([x, 0])))
        paint = VectorPaint(stroke=color)
        widget.publish(MapState(layers=(Layer("pt", source, paint=paint),)))
    display(widget)
    wait_revision(page_session, 3)
    style = view(page_session).evaluate("""async el => {
            const map = el.mapframeMap;
            const data = await map.getSource('mapframe:pt:3').getData();
            return {
                sources: Object.keys(map.getStyle().sources),
                layers: map.getLayersOrder(),
                stroke: map.getPaintProperty('mapframe:pt:3:circle', 'circle-stroke-color'),
                coordinates: data.features[0].geometry.coordinates,
            };
        }""")
    assert style == {
        "sources": ["mapframe:pt:3"],
        "layers": ["mapframe:pt:3:fill", "mapframe:pt:3:line", "mapframe:pt:3:circle"],
        "stroke": "#0000ff",
        "coordinates": [2, 0],
    }


def test_a_held_geojson_completion_holds_only_the_marker(harness, page_session):
    widget = MapWidget()
    widget.publish(MapState())
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)
    el.evaluate("el => { mapframeHarness.attach(el).holding = true; }")

    point = Layer("pt", GeoJSONSource(widget.add_payload(points([0, 0]))))
    widget.publish(MapState(layers=(point, Layer("r", RasterSource((RED_TILE,))))))
    page_session.wait_for_function("el => mapframeHarness.attach(el).held", arg=el)
    wait_async(
        page_session,
        "async el => { const [r, g, b] = await mapframeHarness.pixel(el, 20, 20);"
        " return r > 200 && g < 60 && b < 60; }",
        el,
        "the raster never showed under the held marker",
    )
    assert revision_of(el) is None

    el.evaluate("el => mapframeHarness.attach(el).release()")
    wait_revision(page_session, 2)
    wait_feature(page_session, el, [0, 0], ["mapframe:pt:1:circle"])


def test_a_rejected_paint_change_waits_for_the_next_revision(harness, page_session):
    widget = MapWidget()
    source = GeoJSONSource(widget.add_payload(points([0, 0])))

    def draw(color):
        paint = VectorPaint(stroke=color)
        widget.publish(MapState(layers=(Layer("pt", source, paint=paint),)))

    draw("#ff0000")
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)
    el.evaluate("el => { mapframeHarness.attach(el).failPaint = true; }")

    draw("#0000ff")
    page_session.wait_for_function("el => mapframeHarness.attach(el).forcedFailures > 0", arg=el)
    failed = el.evaluate("""async el => {
            await mapframeHarness.quiet(el);
            const failures = mapframeHarness.attach(el).forcedFailures;
            el.mapframeMap.addLayer(
                {id: 'foreign', type: 'background', paint: {'background-opacity': 0}}
            );
            await mapframeHarness.quiet(el);
            return {
                revision: el.dataset.mapframeRevision ?? null,
                rejected: mapframeHarness.inspect(el).rejections.map(
                    (r) => [r.layer, r.revision]
                ),
                retried: mapframeHarness.attach(el).forcedFailures - failures,
            };
        }""")
    assert failed["revision"] is None
    assert {tuple(r) for r in failed["rejected"]} == {("pt", 2)}
    assert failed["retried"] == 0

    el.evaluate("el => { mapframeHarness.attach(el).failPaint = false; }")
    draw("#00ff00")
    wait_revision(page_session, 3)
    assert el.evaluate(
        "el => [el.mapframeMap.getPaintProperty('mapframe:pt:1:circle', 'circle-stroke-color'),"
        " mapframeHarness.inspect(el).rejections.length]"
    ) == ["#00ff00", 0]


def test_an_externally_displaced_owned_layer_is_repaired(harness, page_session):
    widget = MapWidget()
    point = Layer("pt", GeoJSONSource(widget.add_payload(points([0, 0]))))
    widget.publish(MapState(layers=(point, Layer("r", RasterSource((RED_TILE,))))))
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)
    el.evaluate("""async el => {
            const map = el.mapframeMap;
            map.addLayer(
                {id: 'foreign', type: 'background', paint: {'background-opacity': 0}}
            );
            await mapframeHarness.quiet(el);
            mapframeHarness.attach(el);
            map.moveLayer('foreign', 'mapframe:pt:1:circle');
        }""")
    page_session.wait_for_function(
        "el => el.mapframeMap.getLayersOrder().at(-1) === 'foreign'", arg=el
    )
    counts = el.evaluate("""async el => {
            await mapframeHarness.quiet(el);
            const first = mapframeHarness.attach(el).mutations;
            await mapframeHarness.quiet(el, 20);
            return [first, mapframeHarness.attach(el).mutations];
        }""")
    assert counts[0] > 0 and counts[1] == counts[0]
    assert el.evaluate("el => el.mapframeMap.getLayersOrder()") == [
        "mapframe:r:2:raster",
        "mapframe:pt:1:fill",
        "mapframe:pt:1:line",
        "mapframe:pt:1:circle",
        "foreign",
    ]
    wait_revision(page_session, 1)


def test_a_diffed_style_switch_beside_a_custom_layer_is_rebuilt(harness, page_session):
    widget = MapWidget()
    point = Layer("pt", GeoJSONSource(widget.add_payload(points([0, 0]))))
    widget.publish(MapState(layers=(point,)))
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)
    # A basemap switch that carries the current sources and layers over keeps
    # the owned GeoJSON source; the custom layer survives the diff because
    # MapLibre cannot serialize it.
    el.evaluate("""el => {
            const map = el.mapframeMap;
            map.addLayer({id: 'custom', type: 'custom', render() {}});
            window.mapframeOldSource = map.getSource('mapframe:pt:1');
            const background = {
                id: 'bg', type: 'background', paint: {'background-opacity': 0}
            };
            map.setStyle({version: 8, sources: {}, layers: [background]}, {
                transformStyle: (previous, next) => ({
                    ...next,
                    sources: {...previous.sources, ...next.sources},
                    layers: [...previous.layers, ...next.layers],
                }),
            });
        }""")
    wait_revision(page_session, 1)
    after = el.evaluate("""el => ({
            fresh: el.mapframeMap.getSource('mapframe:pt:1') !== window.mapframeOldSource,
            layers: el.mapframeMap.getLayersOrder(),
            rejections: mapframeHarness.inspect(el).rejections,
        })""")
    assert after == {
        "fresh": True,
        "layers": [
            "mapframe:pt:1:fill",
            "mapframe:pt:1:line",
            "mapframe:pt:1:circle",
            "custom",
            "bg",
        ],
        "rejections": [],
    }
    wait_feature(page_session, el, [0, 0], ["mapframe:pt:1:circle"])


def test_a_stale_worker_completion_is_ignored(harness, page_session):
    widget = MapWidget()
    widget.publish(MapState())
    display(widget)
    wait_revision(page_session, 1)
    el = view(page_session)
    el.evaluate("el => { mapframeHarness.attach(el).holding = true; }")

    a = GeoJSONSource(widget.add_payload(points([-20, 0])))
    widget.publish(MapState(layers=(Layer("pt", a),)))
    page_session.wait_for_function("el => mapframeHarness.attach(el).held", arg=el)
    b = GeoJSONSource(widget.add_payload(points([20, 0])))
    widget.publish(MapState(layers=(Layer("pt", b),)))
    wait_revision(page_session, 3)

    el.evaluate("async el => { mapframeHarness.attach(el).release(); }")
    assert features_at(el, [20, 0], ["mapframe:pt:2:circle"]) > 0
    assert revision_of(el) == "3"
    held = el.evaluate("el => mapframeHarness.inspect(el)")
    assert held["payloads"] == [b.digest]
    assert held["sources"] == ["mapframe:pt:2"]


def test_a_view_outlives_late_replies_its_sibling_and_a_style_reset(
    harness, page_session, monkeypatch
):
    widget = MapWidget()
    a = widget.add_payload(points([-20, 0]))
    send = widget.send
    withheld = []

    def withhold_a(content, buffers=None):
        if content.get("digest") == a:
            withheld.append((content, buffers))
        else:
            send(content, buffers)

    monkeypatch.setattr(widget, "send", withhold_a)
    widget.publish(MapState(layers=(Layer("pt", GeoJSONSource(a)),)))
    first, second = widgets.Box([widget]), widgets.Box([widget])
    display(widgets.VBox([first, second]))
    for _ in range(500):
        if withheld:
            break
        page_session.wait_for_timeout(20)
    assert withheld

    b = GeoJSONSource(widget.add_payload(points([20, 0])))
    widget.publish(MapState(layers=(Layer("pt", b),)))
    wait_revision(page_session, 2, nth=0)
    wait_revision(page_session, 2, nth=1)
    gone, kept = view(page_session, 0), view(page_session, 1)

    # A's bytes reach both views after B settled, then one view unmounts.
    # Messages arrive in order, so the reply was handled once the box empties.
    send(*withheld[0])
    first.children = ()
    page_session.wait_for_function("() => document.querySelectorAll('.mapframe-map').length === 1")
    assert gone.evaluate("el => el.mapframeMap === undefined && !el.mapframeInspect")
    assert revision_of(kept) == "2"
    assert features_at(kept, [20, 0], ["mapframe:pt:2:circle"]) > 0
    held = kept.evaluate("el => mapframeHarness.inspect(el)")
    assert held["payloads"] == [b.digest]
    assert held["sources"] == ["mapframe:pt:2"]

    # The survivor still pulls what it lacks.
    c = GeoJSONSource(widget.add_payload(points([30, 0])))
    widget.publish(MapState(layers=(Layer("pt", c),)))
    wait_revision(page_session, 3)
    assert kept.evaluate("el => mapframeHarness.inspect(el).payloads") == [c.digest]

    # A replaced style is rebuilt from the cached payload.
    for diff in ("false", "true"):
        cleared = kept.evaluate(f"""el => {{
                const map = el.mapframeMap;
                window.mapframeOldSource = map.getSource('mapframe:pt:3');
                map.setStyle({{version: 8, sources: {{}}, layers: []}}, {{diff: {diff}}});
                return el.dataset.mapframeRevision ?? null;
            }}""")
        assert cleared is None
        wait_revision(page_session, 3)
        rebuilt = kept.evaluate("""async el => {
                const source = el.mapframeMap.getSource('mapframe:pt:3');
                const data = await source.getData();
                return [source !== window.mapframeOldSource, data.features[0].geometry];
            }""")
        assert rebuilt == [True, {"type": "Point", "coordinates": [30, 0]}]
        wait_feature(page_session, kept, [30, 0], ["mapframe:pt:3:circle"])
