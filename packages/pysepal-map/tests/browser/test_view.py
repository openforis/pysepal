"""Check in a real browser that the browser owns the camera and Python mirrors it."""

import ipywidgets as widgets
import pytest
from IPython.display import display
from pysepal_map import MapWidget

BOX = (10, 10, 20, 20)


def view_at(page, nth=0):
    page.wait_for_function("n => document.querySelectorAll('.psm-map')[n]?.psmCamera", arg=nth)
    return page.locator(".psm-map").nth(nth).element_handle()


def wait_views(page, count):
    page.wait_for_function("n => document.querySelectorAll('.psm-map').length === n", arg=count)


def wait_view(page, widget, check, timeout_ms=15_000):
    """Wait until ``check(widget.view)`` holds; reports come over the comm."""
    for _ in range(timeout_ms // 20):
        if widget.view and check(widget.view):
            return dict(widget.view)
        page.wait_for_timeout(20)
    raise AssertionError(f"the view never matched: {widget.view}")


def camera(el):
    """The camera of the view's map once it stopped moving."""
    return el.evaluate(
        """async el => {
            const map = el.psmMap;
            for (let i = 0; i < 250 && map.isMoving(); i++) {
                await new Promise((resolve) => setTimeout(resolve, 20));
            }
            const c = map.getCenter();
            const b = map.getBounds();
            return {
                center: [c.lng, c.lat],
                zoom: map.getZoom(),
                bearing: map.getBearing(),
                pitch: map.getPitch(),
                bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
            };
        }"""
    )


def contains(bounds, box):
    west, south, east, north = bounds
    return west <= box[0] and south <= box[1] and east >= box[2] and north >= box[3]


def near(a, b, tol=1e-6):
    return all(x == pytest.approx(y, abs=tol) for x, y in zip(a, b))


def matches(el):
    """A check that Python mirrors this view's camera once it settled."""

    def check(view):
        now = camera(el)
        return near(view["center"], now["center"]) and view["zoom"] == pytest.approx(
            now["zoom"], abs=1e-6
        )

    return check


def middle(page, nth=0):
    """The middle of a view, once its map is idle and nothing covers it.

    Solara can briefly lay a progress spinner over the page as a test starts.
    """
    el = view_at(page, nth)
    el.evaluate("el => psmHarness.quiet(el)")
    box = el.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.wait_for_function(
        "([el, x, y]) => document.elementFromPoint(x, y)?.closest('.psm-map') === el",
        arg=[el, x, y],
    )
    return x, y


def drag(page, start, by, button="left"):
    x, y = start
    page.mouse.move(x, y)
    page.mouse.down(button=button)
    page.mouse.move(x + by[0], y + by[1], steps=10)
    page.mouse.up(button=button)


# Two touches around the map's middle, as (dx, dy) of each at progress t.
TURN = "t => [0, Math.PI].map(a => [80 * Math.cos(a + t), 80 * Math.sin(a + t)])"
TILT = "t => [[-60, -100 * t], [60, -100 * t]]"


def two_fingers(el, at):
    """Drag two touches over the map; ``at`` places them as progress goes 0 to 1."""
    el.evaluate(
        """(el, at) => {
            const place = eval(at);
            const target = el.psmMap.getCanvasContainer();
            const r = target.getBoundingClientRect();
            const [x, y] = [r.left + r.width / 2, r.top + r.height / 2];
            const touches = (t) => place(t).map(([dx, dy], identifier) =>
                new Touch({identifier, target, clientX: x + dx, clientY: y + dy}));
            const fire = (type, list) => target.dispatchEvent(new TouchEvent(type, {
                touches: type === 'touchend' ? [] : list,
                targetTouches: type === 'touchend' ? [] : list,
                changedTouches: list, bubbles: true, cancelable: true,
            }));
            fire('touchstart', touches(0));
            for (let i = 1; i <= 10; i++) fire('touchmove', touches(i / 10));
            fire('touchend', touches(1));
        }""",
        at,
    )


def test_request_before_display_applies(harness, page_session):
    widget = MapWidget()
    widget.fit_bounds(BOX)
    display(widget)
    view = wait_view(page_session, widget, lambda v: v["request_seq"] == 2)
    assert contains(view["bounds"], BOX)
    assert contains(camera(view_at(page_session))["bounds"], BOX)


def test_a_zoomless_center_before_display_keeps_the_zoom(harness, page_session):
    widget = MapWidget(zoom=6)
    widget.set_center(10, 10)
    display(widget)
    view = wait_view(page_session, widget, lambda v: v["request_seq"] == 2)
    assert near(view["center"], [10, 10]) and view["zoom"] == 6
    shown = camera(view_at(page_session))
    assert near(shown["center"], [10, 10]) and shown["zoom"] == 6


def test_a_short_map_reports_no_zoom_python_rejects(harness, page_session):
    widget = MapWidget(height="100px", zoom=0)
    display(widget)
    wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    el = view_at(page_session)
    x, y = middle(page_session)
    page_session.mouse.move(x, y)
    for _ in range(5):
        page_session.mouse.wheel(0, 600)
        page_session.wait_for_timeout(100)
    view = wait_view(page_session, widget, matches(el))
    assert view["zoom"] == 0
    widget.set_center(*view["center"], zoom=view["zoom"])


def test_a_resize_report_updates_the_bounds(harness, page_session):
    widget = MapWidget(height="100%")
    box = widgets.VBox([widget], layout=widgets.Layout(height="300px"))
    display(box)
    before = wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    el = view_at(page_session)
    box.layout.height = "500px"
    page_session.wait_for_function("el => el.clientHeight === 500", arg=el)

    def taller(view):
        return view["bounds"][3] - view["bounds"][1] > before["bounds"][3] - (before["bounds"][1])

    after = wait_view(page_session, widget, taller)
    assert near(after["bounds"], camera(el)["bounds"])
    assert near(after["center"], before["center"])
    assert after["request_seq"] == 1


def test_only_the_panned_views_resize_updates_its_camera(harness, page_session):
    widget = MapWidget(height="100%")
    received = []
    widget.on_msg(lambda _, content, buffers: received.append(content))
    one = widgets.VBox([widget], layout=widgets.Layout(height="200px"))
    two = widgets.VBox([widget], layout=widgets.Layout(height="200px"))
    display(widgets.VBox([one, two]))
    wait_views(page_session, 2)
    a, b = view_at(page_session, 0), view_at(page_session, 1)
    wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    drag(page_session, middle(page_session, 0), (-150, 80))
    panned = wait_view(page_session, widget, matches(a))

    # a grows, as on a fullscreen toggle: the bounds follow, the pan stays.
    one.layout.height = "320px"
    page_session.wait_for_function("el => el.clientHeight === 320", arg=a)
    grown = wait_view(page_session, widget, lambda v: near(v["bounds"], camera(a)["bounds"]))
    assert near(grown["center"], panned["center"])
    assert grown["bounds"] != panned["bounds"]

    # b's resize on the same request leaves the camera of a's pan alone.
    panner = next(m["view_id"] for m in received if m.get("cause") == "user")
    received.clear()
    two.layout.height = "320px"
    page_session.wait_for_function("el => el.clientHeight === 320", arg=b)
    for _ in range(750):
        if any(m.get("cause") == "resize" and m["view_id"] != panner for m in received):
            break
        page_session.wait_for_timeout(20)
    else:
        raise AssertionError("b's resize was never reported")
    assert widget.view == grown


def test_a_collapsed_host_fits_its_latest_request_once_shown(harness, page_session):
    widget = MapWidget(height="100%")
    box = widgets.VBox([widget], layout=widgets.Layout(height="0px"))
    display(box)
    el = view_at(page_session)
    widget.fit_bounds((-60, -30, -40, -10))
    widget.fit_bounds(BOX)
    page_session.wait_for_function("el => el.psmCamera.inspect().pending === 3", arg=el)
    assert el.evaluate("el => el.psmCamera.inspect().applied") == 1
    assert widget.view == {}

    box.layout.height = "320px"
    view = wait_view(page_session, widget, lambda v: v["request_seq"] == 3)
    fit = el.evaluate(
        """el => {
            const map = el.psmMap;
            const fit = map.cameraForBounds([10, 10, 20, 20], {padding: 20});
            const center = maplibreCenter(fit.center);
            return {height: el.clientHeight, zoom: fit.zoom, center};
            function maplibreCenter(c) {
                return Array.isArray(c) ? c : [c.lng, c.lat];
            }
        }"""
    )
    assert fit["height"] == 320
    assert view["zoom"] == pytest.approx(fit["zoom"], abs=1e-6)
    assert near(view["center"], fit["center"])
    assert contains(view["bounds"], BOX)


def test_fit_respects_insets(harness, page_session):
    widget = MapWidget()
    display(widget)
    wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    el = view_at(page_session)
    widget.set_insets(left=300)
    widget.fit_bounds(BOX)
    view = wait_view(page_session, widget, lambda v: v["request_seq"] == 2)
    shown = el.evaluate(
        """(el, box) => {
            const map = el.psmMap;
            const [w, h] = [el.clientWidth, el.clientHeight];
            const xs = [[box[0], box[1]], [box[2], box[3]]].map((c) => map.project(c).x);
            const corners = [[300, 0], [w, 0], [w, h], [300, h]].map((p) => map.unproject(p));
            const lngs = corners.map((c) => c.lng);
            const lats = corners.map((c) => c.lat);
            const corner = el.querySelector('.maplibregl-ctrl-top-left');
            return {
                width: w,
                xs,
                inside: [Math.min(...lngs), Math.min(...lats), Math.max(...lngs), Math.max(...lats)],
                corner: corner.getBoundingClientRect().left - el.getBoundingClientRect().left,
            };
        }""",
        list(BOX),
    )
    assert all(300 <= x <= shown["width"] for x in shown["xs"])
    assert near(view["bounds"], shown["inside"])
    assert shown["corner"] == pytest.approx(300, abs=0.5)


def test_the_camera_stays_north_up_and_flat(harness, page_session):
    widget = MapWidget(center=(0, 0), zoom=3)
    box = widgets.VBox([widget])
    display(box)
    before = wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    el = view_at(page_session)
    x, y = middle(page_session)

    # A default MapLibre map rotates or pitches on each of these.
    drag(page_session, (x, y), (60, -80), button="right")
    for by in ((-120, 60), (0, -80)):
        page_session.keyboard.down("Control")
        drag(page_session, (x, y), by)
        page_session.keyboard.up("Control")
    page_session.locator(".psm-map canvas.maplibregl-canvas").focus()
    for key in ("Shift+ArrowLeft", "Shift+ArrowUp"):
        page_session.keyboard.press(key)
    two_fingers(el, TURN)
    two_fingers(el, TILT)
    page_session.wait_for_timeout(500)
    turned = camera(el)
    assert (turned["bearing"], turned["pitch"]) == (0, 0)

    # Panning and zooming still work, and Python hears of them.
    drag(page_session, (x, y), (-150, 80))
    page_session.mouse.move(x, y)
    page_session.mouse.wheel(0, -400)
    page_session.wait_for_timeout(300)
    moved = wait_view(page_session, widget, matches(el))
    assert moved["zoom"] > before["zoom"] + 0.2
    assert not near(moved["center"], before["center"], tol=1)
    assert moved["request_seq"] == 1
    after = camera(el)
    assert (after["bearing"], after["pitch"]) == (0, 0)

    box.children = ()
    wait_views(page_session, 0)
    box.children = (widget,)
    restored = camera(view_at(page_session))
    assert near(restored["center"], moved["center"])
    assert restored["zoom"] == pytest.approx(moved["zoom"], abs=1e-6)
    assert widget.view_request["seq"] == 1


def test_redisplay_keeps_the_last_reported_view(harness, page_session):
    widget = MapWidget()
    # A widgets.Box lays its children out in a row, where the map has no width.
    first = widgets.VBox([widget])
    box = widgets.VBox([first])
    display(box)
    wait_view(page_session, widget, lambda v: v["request_seq"] == 1)
    widget.set_center(30, 10, zoom=4)
    reported = wait_view(page_session, widget, lambda v: v["request_seq"] == 2)
    assert near(reported["center"], [30, 10]) and reported["zoom"] == 4

    box.children = (first, widgets.VBox([widget]))
    wait_views(page_session, 2)
    shown = camera(view_at(page_session, 1))
    assert near(shown["center"], [30, 10]) and shown["zoom"] == 4

    drag(page_session, middle(page_session, 0), (-150, 80))
    panned = wait_view(page_session, widget, lambda v: v["center"][0] > 31)
    panned = wait_view(page_session, widget, matches(view_at(page_session, 0)))
    assert panned["request_seq"] == 2
    # The other displayed view keeps its own camera.
    shown = camera(view_at(page_session, 1))
    assert near(shown["center"], [30, 10]) and shown["zoom"] == 4

    box.children = (first,)
    wait_views(page_session, 1)
    box.children = (first, widgets.VBox([widget]))
    wait_views(page_session, 2)
    restored = camera(view_at(page_session, 1))
    assert near(restored["center"], panned["center"])
    assert restored["zoom"] == pytest.approx(panned["zoom"], abs=1e-6)
    assert widget.view_request["seq"] == 2
    assert widget.view["request_seq"] == 2


def test_a_view_applies_a_request_another_view_acknowledged(harness, page_session):
    widget = MapWidget(height="100%")
    received = []
    widget.on_msg(lambda _, content, buffers: received.append(content))
    one = widgets.VBox([widget], layout=widgets.Layout(height="300px"))
    two = widgets.VBox([widget], layout=widgets.Layout(height="300px"))
    display(widgets.VBox([one, two]))
    wait_views(page_session, 2)
    a, b = view_at(page_session, 0), view_at(page_session, 1)
    wait_view(page_session, widget, lambda v: v["request_seq"] == 1)

    # Hold b's reports at their origin; its user moves on request 1.
    b.evaluate("el => { psmHarness.cameraGate(el).holding = true; }")
    drag(page_session, middle(page_session, 1), (-150, 80))
    page_session.wait_for_function("el => psmHarness.cameraGate(el).held.length > 0", arg=b)
    two.layout.height = "0px"
    page_session.wait_for_function("el => el.clientHeight === 0", arg=b)

    widget.fit_bounds(BOX)
    view = wait_view(page_session, widget, lambda v: v["request_seq"] == 2)
    assert contains(view["bounds"], BOX)
    assert contains(camera(a)["bounds"], BOX)
    assert b.evaluate("el => el.psmCamera.inspect()")["pending"] == 2

    # The user pans a on request 2.
    drag(page_session, middle(page_session, 0), (-150, 80))
    panned = wait_view(page_session, widget, matches(a))
    assert panned["request_seq"] == 2

    # b takes request 2 once shown, though Python saw a acknowledge it.
    two.layout.height = "300px"
    page_session.wait_for_function("el => el.psmCamera.inspect().applied === 2", arg=b)
    assert contains(camera(b)["bounds"], BOX)
    page_session.wait_for_function(
        "el => psmHarness.cameraGate(el).held.some(r => r.request_seq === 2)", arg=b
    )

    # b's late acknowledgement, then its report on request 1, reach Python
    # after the pan; neither replaces it.
    received.clear()
    b.evaluate("el => psmHarness.cameraGate(el).release(true)")
    for _ in range(750):
        if any(m.get("request_seq") == 1 for m in received):
            break
        page_session.wait_for_timeout(20)
    else:
        raise AssertionError("the old report never arrived")
    assert any(m.get("cause") == "request" for m in received)
    assert widget.view == panned
