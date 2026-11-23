"""Test link_group: the link it writes on the maps, and Python's fallback for hidden members."""

import contextlib
import gc
import re
import weakref

import pytest
from pysepal_map import MapWidget, widget


class FakeKernel:
    """A kernel stand-in; ``object()`` and ``SimpleNamespace`` take no weak references."""


def open_view(m, name="v"):
    m._handle_custom_msg({"type": "view_open", "view_id": name, "side": "main"}, [])


def close_view(m, name="v"):
    m._handle_custom_msg({"type": "view_close", "view_id": name, "side": "main"}, [])


def mounted(link_group=None, name="v", **kwargs):
    m = MapWidget(link_group=link_group, **kwargs)
    open_view(m, name)
    return m


def report(m, cause="user", center=(0.0, 0.0), zoom=3.0, name="v"):
    m._handle_custom_msg(
        {
            "type": "view_report",
            "view_id": name,
            "request_seq": m.view_request["seq"],
            "cause": cause,
            "center": list(center),
            "zoom": zoom,
            "bounds": [-1, -1, 1, 1],
        },
        [],
    )


def seq(m):
    return m.view_request["seq"]


@contextlib.contextmanager
def sends(m):
    """The keys of each ``send_state`` call of ``m`` meanwhile; nothing is sent."""
    sent = []

    def spy(key=None):
        # hold_sync passes its own set, and clears it after the call.
        sent.append(set(key) if isinstance(key, (set, list, tuple)) else {key})

    # The test comm has no kernel, and a widget sends no state without one.
    kernel, m.comm.kernel = m.comm.kernel, object()
    m.send_state = spy
    try:
        yield sent
    finally:
        del m.send_state
        m.comm.kernel = kernel


def test_link_group_writes_the_group_and_the_request_seq(monkeypatch):
    monkeypatch.setattr(widget, "_current_kernel", lambda: None)
    m = MapWidget(link_group="g")
    assert re.fullmatch("[0-9a-f]{32}", widget._PROCESS)
    assert m._link == {"group": f"{widget._PROCESS}:g", "seq": 1}
    assert m.link_group == "g"

    m.set_center(1, 2)
    m.link_group = "h"
    assert m._link == {"group": f"{widget._PROCESS}:h", "seq": 2}
    assert m.link_group == "h"


def test_groups_are_scoped_by_kernel(monkeypatch):
    k1, k2 = FakeKernel(), FakeKernel()

    def built_in(kernel, **kwargs):
        monkeypatch.setattr(widget, "_current_kernel", lambda: kernel)
        return MapWidget(**kwargs)

    a = built_in(k1, link_group="g")
    open_view(a)
    b = built_in(k2, link_group="g")
    c = built_in(k1, link_group="g")
    assert a._link["group"] == c._link["group"] != b._link["group"]
    assert a._link["group"].endswith(":g") and b._link["group"].endswith(":g")

    report(a, center=(10, 20), zoom=5)
    assert c.view_request["center"] == [10, 20] and seq(b) == 1

    late = built_in(k2, link_group="g")
    assert late.view_request["center"] == [0, 0]


def test_none_clears_the_link():
    a, b = mounted("g"), MapWidget(link_group="g")
    assert a._link["group"].endswith(":g")
    a.link_group = None
    assert a._link == {} and a.link_group is None

    report(a, center=(10, 20), zoom=5)
    assert seq(b) == 1


def test_setting_the_same_group_changes_nothing():
    m = MapWidget(link_group="g")
    m.set_center(1, 2)
    m.link_group = "g"
    assert m._link["seq"] == 1 and seq(m) == 2


@pytest.mark.parametrize("name", ["", 3, b"g"])
def test_link_group_rejects_bad_names(name):
    with pytest.raises(ValueError):
        MapWidget(link_group=name)
    m = MapWidget(link_group="g")
    link = dict(m._link)
    with pytest.raises(ValueError):
        m.link_group = name
    assert m._link == link and m.link_group == "g"


