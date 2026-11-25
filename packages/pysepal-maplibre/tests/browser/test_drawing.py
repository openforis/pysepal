"""Drawing with the real Terra Draw: the views own the features, Python mirrors them."""

import json
import re
import uuid

from IPython.display import display

from pysepal_map import GeoJSONSource, Layer, MapState, MapWidget

MOUNTED = "[...document.querySelectorAll('.psm-map')].filter((el) => el.psmDraw)"
UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
EMPTY = {"type": "FeatureCollection", "features": []}


def square(west, south, east, north):
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "Polygon", "coordinates": [ring]}


def feature(geometry, **extra):
    return {"type": "Feature", "properties": {}, "geometry": geometry, **extra}


def payload(*geometries):
    features = [feature(g) for g in geometries]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


def show(page, widget, count=1):
    """Display ``widget`` once more; its ``count`` views once their maps are idle."""
    display(widget)
    page.wait_for_function(f"n => {MOUNTED}.length === n", arg=count)
    views = [page.locator(".psm-map").nth(i).element_handle() for i in range(count)]
    for el in views:
        el.evaluate("el => psmHarness.quiet(el)")
    return views


def state(el):
    return el.evaluate("el => psmHarness.drawState(el)")


def wait_drawing(page, el, mode):
    """Wait until the view's Terra Draw runs in ``mode``."""
    page.wait_for_function(
        "([el, mode]) => { const s = psmHarness.drawState(el); return s.running && s.mode === mode; }",
        arg=[el, mode],
    )


def wait_stopped(page, el):
    page.wait_for_function("el => !psmHarness.drawState(el).running", arg=el)


