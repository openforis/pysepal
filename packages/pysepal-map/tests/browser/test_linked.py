"""Check in a real browser that linked maps keep one camera."""

import ipywidgets as widgets
import pytest
import solara
from IPython.display import display
from pysepal_map import MapState, MapWidget
from test_compare import cameras, sided_layers, wait_for
from test_view import (
    BOX,
    camera,
    contains,
    drag,
    matches,
    middle,
    near,
    view_at,
    wait_view,
    wait_views,
)


def test_linked_widgets_follow_each_other(harness, page_session):
    one = MapWidget(height="300px")
    two = MapWidget(height="300px", center=(30, 40), zoom=4)
    display(widgets.VBox([one, two]))
    wait_views(page_session, 2)
    a, b = view_at(page_session, 0), view_at(page_session, 1)
    wait_view(page_session, one, lambda v: v["request_seq"] == one.view_request["seq"])
    wait_view(page_session, two, lambda v: v["request_seq"] == two.view_request["seq"])

    # The second takes the first's view.
    one.link_group = "g"
    two.link_group = "g"
    seqs = (one.view_request["seq"], two.view_request["seq"])
    page_session.wait_for_function(
        """([a, b]) => {
            const [p, q] = [a.psmMap, b.psmMap];
            return q.getCenter().distanceTo(p.getCenter()) < 1 && q.getZoom() === 2;
        }""",
        arg=[a, b],
    )

    # A move of one moves the other in the same call, Python out of the loop.
    followed = page_session.evaluate(
        """([a, b]) => {
            a.psmMap.jumpTo({center: [10, 20], zoom: 5});
            const c = b.psmMap.getCenter();
            return [c.lng, c.lat, b.psmMap.getZoom()];
        }""",
        [a, b],
    )
    assert near(followed, [10, 20, 5])

    # Mid-drag the other map is already there.
    x, y = middle(page_session, 1)
    page_session.mouse.move(x, y)
    page_session.mouse.down()
    page_session.mouse.move(x - 150, y + 80, steps=10)
    page_session.wait_for_function("b => Math.abs(b.psmMap.getCenter().lng - 10) > 1e-3", arg=b)
    during = page_session.evaluate(
        """([a, b]) => [a, b].map(el => {
            const c = el.psmMap.getCenter();
            return [c.lng, c.lat, el.psmMap.getZoom()];
        })""",
        [a, b],
    )
    page_session.mouse.up()
    assert near(during[0], during[1])

    # Each view reports its own camera, the follower's as the user's.
    panned = wait_view(page_session, two, matches(b))
    wait_view(
        page_session,
        one,
        lambda v: near(v["center"], panned["center"])
        and v["zoom"] == pytest.approx(panned["zoom"])
        and v["cause"] == "user",
    )
    assert (one.view_request["seq"], two.view_request["seq"]) == seqs


CAMERAS = "els => els.map(el => [el.psmMap.getCenter().lng, el.psmMap.getCenter().lat, el.psmMap.getZoom()])"


def test_two_views_of_one_widget_never_move_each_other(harness, page_session):
    one = MapWidget(height="250px", link_group="g")
    peer = MapWidget(height="250px", link_group="g")
    display(one)
    display(one)
    display(peer)
    wait_views(page_session, 3)
    views = [view_at(page_session, nth) for nth in range(3)]
    for m in (one, peer):
        wait_view(page_session, m, acknowledged(m))
    before = page_session.evaluate(CAMERAS, views)

    # In one call, so that nothing but the link can move them meanwhile.
    moved = page_session.evaluate(
        f"""([a, b, c]) => {{
            const cameras = {CAMERAS};
            a.psmMap.jumpTo({{center: [10, 20], zoom: 5}});
            const first = cameras([b, c]);
            c.psmMap.jumpTo({{center: [-30, -10], zoom: 4}});
            return [first, cameras([a, b])];
        }}""",
        views,
    )
    (other_view, peer_view), followers = moved
    assert other_view == before[1]
    assert near(peer_view, [10, 20, 5])
    for shown in followers:
        assert near(shown, [-30, -10, 4])


