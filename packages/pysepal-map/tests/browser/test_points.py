"""Pin markers and point clusters render, tint, expand on a click and yield to the camera."""

import json
from dataclasses import replace

from IPython.display import display
from pysepal_map import (
    Basemap,
    Cluster,
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    VectorPaint,
)
from test_pointer import canvas_point, wait_for

ROOT = "document.querySelector('.psm-map')"
BLUE = (51, 136, 255)
RED = (255, 0, 0)


def points(coords):
    return json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {"n": i},
                    "geometry": {"type": "Point", "coordinates": list(c)},
                }
                for i, c in enumerate(coords)
            ],
        }
    ).encode()


# 200 points in a box of about 0.4 degrees.
BOX = [(-0.2 + 0.02 * i, -0.1 + 0.02 * j) for i in range(20) for j in range(10)]


def layer_of(widget, coords, cluster=Cluster(max_zoom=14), **kw):
    digest = widget.add_payload(points(coords))
    return Layer("pts", GeoJSONSource(digest, cluster=cluster), **kw)


def idle(page):
    """Wait for the next idle, once the map has had a repaint to place its symbols in."""
    page.evaluate(
        f"() => new Promise(r => {{ const m = {ROOT}.psmMap; m.once('idle', r); m.triggerRepaint(); }})"
    )


def publish(page, widget, *layers, **state):
    widget.publish(MapState(layers=layers, **state))
    revision = widget.state["revision"]
    page.wait_for_function(
        f"r => {ROOT}?.dataset.psmRevision === String(r)",
        arg=revision,
    )
    idle(page)


def show(page, widget, *layers, **state):
    display(widget)
    publish(page, widget, *layers, **state)


def style_id(widget, part):
    layer = widget.state["layers"][0]
    return f"psm:{layer['id']}:{layer['instance']}:{part}"


def features(page, widget, part):
    """The rendered features of a part, once per id, with their screen position."""
    return page.evaluate(
        f"""(id) => {{
            const map = {ROOT}.psmMap;
            if (!map.getLayer(id)) return [];
            const seen = new Map();
            for (const f of map.queryRenderedFeatures({{ layers: [id] }})) {{
                if (seen.has(f.id)) continue;
                const [lng, lat] = f.geometry.coordinates;
                const p = map.project([lng, lat]);
                seen.set(f.id, {{ lng, lat, x: p.x, y: p.y, props: f.properties }});
            }}
            return [...seen.values()];
        }}""",
        style_id(widget, part),
    )


def pixel(page, x, y):
    return page.evaluate(f"([x, y]) => psmHarness.pixel({ROOT}, x, y)", [x, y])


def near(rgba, rgb, tolerance=30):
    return all(abs(a - b) <= tolerance for a, b in zip(rgba[:3], rgb)) and rgba[3] > 200


def inside(page, bubble):
    """A pixel in a bubble clear of its ring and its label."""
    return pixel(page, bubble["x"], bubble["y"] - 7)


def clustered_view(page, widget, **kw):
    widget.set_center(0, 0, zoom=9)
    show(page, widget, layer_of(widget, BOX, **kw))
    return widget.state["layers"][0]


def wait_view_zoom(page, widget, check, what):
    wait_for(page, lambda: widget.view and check(widget.view["zoom"]), what)


def test_clusters_render_and_expand(harness, page_session):
    widget = MapWidget()
    received = []
    widget.on_msg(lambda _, content, buffers: received.append(content))
    clustered_view(page_session, widget)

    bubbles = features(page_session, widget, "cluster")
    assert bubbles
    assert near(inside(page_session, bubbles[0]), BLUE)
    assert features(page_session, widget, "circle") == []

    wait_for(page_session, lambda: widget.view, "no view report")
    zoom = widget.view["zoom"]
    received.clear()
    page_session.mouse.click(*canvas_point(page_session, bubbles[0]["lng"], bubbles[0]["lat"]))
    wait_view_zoom(page_session, widget, lambda z: z > zoom + 0.5, "the zoom never grew")
    reports = [m for m in received if m.get("type") == "view_report"]
    assert any(m.get("cause") == "user" for m in reports)
    assert not any(m.get("type") == "click" for m in received)