def wait_for(page, check, what, timeout_ms=15_000):
    """Wait until ``check()`` holds; Python's side changes as messages arrive."""
    for _ in range(timeout_ms // 20):
        if check():
            return
        page.wait_for_timeout(20)
    raise AssertionError(what)


def record(widget):
    """The draw reports Python handled, and a list for a session's ``on_change`` calls."""
    reports, calls = [], []

    def on_msg(_, content, buffers):
        if content.get("type") == "draw_report":
            reports.append(content)

    widget.on_msg(on_msg)
    return reports, calls


def acknowledged(reports, seq):
    """The acknowledgements of request ``seq`` among ``reports``."""
    return [r for r in reports if r["cause"] == "request" and r["request_seq"] == seq]


def wait_acknowledged(page, reports, seq, views):
    """Wait until each of ``views`` acknowledged request ``seq``.

    A view an earlier display replaced may still acknowledge it too.
    """
    ids = {el.evaluate("el => psmHarness.viewId(el)") for el in views}
    wait_for(
        page,
        lambda: ids <= {r["view_id"] for r in acknowledged(reports, seq)},
        f"not every view acknowledged request {seq}",
    )


def wait_session(page, el, session, mode="static"):
    """Wait until the view's Terra Draw runs for ``session`` in ``mode``."""
    page.wait_for_function(
        "([el, session, mode]) => { const s = psmHarness.drawState(el);"
        " return s.running && s.session === session && s.mode === mode; }",
        arg=[el, session, mode],
    )


def at(page, el, x, y):
    """The page position of the view's canvas pixel, once nothing covers it."""
    box = el.bounding_box()
    px, py = box["x"] + x, box["y"] + y
    # Solara can briefly lay a progress spinner over the page as a test starts.
    page.wait_for_function(
        "([el, x, y]) => document.elementFromPoint(x, y) === el.psmMap.getCanvas()",
        arg=[el, px, py],
    )
    return px, py


def click(page, el, x, y, **kwargs):
    page.mouse.click(*at(page, el, x, y), **kwargs)


def drag(page, el, start, by):
    x, y = at(page, el, *start)
    page.mouse.move(x, y)
    page.mouse.down()
    page.mouse.move(x + by[0], y + by[1], steps=8)
    page.mouse.up()


def pixel(el, lnglat):
    """The whole canvas pixel of a coordinate, as pointer events carry it."""
    return el.evaluate(
        "(el, c) => { const p = el.psmMap.project(c); return [Math.round(p.x), Math.round(p.y)]; }",
        list(lnglat),
    )


def lnglat(el, x, y):
    """The coordinate of a canvas pixel."""
    return el.evaluate("(el, p) => el.psmMap.unproject(p).toArray()", [x, y])


def spread(el, *fractions):
    """Canvas pixels at fractions of the view's width and height."""
    box = el.bounding_box()
    return [(round(fx * box["width"]), round(fy * box["height"])) for fx, fy in fractions]


def close(got, want, tol=1e-6):
    return all(abs(g - w) < tol for g, w in zip(got, want))


def same_corners(ring, want, tol=1e-6):
    """Whether a closed ring has the corners ``want``, in any order or winding."""
    corners = ring[:-1]
    return (
        ring[0] == ring[-1]
        and len(corners) == len(want)
        and all(any(close(c, w, tol) for c in corners) for w in want)
    )


def place(page, el, points, first=1):
    """Click each canvas pixel of ``points`` in polygon mode, the ``first``-th vertex first."""
    for n, (x, y) in enumerate(points, start=first):
        click(page, el, x, y)
        page.wait_for_function(
            "([el, n]) => psmHarness.drawState(el).store.some((f) =>"
            " f.properties.currentlyDrawing && f.properties.committedCoordinateCount === n)",
            arg=[el, n],
        )


def draw_polygon(page, el, points):
    """Click each canvas pixel of ``points``, then the first again to close the polygon."""
    place(page, el, points)
    click(page, el, *points[0])
    page.wait_for_function(
        "el => !psmHarness.drawState(el).store.some((f) => f.properties.currentlyDrawing)",
        arg=el,
    )


def polygons(el):
    """The committed polygons the view holds."""
    return [f for f in state(el)["committed"] if f["geometry"]["type"] == "Polygon"]


def shown(page, el, lnglat_, layer):
    """Wait until the view renders a feature of Terra Draw's ``layer`` at ``lnglat_``."""
    page.wait_for_function(
        """([el, c, layer]) => {
            const map = el.psmMap;
            if (!map.getLayer(layer)) return false;
            const p = map.project(c);
            map.triggerRepaint();
            return map.queryRenderedFeatures([p.x, p.y], {layers: [layer]}).length > 0;
        }""",
        arg=[el, list(lnglat_), layer],
    )


def select(page, el, inside):
    """Select the drawn feature under ``inside`` in select mode."""
    click(page, el, *pixel(el, inside))
    page.wait_for_function(
        "el => psmHarness.drawState(el).store.some((f) => f.properties.selected)", arg=el
    )


def test_draw_polygon_reports_feature(harness, page_session):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    session.start("polygon")
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "polygon")
    points = spread(el, (0.3, 0.3), (0.5, 0.25), (0.55, 0.65), (0.35, 0.7))
    want = [lnglat(el, *p) for p in points]

    draw_polygon(page_session, el, points)
    wait_for(page_session, lambda: calls, "on_change never ran")
    page_session.wait_for_timeout(500)

    [drawn] = session.features["features"]
    assert drawn["geometry"]["type"] == "Polygon"
    assert same_corners(drawn["geometry"]["coordinates"][0], want)
    assert drawn["properties"] == {"mode": "polygon"}
    assert calls == [session.features]
    assert [r["cause"] for r in reports] == ["request", "user"]

    # Terra Draw owns the cursor while it draws and clears it on the way out.
    widget.cursor = "wait"
    page_session.wait_for_timeout(200)
    assert el.evaluate("el => el.psmMap.getCanvas().style.cursor") != "wait"
    session.stop()
    page_session.wait_for_function("el => el.psmMap.getCanvas().style.cursor === 'wait'", arg=el)