def test_a_member_shown_first_after_a_hidden_pan_keeps_the_pan(harness, page_session):
    a = MapWidget(height="300px", link_group="g")
    b = MapWidget(height="300px", link_group="g", center=(30, 40), zoom=4)
    box = widgets.VBox([a])
    display(box)
    wait_view(page_session, a, lambda v: v["request_seq"] == 1)

    drag(page_session, middle(page_session), (-150, 80))
    wait_view(page_session, a, lambda v: v["cause"] == "user")
    panned = wait_view(page_session, a, matches(view_at(page_session)))

    # b mounts first, so the group's camera is the one it holds.
    box.children = ()
    wait_views(page_session, 0)
    box.children = (b, a)
    wait_views(page_session, 2)
    for nth in (0, 1):
        shown = camera(view_at(page_session, nth))
        assert near(shown["center"], panned["center"]), nth
        assert shown["zoom"] == pytest.approx(panned["zoom"], abs=1e-6), nth


def acknowledged(widget):
    """A check that a view applied the widget's latest request."""
    return lambda v: v["request_seq"] == widget.view_request["seq"]


def test_a_followers_python_view_follows_a_peer_request(harness, page_session):
    a = MapWidget(height="300px", link_group="g")
    b = MapWidget(height="300px", link_group="g")
    box = widgets.VBox([a, b])
    display(box)
    wait_views(page_session, 2)
    for m in (a, b):
        wait_view(page_session, m, acknowledged(m))

    a.set_center(10, 20, 5)
    wait_view(page_session, b, lambda v: near(v["center"], [10, 20]) and v["cause"] == "link")

    # A user pans b, whose new view then follows a peer's request on that pan's seq.
    drag(page_session, middle(page_session, 1), (-150, 80))
    wait_view(page_session, b, lambda v: v["cause"] == "user")
    box.children = (a,)
    wait_views(page_session, 1)
    box.children = (a, b)
    wait_views(page_session, 2)
    view_at(page_session, 1)
    a.fit_bounds(BOX)
    fitted = wait_view(page_session, a, acknowledged(a))
    wait_view(page_session, b, lambda v: near(v["center"], fitted["center"]))


def test_a_pending_fit_inside_a_group_does_not_yank_the_group(harness, page_session):
    one = MapWidget(height="300px")
    two = MapWidget(height="100%")
    holder = widgets.VBox([two], layout=widgets.Layout(height="0px"))
    display(widgets.VBox([one, holder]))
    wait_views(page_session, 2)
    wait_view(page_session, one, acknowledged(one))
    two.fit_bounds(BOX)
    el = view_at(page_session, 1)
    page_session.wait_for_function("el => el.psmCamera.inspect().pending === 2", arg=el)
    assert two.view == {}

    # one seeds the group from its view; the fit is not newer than two's link.
    two.link_group = "g"
    one.link_group = "g"
    assert "bounds" in two.view_request
    assert two._link["seq"] == two.view_request["seq"]

    drag(page_session, middle(page_session, 0), (-150, 80))
    wait_view(page_session, one, lambda v: v["cause"] == "user")
    wait_view(page_session, one, matches(view_at(page_session, 0)))
    before = camera(view_at(page_session, 0))

    holder.layout.height = "300px"
    wait_view(page_session, two, acknowledged(two))
    after, shown = camera(view_at(page_session, 0)), camera(el)
    assert near(after["center"], before["center"])
    assert after["zoom"] == pytest.approx(before["zoom"], abs=1e-6)
    assert near(shown["center"], after["center"])
    assert shown["zoom"] == pytest.approx(after["zoom"], abs=1e-6)


def test_a_follower_reports_as_often_as_the_leader(harness, page_session):
    one = MapWidget(height="300px", link_group="g")
    two = MapWidget(height="300px", link_group="g")
    display(widgets.VBox([one, two]))
    wait_views(page_session, 2)
    for m in (one, two):
        wait_view(page_session, m, acknowledged(m))
    x, y = middle(page_session, 0)
    # The join's own reports land before the count starts.
    page_session.wait_for_timeout(600)
    seen = {"one": [], "two": []}
    one.on_view(lambda v: seen["one"].append(v["cause"]))
    two.on_view(lambda v: seen["two"].append(v["cause"]))

    # Slow enough that a follower reporting every 250 ms would report mid-drag.
    page_session.mouse.move(x, y)
    page_session.mouse.down()
    for step in range(1, 21):
        page_session.mouse.move(x - 7.5 * step, y + 4 * step)
        page_session.wait_for_timeout(30)
    page_session.mouse.up()
    wait_view(page_session, one, matches(view_at(page_session, 0)))
    wait_view(page_session, two, matches(view_at(page_session, 1)))
    page_session.wait_for_timeout(600)
    assert seen["one"] and set(seen["one"]) == {"user"}
    assert seen["two"] == seen["one"]


