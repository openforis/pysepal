"""Check in a real browser that a compare view draws each side on its own map."""

import json
import re
from dataclasses import replace

import ipywidgets as widgets
import pytest
from IPython.display import display
from pysepal_map import (
    Cluster,
    GeoJSONSource,
    Interaction,
    Layer,
    MapState,
    MapWidget,
    RasterSource,
    VectorPaint,
)
from test_drawing import (
    click,
    draw_polygon,
    feature,
    place,
    record,
    select,
    show,
    spread,
    square,
    wait_drawing,
    wait_stopped,
)
from test_drawing import state as draw_state
from test_pointer import canvas_point
from test_points import points

COMPARE_RIGHT = ".psm-map .psm-compare-right"
HANDLE = ".psm-map .psm-compare-handle"
ATTRIBUTION = ".psm-map .maplibregl-ctrl-attrib-inner"
MAPLIBRE_LINK = 'a[href="https://maplibre.org/"]'


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


def clip_x(el):
    """Where the right map's clip starts, in px from the view's left edge."""
    clip = el.evaluate("el => el.psmCompare.map.getContainer().style.clipPath")
    match = re.fullmatch(r"inset\(([^)]*)\)", clip)
    assert match, clip
    sides = [float(value.removesuffix("px")) for value in match[1].split()]
    # The browser shortens the four sides as the margin shorthand does.
    top, right = sides[0], sides[1 % len(sides)]
    bottom = sides[2] if len(sides) > 2 else top
    left = sides[3] if len(sides) > 3 else right
    assert top == right == bottom == 0, clip
    return left


def width_of(el):
    return el.evaluate("el => el.clientWidth")


def center_of(page, locator):
    """The page position of an element's center, once nothing covers it there."""
    box = locator.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.wait_for_function(
        "([el, x, y]) => el.contains(document.elementFromPoint(x, y))",
        arg=[locator.element_handle(), x, y],
    )
    return x, y


def press(page, key, percent):
    """Press ``key`` on the focused handle, then wait for the divider at ``percent``."""
    page.keyboard.press(key)
    page.wait_for_function(
        f"p => document.querySelector('{HANDLE}').getAttribute('aria-valuenow') === p",
        arg=str(percent),
    )


def polygon_layer(widget, layer_id, west, south, east, north, **kwargs):
    """A GeoJSON layer of one rectangle, whose ``name`` is ``layer_id``."""
    rectangle = feature(square(west, south, east, north), properties={"name": layer_id})
    data = json.dumps({"type": "FeatureCollection", "features": [rectangle]}).encode()
    return Layer(layer_id, GeoJSONSource(widget.add_payload(data)), paint=VectorPaint(), **kwargs)


def mirror(el):
    """The right map's copy of the drawing, as ``[role, geometry]`` pairs; None before it has one."""
    return el.evaluate(
        """async el => {
            const source = el.psmCompare?.map.getSource('psm-draw-mirror');
            if (!source) return null;
            const data = await source.getData();
            return data.features.map((f) => [f.properties.psmRole, f.geometry]);
        }"""
    )


def rendered(el):
    """What Terra Draw's store holds, as the mirror should copy it."""

    def role(properties):
        if properties.get("midPoint"):
            return "midpoint"
        vertex = properties.get("selectionPoint") or properties.get("closingPoint")
        return "vertex" if vertex else "shape"

    return [[role(f["properties"]), f["geometry"]] for f in draw_state(el)["store"]]


def compare_view(page, wait_settled, widget, *layers):
    """Show ``widget`` comparing ``layers``, its maps settled; its root."""
    widget.publish(MapState(layers=layers, compare=True))
    display(widget)
    wait_settled(page, 1)
    el = root(page)
    el.evaluate("el => psmHarness.quiet(el)")
    return el


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