def test_reorder_mid_polygon_through_widget(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    south = Layer("south", GeoJSONSource(widget.add_payload(payload(square(-40, -20, -30, -10)))))
    north = Layer("north", GeoJSONSource(widget.add_payload(payload(square(30, 10, 40, 20)))))
    widget.publish(MapState(layers=(south, north)))
    reports, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    session.start("polygon")
    [el] = show(page_session, widget)
    wait_settled(page_session, 1)
    wait_drawing(page_session, el, "polygon")

    def drawing_on_top():
        order = el.evaluate("el => el.psmMap.getLayersOrder()")
        drawing = [i for i, i_d in enumerate(order) if i_d.startswith("psm-draw-")]
        owned = [i for i, i_d in enumerate(order) if i_d.startswith("psm:")]
        assert drawing and owned and max(owned) < min(drawing), order

    drawing_on_top()
    points = spread(el, (0.3, 0.3), (0.55, 0.25), (0.45, 0.7))
    want = [lnglat(el, *p) for p in points]
    place(page_session, el, points[:2])
    third = Layer("third", GeoJSONSource(widget.add_payload(payload(square(-5, -5, 5, 5)))))
    widget.publish(MapState(layers=(north, south, third)))
    wait_settled(page_session, 2)
    drawing_on_top()

    place(page_session, el, points[2:], first=3)
    drawing_on_top()
    click(page_session, el, *points[0])
    wait_for(page_session, lambda: calls, "on_change never ran")
    drawing_on_top()
    page_session.wait_for_timeout(500)
    assert len(calls) == 1 and [r["cause"] for r in reports] == ["request", "user"]
    [drawn] = widget.draw.features["features"]
    assert same_corners(drawn["geometry"]["coordinates"][0], want)


def test_cancel_and_vertex_delete(harness, page_session):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(
        ("polygon",), features=[feature(square(-20, -10, 0, 10))], on_change=calls.append
    )
    [el] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")

    session.start("polygon")
    wait_drawing(page_session, el, "polygon")
    place(page_session, el, spread(el, (0.7, 0.3), (0.8, 0.4)))
    el.evaluate("el => el.psmMap.getCanvas().focus()")
    page_session.keyboard.press("Escape")
    page_session.wait_for_function(
        "el => !psmHarness.drawState(el).store.some((f) => f.properties.currentlyDrawing)",
        arg=el,
    )
    page_session.wait_for_timeout(500)
    assert [r["cause"] for r in reports] == ["request"]

    session.start("select")
    wait_drawing(page_session, el, "select")
    select(page_session, el, (-10, 0))
    click(page_session, el, *pixel(el, (0, 10)), button="right")
    wait_for(page_session, lambda: calls, "the vertex deletion never reached Python")
    page_session.wait_for_timeout(500)
    assert [r["cause"] for r in reports] == ["request", "user"]
    [edited] = session.features["features"]
    assert same_corners(edited["geometry"]["coordinates"][0], [[-20, -10], [0, -10], [-20, 10]])


def test_theme_change_mid_polygon(harness, page_session):
    widget = MapWidget(zoom=3)
    _, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    session.start("polygon")
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "polygon")
    points = spread(el, (0.3, 0.3), (0.55, 0.25), (0.45, 0.7))
    want = [lnglat(el, *p) for p in points]
    place(page_session, el, points[:2])

    widget.draw.set_color("#ff0000")
    # wait_for_function takes a pending promise for a truthy result; evaluate awaits it.
    outlined = """async el => {
        const data = await el.psmMap.getSource('psm-draw-polygon').getData();
        return data.features.some((f) => f.properties.polygonOutlineColor === '#ff0000');
    }"""
    wait_for(page_session, lambda: el.evaluate(outlined), "the colour never reached the map")
    assert state(el)["color"] == "#ff0000"
    [drawing] = [f for f in state(el)["store"] if f["properties"].get("currentlyDrawing")]
    assert drawing["properties"]["committedCoordinateCount"] == 2

    place(page_session, el, points[2:], first=3)
    click(page_session, el, *points[0])
    wait_for(page_session, lambda: calls, "on_change never ran")
    [drawn] = session.features["features"]
    assert same_corners(drawn["geometry"]["coordinates"][0], want)


