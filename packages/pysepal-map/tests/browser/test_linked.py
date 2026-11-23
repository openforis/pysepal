"""Check in a real browser that linked maps keep one camera."""

import ipywidgets as widgets
import pytest
from IPython.display import display
from pysepal_map import MapWidget
from test_view import (
    camera,
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