def test_divider_drag_clips_without_panning(harness, page_session, wait_settled):
    el = compare_view(page_session, wait_settled, MapWidget())
    width = width_of(el)
    assert clip_x(el) == pytest.approx(width / 2)
    # Out of the canvas container, where MapLibre binds its drag handlers.
    assert el.evaluate(f"el => el.querySelector('{HANDLE}').parentElement === el")
    before = cameras(el)

    x, y = center_of(page_session, page_session.locator(HANDLE))
    page_session.mouse.move(x, y)
    page_session.mouse.down()
    page_session.mouse.move(x - 100, y + 40, steps=10)
    page_session.mouse.up()
    assert clip_x(el) == pytest.approx(width / 2 - 100, abs=1)
    el.evaluate("el => psmHarness.quiet(el)")
    assert cameras(el) == before
    # The handle followed the pointer across, not down.
    after = page_session.locator(HANDLE).bounding_box()
    assert after["x"] + after["width"] / 2 == pytest.approx(x - 100, abs=1)
    assert after["y"] + after["height"] / 2 == pytest.approx(y, abs=1)


def test_divider_keyboard(harness, page_session, wait_settled):
    el = compare_view(page_session, wait_settled, MapWidget())
    width = width_of(el)
    before = cameras(el)
    page_session.locator(HANDLE).focus()
    assert el.evaluate("() => document.activeElement.matches('.psm-compare-handle')")

    # The arrows are MapLibre's pan keys too.
    steps = [
        ("ArrowLeft", 45),
        ("ArrowLeft", 40),
        ("ArrowRight", 45),
        ("Home", 0),
        ("ArrowLeft", 0),
        ("End", 100),
        ("ArrowRight", 100),
    ]
    for key, percent in steps:
        press(page_session, key, percent)
        assert clip_x(el) == pytest.approx(width * percent / 100, abs=0.5), key
    el.evaluate("el => psmHarness.quiet(el)")
    assert cameras(el) == before


def test_divider_stays_inside_insets(harness, page_session, wait_settled):
    widget = MapWidget()
    widget.set_insets(left=300)
    el = compare_view(page_session, wait_settled, widget)
    width = width_of(el)
    assert clip_x(el) == pytest.approx(300 + (width - 300) / 2)
    page_session.locator(HANDLE).focus()
    press(page_session, "Home", 0)
    assert clip_x(el) == pytest.approx(300)
    press(page_session, "End", 100)
    assert clip_x(el) == pytest.approx(width)

    widget.layout.width = "700px"
    page_session.wait_for_function("el => el.clientWidth === 700", arg=el)
    wait_for(page_session, lambda: clip_x(el) == pytest.approx(700), "the clip stayed put")
    page_session.locator(HANDLE).focus()
    press(page_session, "Home", 0)
    assert clip_x(el) == pytest.approx(300)

    try:
        page_session.locator(".psm-map .maplibregl-ctrl-fullscreen").click()
        page_session.wait_for_function("el => el.hasAttribute('data-psm-fullscreen')", arg=el)
        # Fullscreen hides the UI the insets describe: the divider uses the whole width.
        wait_for(page_session, lambda: clip_x(el) == 0, "the divider kept the insets")
        page_session.locator(HANDLE).focus()
        press(page_session, "End", 100)
        full = width_of(el)
        assert full > 700
        assert clip_x(el) == pytest.approx(full)
    finally:
        page_session.evaluate("() => document.fullscreenElement && document.exitFullscreen()")
    page_session.wait_for_function("el => !el.hasAttribute('data-psm-fullscreen')", arg=el)
    wait_for(page_session, lambda: clip_x(el) == pytest.approx(700), "the insets never came back")


