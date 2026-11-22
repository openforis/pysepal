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
    b.set_center(60, 60, 3)
    app_seq = seq(b)
    a.set_center(1, 1, 2)
    ack(a, center=(1, 1), zoom=2)
    # The group's request on b is newer than the app's, which b acknowledges late.
    assert seq(b) > app_seq
    before = seq(a)
    report(b, app_seq, "request", center=(60, 60), zoom=3)
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
    with pytest.raises(ValueError, match="in one call"):
        link_views(b, c)
    assert seq(c) == 1


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 0, 1)])
def test_linking_the_same_group_again_returns_its_unlink(order):
    maps = [mounted(), mounted(), mounted()]
    ack(maps[0], center=(9, 8), zoom=7)
    unlink = link_views(*maps)
    maps[0].set_center(1, 2, 3)
    issued = [seq(w) for w in maps]
    assert link_views(*(maps[i] for i in order)) is unlink
    assert [seq(w) for w in maps] == issued
    unlink()
    report(maps[0], seq(maps[0]), "user", center=(10, 20), zoom=5)
    assert [seq(w) for w in maps] == issued


@pytest.mark.parametrize("pick", [(0, 1), (0, 1, 3), (1, 3)])
def test_linking_part_or_more_of_a_group_raises(pick):
    maps = [mounted(), mounted(), mounted(), mounted()]
    link_views(*maps[:3])
    with pytest.raises(ValueError, match="in one call"):
        link_views(*(maps[i] for i in pick))
    assert seq(maps[3]) == 1


def test_a_group_can_be_linked_again_after_unlinking():
    a, b = mounted(), mounted()
    first = link_views(a, b)
    first()
    ack(a, center=(4, 5), zoom=6)
    second = link_views(a, b)
    assert second is not first
    assert b.view_request["center"] == [4, 5]
    ack(a)
    ack(b)
    before = seq(b)
    report(a, seq(a), "user", center=(10, 20), zoom=5)
    assert seq(b) == before + 1


def test_a_failed_link_leaves_the_maps_free(monkeypatch):
    a, b = mounted(), mounted()
    ack(a, center=(9, 8), zoom=7)

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(b, "set_center", fail)
    with pytest.raises(RuntimeError, match="boom"):
        link_views(a, b)
    monkeypatch.undo()
    unlink = link_views(a, b)
    assert b.view_request["center"] == [9, 8]
    ack(a)
    ack(b)
    before = seq(b)
    report(a, seq(a), "user", center=(10, 20), zoom=5)
    assert seq(b) == before + 1
    unlink()


def test_a_stale_unlink_does_not_free_a_relinked_map():
    a, b, c, d = mounted(), mounted(), mounted(), mounted()
    first = link_views(a, b)
    first()
    link_views(a, c)
    first()
    with pytest.raises(ValueError):
        link_views(a, d)


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


def test_a_closed_member_is_collected_while_the_other_lives():
    a, b = mounted(), mounted()
    link_views(a, b)
    ref = weakref.ref(b)
    b.close()
    del b
    gc.collect()
    assert ref() is None
    assert a.comm is not None