def test_redisplay_restores_drawing(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    _, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    session.start("polygon")
    [first] = show(page_session, widget)
    wait_drawing(page_session, first, "polygon")
    draw_polygon(page_session, first, spread(first, (0.3, 0.2), (0.6, 0.2), (0.6, 0.8), (0.3, 0.8)))
    wait_for(page_session, lambda: calls, "on_change never ran")
    [drawn] = session.features["features"]

    # The first view took the start: a view shown later begins with no tool.
    _, second = show(page_session, widget, count=2)
    wait_drawing(page_session, second, "static")
    assert polygons(second) == [drawn]

    session.start("select")
    wait_drawing(page_session, second, "select")
    corners = drawn["geometry"]["coordinates"][0]
    middle = [sum(c[i] for c in corners[:-1]) / 4 for i in (0, 1)]
    select(page_session, second, middle)
    vertex = pixel(second, corners[1])
    drag(page_session, second, vertex, (30, 20))
    wait_for(page_session, lambda: len(calls) == 2, "the vertex drag never reached Python")
    [moved] = session.features["features"]
    assert widget.drawn["request_seq"] == 1
    assert moved["id"] == drawn["id"]
    target = lnglat(second, vertex[0] + 30, vertex[1] + 20)
    assert any(close(c, target, 1e-3) for c in moved["geometry"]["coordinates"][0])
    assert not any(close(c, corners[1], 1e-6) for c in moved["geometry"]["coordinates"][0])


def test_seed_replaces_drawing(harness, page_session):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    session.start("polygon")
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "polygon")
    draw_polygon(page_session, el, spread(el, (0.3, 0.3), (0.5, 0.25), (0.45, 0.7)))
    wait_for(page_session, lambda: calls, "on_change never ran")

    session.set(feature(square(-10, -10, 10, 10)))
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 2, "no acknowledgement")
    page_session.wait_for_timeout(500)
    [seed] = widget.drawn["features"]
    assert seed["geometry"] == widget.draw_request["features"][0]["geometry"]
    assert polygons(el) == [seed] and len(state(el)["committed"]) == 1
    assert session.features["features"] == [seed]
    assert len(calls) == 1
    assert [r["cause"] for r in reports] == ["request", "user", "request"]