def test_a_report_moves_the_members_with_no_view():
    a, d = mounted("g"), mounted("g")
    b, c = MapWidget(link_group="g"), MapWidget(link_group="g")
    report(a, center=(10, 20), zoom=5)
    for m in (b, c):
        assert m.view_request == {"seq": 2, "center": [10, 20], "zoom": 5}
        assert m._link["seq"] == m.view_request["seq"]
    assert (seq(a), seq(d)) == (1, 1)


def test_the_fallback_sends_the_request_and_the_link_together():
    a, b = mounted("g"), MapWidget(link_group="g")
    with sends(b) as sent:
        report(a, center=(10, 20), zoom=5)
    assert len(sent) == 1 and {"view_request", "_link"} <= sent[0]


def test_the_fallback_skips_other_groups_closed_maps_and_dropped_reports():
    a = mounted("g")
    other, closed, hidden = (MapWidget(link_group=g) for g in ("h", "g", "g"))
    closed.close()

    report(a, center=(10, 20), zoom=5, name="not-mounted")
    assert a.view == {} and seq(hidden) == 1
    # A resize is accepted, but it keeps the camera.
    report(a, "resize", center=(10, 20), zoom=5)
    assert a.view["cause"] == "resize" and seq(hidden) == 1

    report(a, center=(10, 20), zoom=5)
    assert (seq(hidden), seq(other), seq(closed)) == (2, 1, 1)


@pytest.mark.parametrize("center, zoom", [((10, 95), 5), ((10, 20), 30)])
def test_a_bad_report_moves_nobody(center, zoom):
    a, b = mounted("g"), MapWidget(link_group="g")
    report(a, center=center, zoom=zoom)
    assert a.view == {} and seq(b) == 1


def test_a_failing_peer_does_not_stop_the_others(monkeypatch, caplog):
    a, b, c = mounted("g"), MapWidget(link_group="g"), MapWidget(link_group="g")

    def fail(*args):
        raise RuntimeError("boom")

    monkeypatch.setattr(b, "_follow", fail)
    with caplog.at_level("ERROR", logger="pysepal_map"):
        report(a, center=(10, 20), zoom=5)
    assert c.view_request["center"] == [10, 20]
    assert "boom" in caplog.text
    assert a.view["center"] == [10, 20]


def test_the_fallback_skips_a_peer_already_there():
    a, d, b = mounted("g"), mounted("g"), MapWidget(link_group="g")
    report(a, center=(10, 20), zoom=5)
    report(d, center=(10, 20), zoom=5)
    assert seq(b) == 2


def test_a_move_back_to_an_earlier_camera_is_forwarded():
    a, b = mounted("g"), MapWidget(link_group="g")
    report(a, center=(10, 20), zoom=5)
    assert seq(b) == 2

    open_view(b)
    report(b, center=(50, 50), zoom=5)
    close_view(b)

    report(a, center=(10, 20), zoom=5)
    assert b.view_request == {"seq": 3, "center": [10, 20], "zoom": 5}


def test_the_fallback_stops_once_a_view_mounts():
    a, b, c = mounted("g"), MapWidget(link_group="g"), MapWidget(link_group="g")
    open_view(b)
    report(a, center=(10, 20), zoom=5)
    assert (seq(b), seq(c)) == (1, 2)


def test_a_late_joiner_takes_the_groups_camera():
    a = mounted("g")
    report(a, center=(10, 20), zoom=5)

    late = MapWidget(link_group="g", center=(0, 0), zoom=2)
    assert late.view_request == {"seq": 1, "center": [10, 20], "zoom": 5}
    assert late._link["seq"] == 1

    c = MapWidget()
    c.link_group = "g"
    assert c.view_request == {"seq": 2, "center": [10, 20], "zoom": 5}
    assert c._link["seq"] == 2

    # Mounted, and in no group yet.
    d = mounted()
    report(d, center=(0, 0), zoom=3)
    with sends(d) as sent:
        d.link_group = "g"
    assert (d.view_request["center"], d.view_request["zoom"]) == ([10, 20], 5)
    assert d._link["seq"] == d.view_request["seq"]
    assert len(sent) == 1 and {"view_request", "_link"} <= sent[0]

    refs = [weakref.ref(m) for m in (a, late, c, d)]
    for m in (a, late, c, d):
        m.close()
    del a, late, c, d, m
    gc.collect()
    assert [r() for r in refs] == [None] * 4
    assert MapWidget(link_group="g", center=(3, 4)).view_request["center"] == [3, 4]