def test_marker_and_popup_above_right_map(harness, page_session, wait_settled, tiles):
    tiles.color("red", (200, 0, 0))
    widget = MapWidget()
    feature = {
        "type": "Feature",
        "properties": {"name": "p"},
        "geometry": {"type": "Point", "coordinates": [30, -10]},
    }
    data = json.dumps({"type": "FeatureCollection", "features": [feature]}).encode()
    point = Layer(
        "p",
        GeoJSONSource(widget.add_payload(data)),
        paint=VectorPaint(),
        interaction=Interaction(popup=("name",), tooltip=("name",)),
    )
    # An opaque right map, so whatever shows in the right half paints above it.
    cover = Layer("cover", RasterSource((tiles.url("red"),)), side="right")
    el = compare_view(page_session, wait_settled, widget, point, cover)
    el.evaluate("el => psmHarness.quiet(el, 5, 'right')")
    box = el.bounding_box()
    divider = box["x"] + clip_x(el)

    def at(lng, lat):
        x, y = el.evaluate(
            "(el, c) => { const p = el.psmMap.project(c); return [p.x, p.y]; }", [lng, lat]
        )
        return box["x"] + x, box["y"] + y

    over_point = at(30, -10)
    plain = at(55, -25)
    away = (box["x"] + box["width"] / 4, box["y"] + box["height"] * 0.8)
    assert divider + 20 < over_point[0] < plain[0] < box["x"] + box["width"] - 60

    widget.set_marker(75, 20)
    marker = page_session.locator(".psm-map .maplibregl-marker")
    marker.wait_for()
    assert center_of(page_session, marker)[0] > divider + 20

    # The tooltip takes no input: its pixels tell whether it paints above.
    page_session.mouse.move(*over_point)
    tooltip = page_session.locator(".psm-tooltip .maplibregl-popup-content")
    tooltip.wait_for()
    region = tooltip.bounding_box()
    assert region["x"] > divider
    shown = page_session.screenshot(clip=region)
    page_session.mouse.move(*away)
    tooltip.wait_for(state="detached")
    el.evaluate("el => psmHarness.quiet(el, 5, 'right')")
    assert page_session.screenshot(clip=region) != shown

    page_session.mouse.click(*over_point)
    popup = page_session.locator(".psm-popup .maplibregl-popup-content")
    popup.wait_for()
    page_session.mouse.move(*away)
    page_session.locator(".psm-tooltip").wait_for(state="detached")

    def hit(x, y):
        return el.evaluate(
            """(el, [x, y]) => {
                const hit = document.elementFromPoint(x, y);
                if (hit === el.psmCompare.map.getCanvas()) return 'right canvas';
                if (hit?.closest('.maplibregl-marker')) return 'marker';
                if (hit?.closest('.psm-popup')) return 'popup';
                if (hit?.closest('.psm-compare-handle')) return 'handle';
                return hit?.className ?? null;
            }""",
            [x, y],
        )

    handle = center_of(page_session, page_session.locator(HANDLE))
    popup_at = center_of(page_session, popup)
    marker_at = center_of(page_session, marker)
    # Let hit testing see the right map, which otherwise takes no input.
    el.evaluate("el => { el.psmCompare.map.getContainer().style.pointerEvents = 'auto'; }")
    try:
        assert hit(*plain) == "right canvas"
        assert hit(*marker_at) == "marker"
        assert hit(*popup_at) == "popup"
        assert hit(*handle) == "handle"
    finally:
        el.evaluate("el => { el.psmCompare.map.getContainer().style.pointerEvents = ''; }")


def test_attribution_lists_right_only_layers(harness, page_session, wait_settled):
    widget = MapWidget()
    left, right = sided_layers(widget, {}, sides=(("l", "left"), ("r", "right")))
    layers = (replace(left, attribution="L-attr"), replace(right, attribution="R-attr"))
    compare_view(page_session, wait_settled, widget, *layers)
    shows = "t => (document.querySelector('{}')?.textContent ?? '').includes(t)".format(ATTRIBUTION)
    attribution = page_session.locator(ATTRIBUTION)

    # The right map's own, and the main map's from its sources.
    page_session.wait_for_function(shows, arg="R-attr")
    page_session.wait_for_function(shows, arg="L-attr")
    # The compact control hides its text until opened.
    assert attribution.locator(MAPLIBRE_LINK).text_content() == "MapLibre"
    assert attribution.text_content().count("R-attr") == 1

    widget.publish(MapState(layers=layers))
    wait_settled(page_session, 2)
    # The main map draws both now, and lists both from its sources.
    page_session.wait_for_function(shows, arg="R-attr")
    assert "L-attr" in attribution.text_content()
    assert attribution.text_content().count("R-attr") == 1
    assert attribution.locator(MAPLIBRE_LINK).count() == 1