def same_camera(shown, center, zoom):
    return near(shown["center"], center) and shown["zoom"] == pytest.approx(zoom, abs=1e-6)


def followed(widget, seq):
    """A check that Python moved a map with no view to the group's camera."""
    return lambda: widget.view_request["seq"] == seq and widget._link["seq"] == seq


@pytest.mark.parametrize("first", ["a", "b"])
def test_mount_order_sets_the_camera(harness, page_session, first):
    maps = {
        "a": MapWidget(height="300px", link_group="g", center=(30, 40), zoom=4),
        "b": MapWidget(height="300px", link_group="g", center=(0, 0), zoom=2),
    }
    center, zoom = {"a": ((30, 40), 4), "b": ((0, 0), 2)}[first]
    shown_first = maps.pop(first)
    [shown_second] = maps.values()
    box = widgets.VBox([shown_first])
    display(box)
    wait_view(page_session, shown_first, acknowledged(shown_first))
    box.children = (shown_first, shown_second)
    wait_views(page_session, 2)
    wait_view(page_session, shown_second, acknowledged(shown_second))
    for nth in (0, 1):
        assert same_camera(camera(view_at(page_session, nth)), center, zoom), nth


def test_link_and_compare(harness, page_session, wait_settled):
    one = MapWidget(height="300px", link_group="g")
    two = MapWidget(height="300px", link_group="g")
    one.publish(MapState(layers=sided_layers(one, {}, sides=(("r", "right"),)), compare=True))
    two.publish(MapState())
    display(widgets.VBox([one, two]))
    wait_settled(page_session, 1, expected_views=2)
    el_one, el_two = view_at(page_session, 0), view_at(page_session, 1)
    page_session.wait_for_function("el => el.psmCompare?.map", arg=el_one)

    drag(page_session, middle(page_session, 1), (-150, 80))
    shown = camera(el_two)
    main, right = cameras(el_one)
    assert shown["center"][0] > 1
    assert same_camera({"center": main[:2], "zoom": main[2]}, shown["center"], shown["zoom"])
    assert right == pytest.approx(main, abs=1e-9)

    # Left of the divider, which sits in the middle.
    box = el_one.bounding_box()
    x, y = box["x"] + box["width"] / 4, box["y"] + box["height"] / 2
    page_session.wait_for_function(
        "([el, x, y]) => document.elementFromPoint(x, y)?.closest('.psm-map') === el",
        arg=[el_one, x, y],
    )
    drag(page_session, (x, y), (150, -80))
    main, right = cameras(el_one)
    assert main[0] < shown["center"][0] - 1
    assert right == pytest.approx(main, abs=1e-9)
    assert same_camera(camera(el_two), main[:2], main[2])


@pytest.mark.parametrize("peer", [True, False], ids=["with a mounted peer", "alone"])
def test_a_mounted_joiner_takes_the_groups_camera(harness, page_session, peer):
    a = MapWidget(height="300px", link_group="g")
    d = MapWidget(height="300px", center=(30, 40), zoom=4)
    box = widgets.VBox([a, d] if peer else [a])
    display(box)
    wait_view(page_session, a, acknowledged(a))
    drag(page_session, middle(page_session, 0), (-150, 80))
    wait_view(page_session, a, lambda v: v["cause"] == "user")
    panned = wait_view(page_session, a, matches(view_at(page_session, 0)))
    if not peer:
        # The group keeps a's camera with no member shown.
        box.children = ()
        wait_views(page_session, 0)
        box.children = (d,)
    el_d = view_at(page_session, 1 if peer else 0)
    wait_view(page_session, d, acknowledged(d))

    d.link_group = "g"
    wait_view(page_session, d, acknowledged(d))
    if peer:
        live = camera(view_at(page_session, 0))
        assert same_camera(live, panned["center"], panned["zoom"])
        assert same_camera(camera(el_d), live["center"], live["zoom"])
    else:
        assert same_camera(camera(el_d), panned["center"], panned["zoom"])