def test_multipolygon_seed_survives(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    fid = str(uuid.uuid4())
    rings = [square(w, 0, w + 5, 5)["coordinates"] for w in (-20, -5, 10)]
    multi = {"type": "MultiPolygon", "coordinates": rings}
    widget.draw.begin(features=[feature(multi, id=fid, properties={"name": "m"})])
    [_view] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")
    acknowledged = widget.drawn["features"]
    ids = [f["id"] for f in acknowledged]
    assert len(acknowledged) == 3 and len(set(ids)) == 3 and ids[0] == fid
    assert all(f["properties"] == {"name": "m", "mode": "polygon"} for f in acknowledged)

    _, second = show(page_session, widget, count=2)
    wait_drawing(page_session, second, "static")
    assert polygons(second) == acknowledged


def test_seeds_are_prepared_in_the_browser(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    reports, _ = record(widget)
    display(widget)
    views = show(page_session, widget, count=2)
    fid = str(uuid.uuid4())
    multi = {
        "type": "MultiPolygon",
        "coordinates": [square(w, 0, w + 5, 5)["coordinates"] for w in (-20, -5)],
    }
    precise = square(10.123456789012, 0.000000000001, 15.5, 5)
    session = widget.draw.begin(
        ("polygon",),
        features=[
            feature(multi, id=fid, properties={"name": "m", "selected": True}),
            feature(precise, properties={"selected": True, "mode": "select"}),
        ],
    )
    seq = widget.draw_request["seq"]
    wait_acknowledged(page_session, reports, seq, views)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == seq, "no acknowledgement kept")

    for el in views:
        for middle in ((-17.5, 2.5), (-2.5, 2.5), (12.8, 2.5)):
            shown(page_session, el, middle, "psm-draw-polygon")
    ids = {tuple(f["id"] for f in r["features"]) for r in acknowledged(reports, seq)}
    assert len(ids) == 1
    [held] = ids
    assert len(set(held)) == 3 and held[0] == fid
    assert all(UUID4.fullmatch(i) for i in held)
    features = session.features["features"]
    assert tuple(f["id"] for f in features) == held
    assert [f["properties"] for f in features] == [
        {"name": "m", "mode": "polygon"},
        {"name": "m", "mode": "polygon"},
        {"mode": "polygon"},
    ]
    coordinates = [c for f in features for c in f["geometry"]["coordinates"][0]]
    assert all(round(x, 9) == x for c in coordinates for x in c)
    assert features[2]["geometry"] == square(10.123456789, 0, 15.5, 5)
    for el in views:
        assert [f["id"] for f in state(el)["committed"]] == list(held)


def test_select_deselect_reports_nothing(harness, page_session):
    widget = MapWidget(zoom=3)
    session = widget.draw.begin(("polygon",), features=[feature(square(-10, -10, 10, 10))])
    session.start("select")
    reports, _ = record(widget)
    [el] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")
    wait_drawing(page_session, el, "select")
    log = el.evaluate("el => psmHarness.drawLog(el).length")

    select(page_session, el, (0, 0))
    page_session.wait_for_function(
        "el => psmHarness.drawState(el).store.some((f) => f.properties.selectionPoint)", arg=el
    )
    click(page_session, el, *spread(el, (0.15, 0.25))[0])
    page_session.wait_for_function(
        "el => !psmHarness.drawState(el).store.some((f) => f.properties.selected"
        " || f.properties.selectionPoint)",
        arg=el,
    )
    page_session.wait_for_timeout(500)
    assert el.evaluate("el => psmHarness.drawLog(el).length") == log
    assert [r["cause"] for r in reports] == ["request"]


def test_point_in_repeated_world(harness, page_session):
    widget = MapWidget(center=(-170, 10), zoom=4, height="250px")
    _, calls = record(widget)
    session = widget.draw.begin(("point",), edit=False, on_change=calls.append)
    session.start("point")
    [first] = show(page_session, widget)
    wait_drawing(page_session, first, "point")
    widget.set_center(190, 10)
    page_session.wait_for_function(
        "el => Math.abs(el.psmMap.getCenter().lng - 190) < 1e-6", arg=first
    )
    first.evaluate("el => psmHarness.quiet(el)")

    x, y = pixel(first, (190.1, 10))
    assert lnglat(first, x, y)[0] > 180
    click(page_session, first, x, y)
    wait_for(page_session, lambda: calls, "on_change never ran")
    [held] = [f for f in state(first)["store"] if f["geometry"]["type"] == "Point"]
    raw_lng, raw_lat = held["geometry"]["coordinates"]
    assert raw_lng > 180
    expected = first.evaluate("(el, lng) => Math.round((lng - 360) * 1e9) / 1e9", raw_lng)
    [point] = session.features["features"]
    lng, lat = point["geometry"]["coordinates"]
    assert lng == expected and lat == raw_lat
    assert abs(lng - -169.9) < 0.05 and round(lng, 9) == lng

    # A new session seeded with the reported point shows it in the repeated world.
    session.end()
    wait_stopped(page_session, first)
    widget.draw.begin(("point",), edit=False, features=[point])
    wait_session(page_session, first, 2)
    assert [f["geometry"]["coordinates"] for f in state(first)["store"]] == [[lng, lat]]
    shown(page_session, first, (lng + 360, lat), "psm-draw-point")

    _, second = show(page_session, widget, count=2)
    wait_drawing(page_session, second, "static")
    assert [f["geometry"]["coordinates"] for f in state(second)["store"]] == [[lng, lat]]
    shown(page_session, second, (lng + 360, lat), "psm-draw-point")


def test_rectangle_edit_survives_redisplay(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    _, calls = record(widget)
    session = widget.draw.begin(("rectangle",), on_change=calls.append)
    session.start("rectangle")
    [first] = show(page_session, widget)
    wait_drawing(page_session, first, "rectangle")
    a, b = spread(first, (0.3, 0.25), (0.45, 0.65))
    click(page_session, first, *a)
    page_session.mouse.move(*at(page_session, first, *b), steps=5)
    click(page_session, first, *b)
    wait_for(page_session, lambda: calls, "on_change never ran")
    [drawn] = session.features["features"]
    assert drawn["properties"]["mode"] == "rectangle"

    session.start("select")
    wait_drawing(page_session, first, "select")
    corners = drawn["geometry"]["coordinates"][0]
    middle = [sum(c[i] for c in corners[:-1]) / 4 for i in (0, 1)]
    select(page_session, first, middle)
    corner = max(corners[:-1], key=lambda c: (c[0], -c[1]))
    drag(page_session, first, pixel(first, corner), (40, 30))
    wait_for(page_session, lambda: len(calls) == 2, "the resize never reached Python")
    [resized] = session.features["features"]
    ring = resized["geometry"]["coordinates"][0]
    assert resized["properties"]["mode"] == "rectangle" and ring != corners
    assert len({c[0] for c in ring}) == 2 and len({c[1] for c in ring}) == 2

    _, second = show(page_session, widget, count=2)
    wait_drawing(page_session, second, "static")
    [again] = polygons(second)
    assert again["id"] == resized["id"]
    assert again["geometry"] == resized["geometry"]


def test_edit_after_style_replacement(harness, page_session, browser_errors):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(
        ("polygon",), features=[feature(square(-10, -10, 10, 10))], on_change=calls.append
    )
    session.start("select")
    [el] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")
    wait_drawing(page_session, el, "select")

    for diff in ("false", "true"):
        before = state(el)["committed"]
        el.evaluate(
            f"el => el.psmMap.setStyle({{version: 8, sources: {{}}, layers: []}}, {{diff: {diff}}})"
        )
        page_session.wait_for_function(
            "el => psmHarness.drawState(el).running && el.psmMap.getSource('psm-draw-polygon')"
            " && el.psmMap.isStyleLoaded()",
            arg=el,
        )
        wait_drawing(page_session, el, "select")
        assert state(el)["committed"] == before
        shown(page_session, el, (0, 0), "psm-draw-polygon")

        count = len(calls)
        corners = before[0]["geometry"]["coordinates"][0]
        select(page_session, el, (0, 0))
        drag(page_session, el, pixel(el, corners[1]), (25, 15))
        wait_for(page_session, lambda: len(calls) == count + 1, f"no edit after diff={diff}")
        page_session.wait_for_timeout(300)
        assert len(calls) == count + 1
        assert widget.drawn["features"][0]["geometry"] != before[0]["geometry"]
        # Deselect, for the next round's click to select again.
        click(page_session, el, *spread(el, (0.15, 0.25))[0])
    assert [r["cause"] for r in reports] == ["request", "user", "user"]
    assert browser_errors == []


def test_end_mid_drag_restores_navigation(harness, page_session):
    widget = MapWidget(zoom=3)
    session = widget.draw.begin(("polygon",), features=[feature(square(-10, -10, 10, 10))])
    session.start("select")
    reports, _ = record(widget)
    [el] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")
    wait_drawing(page_session, el, "select")
    select(page_session, el, (0, 0))

    x, y = at(page_session, el, *pixel(el, (10, 10)))
    page_session.mouse.move(x, y)
    page_session.mouse.down()
    page_session.mouse.move(x + 20, y + 20, steps=5)
    page_session.wait_for_function("el => !el.psmMap.dragPan.isEnabled()", arg=el)
    session.end()
    wait_stopped(page_session, el)
    page_session.mouse.move(x + 40, y + 40, steps=5)
    page_session.mouse.up()
    assert el.evaluate(
        "el => [el.psmMap.dragPan.isEnabled(), el.psmMap.doubleClickZoom.isEnabled()]"
    ) == [True, True]

    middle = spread(el, (0.5, 0.5))[0]
    center = el.evaluate("el => el.psmMap.getCenter().toArray()")
    drag(page_session, el, middle, (-120, 60))
    page_session.wait_for_function(
        "([el, c]) => !el.psmMap.isMoving() && Math.abs(el.psmMap.getCenter().lng - c[0]) > 1",
        arg=[el, center],
    )
    zoom = el.evaluate("el => el.psmMap.getZoom()")
    page_session.mouse.dblclick(*at(page_session, el, *middle))
    page_session.wait_for_function("([el, z]) => el.psmMap.getZoom() > z + 0.5", arg=[el, zoom])
    assert [r["cause"] for r in reports] == ["request"]


def test_a_new_session_drops_the_old_drawing(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    reports, calls = record(widget)
    old = widget.draw.begin(("polygon",), on_change=calls.append)
    display(widget)
    one, two = show(page_session, widget, count=2)
    old.start("polygon")
    for el in (one, two):
        wait_drawing(page_session, el, "polygon")
    # The views of one widget never follow each other's drawing.
    draw_polygon(page_session, one, spread(one, (0.2, 0.3), (0.35, 0.3), (0.3, 0.7)))
    wait_for(page_session, lambda: len(calls) == 1, "the first view's polygon never arrived")
    [mine] = old.features["features"]
    draw_polygon(page_session, two, spread(two, (0.6, 0.3), (0.75, 0.3), (0.7, 0.7)))
    wait_for(page_session, lambda: len(calls) == 2, "the second view's polygon never arrived")
    [theirs] = old.features["features"]
    assert mine["id"] != theirs["id"]
    assert polygons(one) == [mine] and polygons(two) == [theirs]

    new = widget.draw.begin(("polygon",), features=[feature(square(-10, -10, 10, 10))])
    seq = widget.draw_request["seq"]
    for el in (one, two):
        wait_session(page_session, el, 2)
    wait_acknowledged(page_session, reports, seq, (one, two))
    [seed] = new.features["features"]
    assert seed["geometry"] == square(-10, -10, 10, 10)
    for el in (one, two):
        assert polygons(el) == [seed]
    assert not old.active and old.features == EMPTY
    assert len(calls) == 2


def test_end_empties_every_view(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    session = widget.draw.begin(("polygon",), features=[feature(square(-10, -10, 10, 10))])
    display(widget)
    views = show(page_session, widget, count=2)
    for el in views:
        wait_drawing(page_session, el, "static")
        assert len(polygons(el)) == 1

    session.end()
    for el in views:
        wait_stopped(page_session, el)
        assert state(el)["committed"] == []
    assert session.features == widget.draw.features == EMPTY

    widget.draw.begin(("polygon",))
    for el in views:
        wait_session(page_session, el, 2)
        assert state(el)["store"] == []


def toolbar(el):
    """The draw toolbar's buttons, as ``[class, mode, title, aria-label, aria-pressed]``."""
    return el.evaluate("""el => [...el.querySelectorAll('.psm-draw-toolbar button')].map((b) => [
            b.className, b.dataset.mode ?? null, b.title, b.getAttribute('aria-label'),
            b.getAttribute('aria-pressed'),
        ])""")


def press(page, el, selector):
    """Click a toolbar button, once nothing covers it."""
    button = el.query_selector(f".psm-draw-toolbar {selector}")
    box = button.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.wait_for_function(
        "([b, x, y]) => b.contains(document.elementFromPoint(x, y))", arg=[button, x, y]
    )
    page.mouse.click(x, y)


def test_toolbar_click_draws_without_python(harness, page_session):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(("polygon",), on_change=calls.append)
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "static")

    press(page_session, el, "[data-mode=polygon]")
    wait_drawing(page_session, el, "polygon")
    assert [b[4] for b in toolbar(el)] == ["true", "false", None]
    draw_polygon(page_session, el, spread(el, (0.3, 0.3), (0.55, 0.25), (0.45, 0.7)))
    wait_for(page_session, lambda: calls, "on_change never ran")
    [drawn] = session.features["features"]
    assert drawn["geometry"]["type"] == "Polygon" and drawn["properties"] == {"mode": "polygon"}
    assert [r["cause"] for r in reports] == ["request", "user"]

    # A second click leaves the tool; Python never asked for either.
    press(page_session, el, "[data-mode=polygon]")
    wait_drawing(page_session, el, "static")
    assert [b[4] for b in toolbar(el)] == ["false", "false", None]
    assert widget.draw_tool["seq"] == 0


def test_toolbar_clear_reports_an_empty_user_drawing(harness, page_session):
    widget = MapWidget(zoom=3)
    reports, calls = record(widget)
    session = widget.draw.begin(
        ("polygon",), features=[feature(square(-10, -10, 10, 10))], on_change=calls.append
    )
    [el] = show(page_session, widget)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")

    press(page_session, el, ".psm-draw-clear")
    wait_for(page_session, lambda: calls, "the clear never reached Python")
    assert calls == [EMPTY] and session.features == EMPTY
    assert state(el)["committed"] == [] and state(el)["store"] == []
    # Already empty, a clear still tells Python that a user cleared it.
    press(page_session, el, ".psm-draw-clear")
    wait_for(page_session, lambda: len(calls) == 2, "the second clear never reached Python")
    assert calls == [EMPTY, EMPTY]
    assert [(r["cause"], r["request_seq"]) for r in reports] == [
        ("request", 1),
        ("user", 1),
        ("user", 1),
    ]
    assert widget.draw_request["seq"] == 1


def test_toolbar_follows_the_session(harness, page_session):
    widget = MapWidget(zoom=3)
    widget.draw.set_labels({"polygon": "Forme libre"})
    [el] = show(page_session, widget)
    assert toolbar(el) == []

    session = widget.draw.begin(("polygon", "point"))
    page_session.wait_for_function("el => el.querySelector('.psm-draw-toolbar')", arg=el)

    def tool(mode, title):
        return ["psm-draw-tool", mode, title, title, "false"]

    assert toolbar(el) == [
        tool("polygon", "Forme libre"),
        tool("point", "Draw a point"),
        tool("select", "Select and edit shapes"),
        ["psm-draw-clear", None, "Remove all shapes", "Remove all shapes", None],
    ]
    # One group below the zoom and fullscreen controls, each button an inline icon.
    corner = el.evaluate(
        "el => [...el.querySelector('.maplibregl-ctrl-top-left').children].map((c) => c.className)"
    )
    assert len(corner) == 3 and "psm-draw-toolbar" in corner[-1]
    icons = el.evaluate("""el => [...el.querySelectorAll('.psm-draw-toolbar button')].map((b) => {
            const box = b.querySelector('svg > path').getBoundingClientRect();
            return [b.querySelectorAll('svg').length, Math.min(box.width, box.height) > 8,
                    Math.max(box.width, box.height) <= 20];
        })""")
    assert icons == [[1, True, True]] * 4

    widget.draw.set_labels({"clear": "Tout effacer"})
    page_session.wait_for_function(
        "el => el.querySelector('.psm-draw-clear').title === 'Tout effacer'", arg=el
    )
    session.end()
    page_session.wait_for_function("el => !el.querySelector('.psm-draw-toolbar')", arg=el)


def test_start_reaches_a_view_shown_later(harness, page_session):
    widget = MapWidget(zoom=3, height="250px")
    session = widget.draw.begin(("polygon",))
    session.start("polygon")
    [first] = show(page_session, widget)
    wait_drawing(page_session, first, "polygon")
    assert [b[4] for b in toolbar(first)] == ["true", "false", None]

    # The first view took the start: the views shown again, or later, begin with no tool.
    views = show(page_session, widget, count=2)
    for el in views:
        wait_drawing(page_session, el, "static")
        assert [b[4] for b in toolbar(el)] == ["false", "false", None]
    session.start("select")
    for el in views:
        wait_drawing(page_session, el, "select")
    assert widget.draw_tool == {"seq": 2, "session": 1, "mode": "select"}