def test_right_half_click_hits_right_layer(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    seen = []
    widget.on_click(seen.append)
    right = polygon_layer(
        widget, "r", 15, -5, 25, 5, side="right", interaction=Interaction(popup=("name",))
    )
    left = polygon_layer(widget, "l", 15, 10, 25, 20, side="left")
    el = compare_view(page_session, wait_settled, widget, right, left)
    el.evaluate("el => psmHarness.quiet(el, 5, 'right')")
    on_right = canvas_point(page_session, 20, 0)
    # The main map draws it there, under the right map.
    on_left = canvas_point(page_session, 20, 15)
    divider = el.bounding_box()["x"] + clip_x(el)
    assert min(on_right[0], on_left[0]) > divider + 20

    page_session.mouse.click(*on_right)
    wait_for(page_session, lambda: seen, "no click arrived")
    assert seen[0].hits("r") == ({"name": "r"},)
    assert seen[0].hits("l") == ()
    assert seen[0].hidden_features == ()
    popup = page_session.locator(".psm-popup")
    popup.wait_for()
    assert popup.locator("td").inner_text() == "r"

    page_session.mouse.click(*on_left)
    wait_for(page_session, lambda: len(seen) == 2, "no second click arrived")
    assert seen[1].features == ()
    # The main map draws l under the right half, so the inspector can read it.
    assert [(h.layer_id, dict(h.properties)) for h in seen[1].hidden_features] == [
        ("l", {"name": "l"})
    ]

    # With the divider at the right edge, the main map shows there.
    page_session.locator(HANDLE).focus()
    press(page_session, "End", 100)
    page_session.mouse.click(*on_left)
    wait_for(page_session, lambda: len(seen) == 3, "no third click arrived")
    assert seen[2].hits("l") == ({"name": "l"},)
    assert seen[2].hits("r") == ()


def test_right_half_tooltip_and_cluster(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    tipped = polygon_layer(
        widget, "t", 15, -5, 25, 5, side="right", interaction=Interaction(tooltip=("name",))
    )
    # 200 points in a box of about 0.4 degrees: one bubble at this zoom.
    box = [(20 + 0.02 * i, 15 + 0.02 * j) for i in range(20) for j in range(10)]
    clustered = Layer(
        "c",
        GeoJSONSource(widget.add_payload(points(box)), cluster=Cluster(max_zoom=14)),
        side="right",
    )
    el = compare_view(page_session, wait_settled, widget, tipped, clustered)
    el.evaluate("el => psmHarness.quiet(el, 5, 'right')")
    main_layers = el.evaluate("el => el.psmMap.getLayersOrder()")
    assert not any(layer.endswith(":cluster") for layer in main_layers)

    page_session.mouse.move(*canvas_point(page_session, 20, 0))
    tooltip = page_session.locator(".psm-tooltip")
    tooltip.wait_for()
    assert tooltip.inner_text() == "t"

    bubble = """el => {
        const map = el.psmCompare.map;
        const id = map.getLayersOrder().find((layer) => layer.endsWith(':cluster'));
        const [found] = map.queryRenderedFeatures({ layers: [id] });
        return found ? found.geometry.coordinates : null;
    }"""
    wait_for(page_session, lambda: el.evaluate(bubble), "the right map drew no bubble")
    lng, lat = el.evaluate(bubble)
    zoom = el.evaluate("el => el.psmMap.getZoom()")
    page_session.mouse.click(*canvas_point(page_session, lng, lat))
    page_session.wait_for_function(
        "([el, z]) => el.psmMap.getZoom() > z + 0.5 && !el.psmMap.isMoving()", arg=[el, zoom]
    )
    main, right = cameras(el)
    assert right == pytest.approx(main, abs=1e-9)


def test_drawing_across_the_divider(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    reports, _ = record(widget)
    session = widget.draw.begin(("polygon",))
    widget.draw.start("polygon")
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "polygon")
    wait_for(page_session, lambda: len(reports) == 1, "the session was never acknowledged")
    # Two vertices each side of the divider, away from its handle.
    clicks = spread(el, (0.3, 0.25), (0.7, 0.25), (0.65, 0.7), (0.35, 0.7))
    draw_polygon(page_session, el, clicks)
    wait_for(page_session, lambda: len(reports) == 2, "the polygon never arrived")
    session.clear()
    wait_for(page_session, lambda: len(reports) == 3, "the clear was never acknowledged")

    widget.publish(MapState(compare=True))
    wait_settled(page_session, widget.state["revision"])
    wait_for(page_session, lambda: mirror(el) == [], "the mirror never started empty")
    place(page_session, el, clicks[:3])
    wait_for(
        page_session,
        lambda: mirror(el) == rendered(el),
        f"the mirror never held the polygon being drawn: {mirror(el)}",
    )
    # The polygon in progress, and the closing points at its first and last vertex.
    in_progress = [[role, g["type"]] for role, g in mirror(el)]
    assert in_progress == [["shape", "Polygon"], ["vertex", "Point"], ["vertex", "Point"]]
    place(page_session, el, clicks[3:], first=4)
    click(page_session, el, *clicks[0])
    wait_for(page_session, lambda: len(reports) == 4, "the second polygon never arrived")
    [held] = draw_state(el)["store"]
    wait_for(
        page_session,
        lambda: mirror(el) == [["shape", held["geometry"]]],
        f"the mirror never held the polygon: {mirror(el)}",
    )

    def drawn(report):
        return report["cause"], [(f["geometry"], f["properties"]) for f in report["features"]]

    assert drawn(reports[3]) == drawn(reports[1])

    session.end()
    wait_stopped(page_session, el)
    wait_for(page_session, lambda: mirror(el) == [], "the mirror kept the drawing")


def test_mirror_after_compare_on(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    _, calls = record(widget)
    widget.draw.begin(("polygon",), on_change=calls.append)
    widget.draw.start("polygon")
    [el] = show(page_session, widget)
    wait_drawing(page_session, el, "polygon")
    draw_polygon(page_session, el, spread(el, (0.3, 0.3), (0.7, 0.3), (0.6, 0.75)))
    wait_for(page_session, lambda: calls, "on_change never ran")
    [held] = draw_state(el)["store"]

    widget.publish(MapState(compare=True))
    wait_settled(page_session, widget.state["revision"])
    wait_for(
        page_session,
        lambda: mirror(el) == [["shape", held["geometry"]]],
        f"the mirror never held the polygon: {mirror(el)}",
    )


def test_mirror_follows_draw_set(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    session = widget.draw.begin(("polygon",))
    widget.publish(MapState(compare=True))
    [el] = show(page_session, widget)
    wait_settled(page_session, 1)
    wait_drawing(page_session, el, "static")

    session.set(feature(square(10, -10, 30, 10)))
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 2, "no acknowledgement")
    [held] = draw_state(el)["store"]
    wait_for(
        page_session,
        lambda: mirror(el) == [["shape", held["geometry"]]],
        f"the mirror never followed draw.set: {mirror(el)}",
    )


def test_mirror_shows_handles_in_select_mode(harness, page_session, wait_settled):
    widget = MapWidget(zoom=3)
    widget.draw.begin(("polygon",), features=[feature(square(15, -5, 25, 5))])
    widget.draw.start("select")
    widget.publish(MapState(compare=True))
    [el] = show(page_session, widget)
    wait_settled(page_session, 1)
    wait_for(page_session, lambda: widget.drawn["request_seq"] == 1, "no acknowledgement")
    wait_drawing(page_session, el, "select")

    select(page_session, el, (20, 0))
    page_session.wait_for_function(
        "el => psmHarness.drawState(el).store.some((f) => f.properties.midPoint)", arg=el
    )
    held = rendered(el)
    assert sorted(role for role, _ in held) == ["midpoint"] * 4 + ["shape"] + ["vertex"] * 4
    wait_for(page_session, lambda: mirror(el) == held, f"the mirror held {mirror(el)}")
    # The right map draws them where Terra Draw does.
    for lnglat, role in (((25, 5), "vertex"), ((25, 0), "midpoint")):
        page_session.wait_for_function(
            """([el, c, role]) => {
                const map = el.psmCompare.map;
                const p = map.project(c);
                map.triggerRepaint();
                return map.queryRenderedFeatures([p.x, p.y], { layers: ['psm-draw-mirror-point'] })
                    .some((f) => f.properties.psmRole === role);
            }""",
            arg=[el, list(lnglat), role],
        )