def test_a_fit_asked_before_a_peer_shows_moves_the_group_when_shown(harness, page_session):
    a = MapWidget(height="300px", link_group="g")
    b = MapWidget(height="300px", link_group="g", center=(30, 40), zoom=4)
    b.fit_bounds(BOX)
    fit = dict(b.view_request)
    box = widgets.VBox([a])
    display(box)
    wait_view(page_session, a, acknowledged(a))

    box.children = (a, b)
    wait_views(page_session, 2)
    wait_view(page_session, b, acknowledged(b))
    shown_a, shown_b = (camera(view_at(page_session, nth)) for nth in (0, 1))
    assert b.view_request == fit
    assert contains(shown_b["bounds"], BOX)
    assert same_camera(shown_a, shown_b["center"], shown_b["zoom"])


@pytest.mark.parametrize("case", ["two members", "three members", "no fit"])
def test_a_fit_on_a_hidden_member_moves_the_group_when_shown(harness, page_session, case):
    a = MapWidget(height="300px", link_group="g")
    b = MapWidget(height="300px", link_group="g", center=(30, 40), zoom=4)
    shown, box = [a], widgets.VBox([a])
    if case == "three members":
        c = MapWidget(height="100%", link_group="g")
        holder = widgets.VBox([c], layout=widgets.Layout(height="300px"))
        shown, box = [a, c], widgets.VBox([a, holder])
    display(box)
    wait_views(page_session, len(shown))
    for m in shown:
        wait_view(page_session, m, acknowledged(m))
    wait_for(page_session, followed(b, 2), f"b never followed: {b.view_request}")

    if case == "no fit":
        drag(page_session, middle(page_session, 0), (-150, 80))
        wait_view(page_session, a, lambda v: v["cause"] == "user")
        panned = wait_view(page_session, a, matches(view_at(page_session, 0)))
        wait_for(
            page_session,
            lambda: near(b.view_request["center"], panned["center"]),
            f"b never followed the pan: {b.view_request}",
        )
    else:
        b.fit_bounds(BOX)
    if case == "three members":
        el_c = view_at(page_session, 1)
        holder.layout.height = "200px"
        page_session.wait_for_function("el => el.clientHeight === 200", arg=el_c)
        wait_view(page_session, c, lambda v: near(v["bounds"], camera(el_c)["bounds"]))
        assert "bounds" in b.view_request

    box.children = (*box.children, b)
    wait_views(page_session, len(shown) + 1)
    wait_view(page_session, b, acknowledged(b))
    *others, shown_b = [camera(view_at(page_session, nth)) for nth in range(len(shown) + 1)]
    if case == "no fit":
        assert same_camera(shown_b, panned["center"], panned["zoom"])
    else:
        # a has b's size; c, now shorter, shows the fit's center and zoom.
        assert contains(shown_b["bounds"], BOX) and contains(others[0]["bounds"], BOX)
    for nth, other in enumerate(others):
        assert same_camera(other, shown_b["center"], shown_b["zoom"]), nth


# The maps each page of PageInGroup built, in page order.
BUILT: list[tuple[MapWidget, MapWidget]] = []


@solara.component
def PageInGroup():
    """A shown map and a hidden one in group ``g``, built in the page's own kernel."""

    def build():
        shown, hidden = (MapWidget(height="300px", link_group="g") for _ in range(2))
        BUILT.append((shown, hidden))
        return shown

    solara.display(solara.use_memo(build, []))


def test_pages_of_one_solara_server_link_apart(
    solara_server, solara_app, page_session, load_harness
):
    BUILT.clear()
    second = page_session.context.new_page()
    try:
        with solara_app(f"{__name__}:PageInGroup"):
            for page in (page_session, second):
                page.goto(solara_server.base_url)
                page.wait_for_function("document.querySelector('.psm-map')?.psmMap")
                load_harness(page)
            (shown, hidden), (other_shown, other_hidden) = BUILT
            assert shown._link["group"] != other_shown._link["group"]
            for m in (hidden, other_hidden):
                wait_for(page_session, followed(m, 2), f"never followed: {m.view_request}")
            before = dict(other_hidden.view_request)

            drag(page_session, middle(page_session), (-150, 80))
            wait_view(page_session, shown, lambda v: v["cause"] == "user")
            panned = wait_view(page_session, shown, matches(view_at(page_session)))
            wait_for(
                page_session,
                lambda: near(hidden.view_request["center"], panned["center"]),
                f"the hidden map never followed the pan: {hidden.view_request}",
            )
            assert other_hidden.view_request == before
    finally:
        BUILT.clear()
        second.close()
        page_session.goto("about:blank")
