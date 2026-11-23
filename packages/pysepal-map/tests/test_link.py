"""Test link_views: the link it writes on the maps, and its rules."""

import gc
import weakref

import pytest
from pysepal_map import MapWidget, link_views


def mounted(name="v"):
    widget = MapWidget()
    widget._handle_custom_msg({"type": "view_open", "view_id": name, "side": "main"}, [])
    return widget


def report(widget, cause, center=(0.0, 0.0), zoom=3.0, name="v"):
    widget._handle_custom_msg(
        {
            "type": "view_report",
            "view_id": name,
            "request_seq": widget.view_request["seq"],
            "cause": cause,
            "center": list(center),
            "zoom": zoom,
            "bounds": [-1, -1, 1, 1],
        },
        [],
    )


def seq(widget):
    return widget.view_request["seq"]


def groups(*maps):
    return [m._link.get("group") for m in maps]


def test_linked_maps_share_one_group():
    a, b, c = mounted(), mounted(), mounted()
    link_views(a, b, c)
    assert a._link["group"] and groups(a, b, c) == [a._link["group"]] * 3


def test_each_group_gets_its_own_id():
    a, b, c, d = mounted(), mounted(), mounted(), mounted()
    link_views(a, b)
    link_views(c, d)
    assert a._link["group"] != c._link["group"]


def test_the_others_take_the_first_view_and_link_after_it():
    a, b = mounted(), mounted()
    report(a, "user", center=(9, 8), zoom=7)
    link_views(a, b)
    assert b.view_request["center"] == [9, 8] and b.view_request["zoom"] == 7
    assert [m._link["seq"] for m in (a, b)] == [seq(a), seq(b)]


def test_a_pending_fit_stays_a_fit():
    a, b = MapWidget(), MapWidget()
    a.fit_bounds((1, 2, 3, 4))
    link_views(a, b)
    assert b.view_request["bounds"] == a.view_request["bounds"]


def test_python_issues_no_requests_once_linked():
    a, b = mounted(), mounted()
    link_views(a, b)
    seqs = (seq(a), seq(b))
    report(a, "user", center=(10, 20), zoom=5)
    report(b, "request")
    a.set_center(1, 2, 3)
    assert (seq(a), seq(b)) == (seqs[0] + 1, seqs[1])


def test_unlinking_clears_the_link_and_is_safe_twice():
    a, b = mounted(), mounted()
    unlink = link_views(a, b)
    unlink()
    unlink()
    assert [a._link, b._link] == [{}, {}]


def test_a_map_joins_one_group_only():
    a, b, c = mounted(), mounted(), mounted()
    link_views(a, b)
    with pytest.raises(ValueError, match="in one call"):
        link_views(b, c)
    assert c._link == {} and seq(c) == 1


@pytest.mark.parametrize("order", [(0, 1, 2), (2, 0, 1)])
def test_linking_the_same_group_again_returns_its_unlink(order):
    maps = [mounted(), mounted(), mounted()]
    unlink = link_views(*maps)
    links = [dict(m._link) for m in maps]
    issued = [seq(m) for m in maps]
    assert link_views(*(maps[i] for i in order)) is unlink
    assert [m._link for m in maps] == links
    assert [seq(m) for m in maps] == issued


@pytest.mark.parametrize("pick", [(0, 1), (0, 1, 3), (1, 3)])
def test_linking_part_or_more_of_a_group_raises(pick):
    maps = [mounted(), mounted(), mounted(), mounted()]
    link_views(*maps[:3])
    with pytest.raises(ValueError, match="in one call"):
        link_views(*(maps[i] for i in pick))
    assert maps[3]._link == {}


def test_a_group_can_be_linked_again_after_unlinking():
    a, b = mounted(), mounted()
    first = link_views(a, b)
    old = a._link["group"]
    first()
    second = link_views(a, b)
    assert second is not first
    assert a._link["group"] not in ("", old) and groups(a, b) == [a._link["group"]] * 2


def test_a_failed_link_leaves_the_maps_free(monkeypatch):
    a, b = mounted(), mounted()
    report(a, "user", center=(9, 8), zoom=7)

    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(b, "set_center", fail)
    with pytest.raises(RuntimeError, match="boom"):
        link_views(a, b)
    assert [a._link, b._link] == [{}, {}]
    monkeypatch.undo()
    link_views(a, b)
    assert groups(a, b) == [a._link["group"]] * 2


def test_a_stale_unlink_does_not_free_a_relinked_map():
    a, b, c, d = mounted(), mounted(), mounted(), mounted()
    first = link_views(a, b)
    first()
    link_views(a, c)
    first()
    assert a._link and groups(a, c) == [a._link["group"]] * 2
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


def test_a_closed_member_leaves_the_relink_to_the_living():
    a, b, c = mounted(), mounted(), mounted()
    unlink = link_views(a, b, c)
    ref = weakref.ref(c)
    c.close()
    del c
    gc.collect()
    assert ref() is None
    assert link_views(a, b) is unlink
    unlink()
    assert [a._link, b._link] == [{}, {}]