def test_the_first_joiner_with_a_view_sets_the_groups_camera():
    a = mounted()
    report(a, center=(9, 8), zoom=7)
    a.link_group = "g"
    assert seq(a) == 1 and a._link["seq"] == 1

    b = MapWidget()
    b.link_group = "g"
    assert b.view_request == {"seq": 2, "center": [9, 8], "zoom": 7}

    # Every member leaves, so the group forgets its camera; a sets it again.
    a.link_group = None
    b.link_group = None
    a.link_group = "g"
    b.link_group = "g"
    assert seq(a) == 1
    assert b.view_request == {"seq": 3, "center": [9, 8], "zoom": 7}

    # A pending request never sets the camera.
    c, d = MapWidget(), MapWidget()
    c.fit_bounds((1, 2, 3, 4))
    fit = dict(c.view_request)
    c.link_group = "h"
    d.link_group = "h"
    assert c.view_request == fit and seq(d) == 1


def test_a_forward_during_the_join_is_not_lost(monkeypatch):
    a = mounted("g")
    report(a, center=(5, 5), zoom=4)
    b = MapWidget()
    set_center = b.set_center
    calls = []

    def racing(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            # Reaches b before its _link is written, so it skips b.
            report(a, center=(1, 2), zoom=3)
        set_center(*args, **kwargs)

    monkeypatch.setattr(b, "set_center", racing)
    b.link_group = "g"
    assert (b.view_request["center"], b.view_request["zoom"]) == ([1, 2], 3)
    assert b._link["seq"] == seq(b)


def test_a_forward_while_the_comm_opens_is_not_lost(monkeypatch):
    a = mounted("g")
    report(a, center=(5, 5), zoom=4)
    open_comm = MapWidget.open

    def racing(self):
        # Reaches the new map after it joined, before its comm is open.
        report(a, center=(1, 2), zoom=3)
        open_comm(self)

    monkeypatch.setattr(MapWidget, "open", racing)
    b = MapWidget(link_group="g")
    assert b.view_request == {"seq": 2, "center": [1, 2], "zoom": 3}
    assert b._link["seq"] == 2


def test_no_two_locks_are_held(monkeypatch):
    a, b = mounted("g"), MapWidget(link_group="g")
    held = []
    follow = b._follow

    def check(*args):
        held.append((a._lock._is_owned(), widget._LINK_LOCK.locked()))
        follow(*args)

    monkeypatch.setattr(b, "_follow", check)
    report(a, center=(10, 20), zoom=5)
    assert held == [(False, False)]

    # A joiner takes the group's camera with only its own lock.
    c = MapWidget()
    take_camera = c._take_camera

    def take(*args):
        held.append((c._lock._is_owned(), widget._LINK_LOCK.locked()))
        take_camera(*args)

    monkeypatch.setattr(c, "_take_camera", take)
    c.link_group = "g"
    assert held[1:] == [(True, False)]


def test_a_linked_map_can_be_collected_once_closed():
    # ipywidgets keeps open widgets alive, so only the link registry is under test.
    a, b = mounted("g"), MapWidget(link_group="g")
    report(a, center=(10, 20), zoom=5)
    refs = [weakref.ref(a), weakref.ref(b)]
    a.close()
    b.close()
    del a, b
    gc.collect()
    assert [r() for r in refs] == [None, None]
    assert widget._LINK_MEMBERS == {} and widget._LINK_CAMERAS == {}
