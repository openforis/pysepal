"""Test link_views against reports fed through the widget's message handler."""

import gc
import weakref

import pytest
from pysepal_map import MapWidget, link_views


def mounted(name="v"):
    widget = MapWidget()
    widget._handle_custom_msg({"type": "view_open", "view_id": name, "side": "main"}, [])
    return widget


def report(widget, seq, cause, center=(0.0, 0.0), zoom=3.0, name="v"):
    widget._handle_custom_msg(
        {
            "type": "view_report",
            "view_id": name,
            "request_seq": seq,
            "cause": cause,
            "center": list(center),
            "zoom": zoom,
            "bounds": [-1, -1, 1, 1],
        },
        [],
    )


def seq(widget):
    return widget.view_request["seq"]


def ack(widget, cause="request", **kwargs):
    report(widget, seq(widget), cause, **kwargs)


def test_a_user_move_issues_one_request_on_the_other():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(a)
    ack(b)
    before = seq(b)
    report(a, seq(a), "user", center=(10, 20), zoom=5)
    assert seq(b) == before + 1
    assert b.view_request["center"] == [10, 20]
    assert b.view_request["zoom"] == 5


def test_the_acknowledgement_of_a_forwarded_request_issues_nothing_back():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(a)
    ack(b)
    report(a, seq(a), "user", center=(10, 20), zoom=5)
    issued = (seq(a), seq(b))
    ack(b, center=(10, 20), zoom=5)
    assert (seq(a), seq(b)) == issued


def test_an_app_request_acknowledged_moves_the_other_once():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(a)
    ack(b)
    a.set_center(7, 8, 4)
    before = seq(b)
    ack(a, center=(7, 8), zoom=4)
    assert seq(b) == before + 1
    assert b.view_request["center"] == [7, 8]
    ack(b, center=(7, 8), zoom=4)
    ack(a, center=(7, 8), zoom=4)
    assert seq(b) == before + 1


def test_a_group_of_three_moves_the_others_once_each():
    a, b, c = mounted(), mounted(), mounted()
    link_views(a, b, c)
    for w in (a, b, c):
        ack(w)
    before = [seq(w) for w in (a, b, c)]
    report(b, seq(b), "user", center=(3, 4), zoom=6)
    assert [seq(w) for w in (a, b, c)] == [before[0] + 1, before[1], before[2] + 1]
    ack(a, center=(3, 4), zoom=6)
    ack(c, center=(3, 4), zoom=6)
    assert [seq(w) for w in (a, b, c)] == [before[0] + 1, before[1], before[2] + 1]


def test_acknowledgements_of_requests_before_the_link_issue_nothing():
    a, b = mounted(), mounted()
    link_views(a, b)
    issued = (seq(a), seq(b))
    report(a, 1, "request")
    report(b, 1, "request")
    assert (seq(a), seq(b)) == issued


def test_a_pending_fit_stays_a_fit_and_its_echo_stays_in_b():
    a, b = mounted(), mounted()
    a.fit_bounds((10, 10, 20, 20), padding=5)
    link_views(a, b)
    assert b.view_request["bounds"] == a.view_request["bounds"]
    assert b.view_request["padding"] == 5
    issued = (seq(a), seq(b))
    ack(b, center=(15, 15), zoom=4)
    assert (seq(a), seq(b)) == issued
    assert a.view_request["bounds"] == b.view_request["bounds"]


def test_the_others_take_the_first_view_at_link_time():
    a, b = mounted(), mounted()
    ack(a, center=(9, 8), zoom=7)
    link_views(a, b)
    assert b.view_request["center"] == [9, 8]
    assert b.view_request["zoom"] == 7


def test_a_user_report_below_the_groups_seq_is_superseded():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(b)
    a.set_center(1, 1, 2)
    ack(a, center=(1, 1), zoom=2)
    # b now has a request from the group; a user report on an older one is stale.
    assert seq(b) > 1
    before = seq(a)
    report(b, seq(b) - 1, "user", center=(50, 50), zoom=9)
    assert seq(a) == before


def test_an_acknowledgement_older_than_the_groups_seq_issues_nothing():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(b)
    a.set_center(1, 1, 2)
    ack(a, center=(1, 1), zoom=2)
    b.set_center(60, 60, 3)
    # The group issued seq on b after b's app request, so b's ack of its own is newer;
    # an ack on a request below the group's seq is what stays quiet.
    before = seq(a)
    report(b, seq(b) - 1, "request", center=(1, 1), zoom=2)
    assert seq(a) == before


def test_resize_reports_issue_nothing():
    a, b = mounted(), mounted()
    link_views(a, b)
    ack(a)
    ack(b)
    issued = (seq(a), seq(b))
    ack(a, cause="resize", center=(30, 30), zoom=8)
    ack(b, cause="resize", center=(30, 30), zoom=8)
    assert (seq(a), seq(b)) == issued


def test_nothing_is_forwarded_after_unlinking():
    a, b = mounted(), mounted()
    unlink = link_views(a, b)
    ack(a)
    ack(b)
    unlink()
    unlink()
    before = seq(b)
    report(a, seq(a), "user", center=(10, 20), zoom=5)
    assert seq(b) == before
    link_views(a, b)


def test_a_map_joins_one_group_only():
    a, b, c = mounted(), mounted(), mounted()
    link_views(a, b)
    with pytest.raises(ValueError):
        link_views(b, c)
    assert seq(c) == 1


@pytest.mark.parametrize("count", [0, 1])
def test_too_few_maps_raise(count):
    with pytest.raises(ValueError):
        link_views(*[MapWidget() for _ in range(count)])


def test_the_same_map_twice_raises():
    a = MapWidget()
    with pytest.raises(ValueError):
        link_views(a, a)


def test_a_linked_pair_can_be_collected_once_closed():
    # ipywidgets keeps open widgets alive, so only the group is under test.
    a, b = mounted(), mounted()
    link_views(a, b)
    refs = [weakref.ref(a), weakref.ref(b)]
    a.close()
    b.close()
    del a, b
    gc.collect()
    assert [r() for r in refs] == [None, None]