def test_cluster_boundary(harness, page_session):
    widget = MapWidget()
    pair = [(10.0, 20.0), (10.0000898, 20.0)]
    widget.set_center(10.00004, 20.0, zoom=15)
    show(page_session, widget, layer_of(widget, pair, cluster=Cluster(max_zoom=14)))
    wait_for(page_session, lambda: widget.view, "no view report")

    assert len(features(page_session, widget, "circle")) == 2
    assert features(page_session, widget, "cluster") == []

    widget.set_center(10.00004, 20.0, zoom=10)
    wait_view_zoom(page_session, widget, lambda z: abs(z - 10) < 0.01, "never at zoom 10")
    idle(page_session)
    bubbles = features(page_session, widget, "cluster")
    assert [b["props"]["point_count"] for b in bubbles] == [2]
    assert features(page_session, widget, "circle") == []


def test_restyle_cluster_colour(harness, page_session, tiles):
    widget = MapWidget()
    basemap = Basemap((tiles.url("base"),))
    tiles.color("base", (0, 160, 0))
    first = layer_of(widget, BOX, paint=VectorPaint(stroke="#3388ff"))
    widget.set_center(0, 0, zoom=9)
    show(page_session, widget, first, basemap=basemap)
    assert features(page_session, widget, "cluster")

    red = replace(first, paint=VectorPaint(stroke="#ff0000"))
    publish(page_session, widget, red, basemap=basemap)
    bubbles = features(page_session, widget, "cluster")
    assert bubbles
    assert near(inside(page_session, bubbles[0]), RED)

    publish(page_session, widget, replace(red, opacity=0), basemap=basemap)
    shown = pixel(page_session, bubbles[0]["x"], bubbles[0]["y"] - 7)
    assert near(shown, (0, 160, 0))


def test_deferred_expansion_yields_to_request(harness, page_session):
    widget = MapWidget()
    layer = clustered_view(page_session, widget)
    bubbles = features(page_session, widget, "cluster")
    assert bubbles
    root = page_session.locator(".psm-map").element_handle()
    root.evaluate("(el, id) => psmHarness.holdExpansion(el, id)", f"psm:pts:{layer['instance']}")

    wait_for(page_session, lambda: widget.view, "no view report")
    page_session.mouse.click(*canvas_point(page_session, bubbles[0]["lng"], bubbles[0]["lat"]))
    widget.set_center(50, 10, zoom=4)
    wait_view_zoom(page_session, widget, lambda z: abs(z - 4) < 0.01, "the request never applied")
    root.evaluate("el => psmHarness.releaseExpansion(el)")
    page_session.wait_for_timeout(1000)
    view = widget.view
    assert abs(view["zoom"] - 4) < 0.01
    assert abs(view["center"][0] - 50) < 0.01 and abs(view["center"][1] - 10) < 0.01


def test_pin_tint(harness, page_session):
    widget = MapWidget()
    red = VectorPaint(stroke="#ff0000", marker="pin")
    left = Layer("a", GeoJSONSource(widget.add_payload(points([(-10, 0)]))), paint=red)
    big = replace(red, point_radius=10)
    right = Layer("b", GeoJSONSource(widget.add_payload(points([(10, 0)]))), paint=big)
    widget.set_center(0, 0, zoom=4)
    show(page_session, widget, left, right)
    for layer_id, lng, size in (("a", -10, 1), ("b", 10, 2)):
        x, y = page_session.evaluate(
            f"c => {{ const p = {ROOT}.psmMap.project(c); return [p.x, p.y]; }}", [lng, 0]
        )
        assert near(pixel(page_session, x, y - 18 * size), RED), layer_id
