"""Drawing: the sessions Python begins, and the features the views report."""

import dataclasses
import math
import uuid

import pytest
import traitlets
from pysepal_map import DRAW_MODES, Draw, DrawSession, MapWidget


def msg(widget, **content):
    widget._handle_custom_msg(content, [])


def mounted(*views):
    widget = MapWidget()
    for view in views or ("a",):
        msg(widget, type="view_open", view_id=view, side="main")
    return widget


def ring(west=0.0, south=0.0, east=1.0, north=1.0):
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def polygon(*rings):
    return {"type": "Polygon", "coordinates": list(rings) or [ring()]}


def feature(geometry, properties=None, **extra):
    return {"type": "Feature", "properties": properties or {}, "geometry": geometry, **extra}


def drawn(geometry, mode="polygon", **properties):
    """A feature as a view reports it."""
    return feature(geometry, {"mode": mode, **properties}, id=str(uuid.uuid4()))


def report(widget, features, *, view="a", seq=None, cause="user"):
    msg(
        widget,
        type="draw_report",
        view_id=view,
        side="main",
        request_seq=widget.draw_request["seq"] if seq is None else seq,
        cause=cause,
        features=features,
    )


def collection(features):
    return {"type": "FeatureCollection", "features": features}


LABELS = {
    "polygon": "Draw a polygon",
    "rectangle": "Draw a rectangle",
    "circle": "Draw a circle",
    "linestring": "Draw a line",
    "point": "Draw a point",
    "select": "Select and edit shapes",
    "clear": "Remove all shapes",
}


def traits(widget):
    return widget.drawing, widget.draw_request, widget.drawn


def test_drawing_starts_off_and_empty():
    widget = MapWidget()
    assert isinstance(widget.draw, Draw)
    assert DRAW_MODES == ("polygon", "rectangle", "circle", "linestring", "point")
    assert widget.drawing == {"session": 0, "modes": [], "color": "#3388ff", "labels": LABELS}
    assert widget.draw_request == {"seq": 0, "features": []}
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert widget.draw_tool == {"seq": 0, "session": 0, "mode": "static"}
    assert (widget.draw.modes, widget.draw.color) == ((), "#3388ff")
    assert widget.draw.features == collection([])
    assert widget.draw._session is None


@pytest.mark.parametrize("name", ["drawing", "draw_request", "drawn", "draw_tool"])
def test_drawing_traits_are_read_only(name):
    with pytest.raises(traitlets.TraitError):
        setattr(MapWidget(), name, {})


def test_each_widget_has_its_own_drawing():
    one, two = MapWidget(), MapWidget()
    one.draw.begin()
    assert one.draw is not two.draw and two.draw.modes == ()


@pytest.mark.parametrize("modes", [(), ("hexagon",), ("polygon", "polygon"), "polygon"])
def test_begin_validates_modes(modes):
    widget = MapWidget()
    with pytest.raises(ValueError):
        widget.draw.begin(modes)
    assert widget.drawing["modes"] == [] and widget.drawing["session"] == 0


def test_begin_offers_the_tools_and_seeds_the_features():
    widget = MapWidget()
    seeds = [
        feature(polygon(), {"name": "a"}),
        feature({"type": "Point", "coordinates": [1.0, 2.0]}, id="p"),
    ]
    session = widget.draw.begin(("point", "linestring"), features=seeds)
    assert isinstance(session, DrawSession) and session.active
    assert widget.draw._session is session
    assert widget.draw.modes == ("point", "linestring", "select")
    assert widget.drawing == {
        "session": 1,
        "modes": ["point", "linestring", "select"],
        "color": "#3388ff",
        "labels": LABELS,
    }
    assert widget.draw_request == {"seq": 1, "features": seeds}
    assert session.features == widget.draw.features == collection(seeds)

    session.start("point")
    widget.draw.begin(edit=False)
    assert widget.draw.modes == ("polygon", "rectangle", "circle")
    assert widget.drawing["session"] == 2
    assert widget.draw_request == {"seq": 2, "features": []}


@dataclasses.dataclass
class SpyComm:
    """A comm with a kernel, so the widget sends its state changes, which it records."""

    comm_id = "spy"
    kernel = True
    sent: list = dataclasses.field(default_factory=list)

    def send(self, data=None, buffers=None):
        self.sent.append(data)

    def on_msg(self, callback):
        pass

    def close(self, *args, **kwargs):
        pass

    def updates(self):
        return [set(m["state"]) for m in self.sent if m.get("method") == "update"]


def test_begin_and_end_write_one_message():
    widget = MapWidget()
    # Solara's test comm has no kernel, so nothing would be sent at all.
    widget.comm = comm = SpyComm()
    session = widget.draw.begin(features=[feature(polygon())])
    assert comm.updates() == [{"drawing", "draw_request"}]
    comm.sent.clear()
    session.end()
    assert comm.updates() == [{"drawing", "draw_request"}]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"modes": ()},
        {"modes": ("hexagon",)},
        {"features": [feature(polygon(ring(), ring(0.2, 0.2, 0.4, 0.4)))]},
    ],
    ids=["no modes", "bad mode", "holed polygon"],
)
def test_a_failed_begin_changes_nothing(kwargs):
    widget = mounted()
    session = widget.draw.begin(("point",), features=[feature(polygon())])
    before = traits(widget)
    with pytest.raises(ValueError):
        widget.draw.begin(**kwargs)
    assert session.active and widget.draw._session is session
    assert traits(widget) == before


def test_begin_ends_the_previous_session():
    widget = mounted()
    old = widget.draw.begin(features=[feature(polygon())])
    new = widget.draw.begin(("point",))
    assert old.active is False and new.active
    assert old.features == collection([])
    for call in (lambda: old.set([]), old.clear):
        with pytest.raises(RuntimeError):
            call()
    before = traits(widget)
    old.end()
    assert traits(widget) == before
    assert new.active and widget.draw._session is new


def test_end_hides_the_tools_and_drops_late_reports():
    widget = mounted()
    seen = []
    session = widget.draw.begin(on_change=seen.append)
    session.start("polygon")
    first = drawn(polygon())
    report(widget, [first])
    assert seen == [collection([first])]
    seq = widget.draw_request["seq"]

    session.end()
    assert session.active is False and widget.draw._session is None
    assert widget.drawing == {"session": 1, "modes": [], "color": "#3388ff", "labels": LABELS}
    assert widget.draw_request == {"seq": seq + 1, "features": []}
    assert session.features == widget.draw.features == collection([])

    report(widget, [drawn(polygon(ring(3, 3, 4, 4)))], seq=seq)
    assert widget.drawn == {"request_seq": seq, "features": [first]}
    assert session.features == collection([])
    assert len(seen) == 1
    for call in (lambda: session.start("polygon"), session.stop):
        with pytest.raises(RuntimeError):
            call()
    before = traits(widget)
    session.end()
    assert traits(widget) == before


def test_on_change_runs_for_user_reports_of_the_active_session_only():
    widget = mounted()
    first_calls, second_calls = [], []
    widget.draw.begin(features=[feature(polygon())], on_change=first_calls.append)
    report(widget, widget.draw_request["features"], cause="request")
    assert first_calls == []
    edit = drawn(polygon(ring(0, 0, 2, 2)))
    report(widget, [edit])
    assert first_calls == [collection([edit])]

    old_seq = widget.draw_request["seq"]
    second = widget.draw.begin(on_change=second_calls.append)
    report(widget, [drawn(polygon())], seq=old_seq)
    mine = drawn(polygon(ring(5, 5, 6, 6)))
    report(widget, [mine])
    assert first_calls == [collection([edit])]
    assert second_calls == [collection([mine])]
    assert second.features == collection([mine])


def test_start_and_stop_write_numbered_tool_requests():
    widget = MapWidget()
    session = widget.draw.begin(("point",), edit=False)
    before = traits(widget)
    for mode in ("polygon", "select", "static"):
        with pytest.raises(ValueError):
            session.start(mode)
    assert widget.draw_tool == {"seq": 0, "session": 0, "mode": "static"}

    session.start("point")
    assert widget.draw_tool == {"seq": 1, "session": 1, "mode": "point"}
    session.stop()
    assert widget.draw_tool == {"seq": 2, "session": 1, "mode": "static"}
    assert traits(widget) == before

    second = widget.draw.begin(("point",))
    assert widget.draw_tool["seq"] == 2
    second.start("select")
    assert widget.draw_tool == {"seq": 3, "session": 2, "mode": "select"}
    second.end()
    for ended in (session, second):
        for call in (lambda: ended.start("point"), ended.stop):
            with pytest.raises(RuntimeError):
                call()
    assert widget.draw_tool == {"seq": 3, "session": 2, "mode": "select"}


def test_labels_travel_in_drawing():
    widget = MapWidget()
    assert widget.drawing["labels"] == LABELS
    widget.draw.set_labels({"polygon": "Forme libre", "select": "Modifier"})
    widget.draw.set_labels({"clear": "Tout effacer", "select": "Choisir"})
    want = {**LABELS, "polygon": "Forme libre", "select": "Choisir", "clear": "Tout effacer"}
    assert widget.drawing["labels"] == want
    widget.draw.begin().end()
    assert widget.drawing["labels"] == want

    before = widget.drawing
    for bad in ({"hexagon": "x"}, {"static": "x"}, {"point": ""}, {"point": None}, {"point": 3}):
        with pytest.raises(ValueError):
            widget.draw.set_labels({"polygon": "kept out", **bad})
    assert widget.drawing == before
    assert MapWidget().drawing["labels"] == LABELS


def test_drawing_has_no_mode():
    widget = MapWidget()
    session = widget.draw.begin()
    session.start("polygon")
    assert "mode" not in widget.drawing
    session.end()
    assert "mode" not in widget.drawing
    for name in ("start", "stop", "mode"):
        assert not hasattr(Draw, name)


def test_set_color():
    widget = MapWidget()
    widget.draw.set_color("#ff0000")
    assert widget.draw.color == "#ff0000" == widget.drawing["color"]
    for bad in ("", None, 3):
        with pytest.raises(ValueError):
            widget.draw.set_color(bad)
    assert widget.draw.color == "#ff0000"
    widget.draw.begin()
    assert widget.draw.color == "#ff0000"


def test_set_splits_multi_geometries():
    widget = MapWidget()
    session = widget.draw.begin()
    multi = {"type": "MultiPolygon", "coordinates": [[ring(0, 0, 1, 1)], [ring(2, 2, 3, 3)]]}
    lines = {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]}
    points = {"type": "MultiPoint", "coordinates": [[0, 0], [1, 1]]}
    session.set(
        [
            feature(multi, {"name": "x", "mode": "circle"}, id="m"),
            feature(lines),
            feature(points, {"n": 1}),
        ]
    )
    features = widget.draw_request["features"]
    assert [f["geometry"]["type"] for f in features] == ["Polygon"] * 2 + ["LineString"] * 2 + [
        "Point"
    ] * 2
    assert [f["properties"] for f in features] == [{"name": "x", "mode": "circle"}] * 2 + [
        {}
    ] * 2 + [{"n": 1}] * 2
    assert [f.get("id") for f in features] == ["m", "m", None, None, None, None]
    assert features[1]["geometry"]["coordinates"] == [ring(2, 2, 3, 3)]
    assert features[5]["geometry"]["coordinates"] == [1, 1]
    assert all(f["type"] == "Feature" for f in features)


def test_set_keeps_ids_properties_and_coordinates():
    widget = MapWidget()
    session = widget.draw.begin()
    precise = [
        [0.123456789012, 0.0],
        [1.0, 0.0],
        [1.0, 1.000000000001],
        [0.123456789012, 0.0],
    ]
    properties = {"selected": True, "mode": "select", "keep": [1, {"a": None}]}
    session.set(feature(polygon(precise), properties, id="not-a-uuid"))
    assert widget.draw_request["features"] == [
        {
            "type": "Feature",
            "id": "not-a-uuid",
            "geometry": polygon(precise),
            "properties": properties,
        }
    ]


def test_set_accepts_a_collection_a_feature_or_a_sequence():
    widget = MapWidget()
    session = widget.draw.begin()
    one = feature(polygon())
    session.set(collection([one, one]))
    assert len(widget.draw_request["features"]) == 2
    session.set(one)
    assert len(widget.draw_request["features"]) == 1
    session.set((one,))
    assert widget.draw_request["seq"] == 4
    for bad in ("polygon", {"type": "Polygon", "coordinates": [ring()]}, 3, [3]):
        with pytest.raises(ValueError):
            session.set(bad)
    assert widget.draw_request["seq"] == 4


@pytest.mark.parametrize(
    "bad",
    [
        polygon(ring(), ring(0.2, 0.2, 0.4, 0.4)),
        polygon(ring()[:-1]),
        polygon([[0, 0], [1, 0], [0, 0]]),
        polygon([[0, 0], [1, math.nan], [1, 1], [0, 0]]),
        polygon([[0, 0], [1, math.inf], [1, 1], [0, 0]]),
        polygon([[0, 0], [190, 0], [1, 1], [0, 0]]),
        polygon([[0, 0], [1, 91], [1, 1], [0, 0]]),
        polygon([[0, 0, 5], [1, 0, 5], [1, 1, 5], [0, 0, 5]]),
        polygon([[0, 0], [True, 0], [1, 1], [0, 0]]),
        polygon([[0, 0], [1, 0], [1, 1], [1e-10, 0]]),
        {"type": "LineString", "coordinates": [[0, 0]]},
        {"type": "Point", "coordinates": [0, "1"]},
        {"type": "Point", "coordinates": [1e300, 0]},
        {"type": "Point", "coordinates": [10**400, 0]},
        {"type": "GeometryCollection", "geometries": []},
        None,
    ],
)
def test_set_rejects_bad_geometry_atomically(bad):
    widget = MapWidget()
    session = widget.draw.begin(features=[feature(polygon())])
    before = widget.draw_request
    with pytest.raises(ValueError):
        session.set([feature(polygon()), feature(polygon()), feature(bad)])
    assert widget.draw_request == before


def test_set_rejects_properties_json_cannot_carry():
    widget = MapWidget()
    session = widget.draw.begin()
    for properties in ({"x": math.nan}, {"x": object()}, "props"):
        with pytest.raises(ValueError):
            session.set(feature(polygon(), properties))
    assert widget.draw_request["seq"] == 1


def test_clear_empties_the_drawing():
    widget = MapWidget()
    session = widget.draw.begin(features=[feature(polygon())])
    session.clear()
    assert widget.draw_request == {"seq": 2, "features": []}
    assert session.features == collection([])


def test_features_follow_request_until_acknowledged():
    widget = mounted()
    session = widget.draw.begin(features=[feature(polygon())])
    assert session.features == collection(widget.draw_request["features"])
    b = drawn(polygon(ring(5, 5, 6, 6)))
    report(widget, [b], cause="request")
    assert session.features == widget.draw.features == collection([b])
    assert widget.drawn == {"request_seq": 1, "features": [b]}


def test_a_report_drops_a_feature_with_an_out_of_range_coordinate():
    widget = mounted()
    session = widget.draw.begin(features=[feature(polygon())])
    good = drawn(polygon(ring(5, 5, 6, 6)))
    for huge in (1e300, 10**400):
        bad = drawn({"type": "Point", "coordinates": [huge, 0]}, mode="point")
        report(widget, [bad, good], cause="request")
        assert session.features == collection([good])


def test_features_are_a_copy():
    widget = mounted()
    session = widget.draw.begin(features=[feature(polygon())])
    session.features["features"][0]["properties"]["x"] = 1
    widget.draw.features["features"][0]["properties"]["x"] = 1
    assert "x" not in widget.draw_request["features"][0]["properties"]


def test_report_on_older_request_is_dropped():
    widget = mounted()
    seen = []
    session = widget.draw.begin(on_change=seen.append)
    session.set(feature(polygon()))
    request = widget.draw_request["features"]
    report(widget, [drawn(polygon(ring(5, 5, 6, 6)))], seq=1, cause="user")
    assert session.features == collection(request)
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert seen == []


def test_user_edit_beats_late_ack():
    widget = mounted("a", "b")
    seen = []
    session = widget.draw.begin(features=[feature(polygon())], on_change=seen.append)
    seed = widget.draw_request["features"]
    report(widget, seed, view="a", cause="request")
    edit = drawn(polygon(ring(0, 0, 2, 2)))
    report(widget, [edit], view="a", cause="user")
    report(widget, seed, view="b", cause="request")
    assert session.features == collection([edit])
    assert widget.drawn["request_seq"] == 1
    assert seen == [collection([edit])]


def test_a_later_user_edit_replaces_an_earlier_one():
    widget = mounted("a", "b")
    session = widget.draw.begin()
    first, second = drawn(polygon()), drawn(polygon(ring(3, 3, 4, 4)))
    report(widget, [first], view="a")
    report(widget, [second], view="b")
    assert session.features == collection([second])


def test_user_report_runs_on_change_and_request_ack_does_not():
    widget = mounted()
    seen = []
    widget.draw.begin(features=[feature(polygon())], on_change=seen.append)
    report(widget, widget.draw_request["features"], cause="request")
    assert seen == []
    edit = drawn(polygon(ring(0, 0, 3, 3)))
    report(widget, [edit])
    assert seen == [collection([edit])]
    seen[0]["features"].clear()
    assert widget.drawn["features"] == [edit]


def test_reentrant_observer_keeps_callback_order():
    widget = mounted()
    seen = []
    widget.draw.begin(on_change=seen.append)
    first, second = drawn(polygon()), drawn(polygon(ring(4, 4, 5, 5)))
    fed = []

    def feed(change):
        if not fed:
            fed.append(True)
            content = {
                "type": "draw_report",
                "view_id": "a",
                "side": "main",
                "request_seq": 1,
                "cause": "user",
                "features": [second],
            }
            widget._on_message(widget, content, [])

    widget.observe(feed, "drawn")
    report(widget, [first])
    assert seen == [collection([first]), collection([second])]
    assert widget.drawn["features"] == [second]


def test_report_from_unmounted_view_is_dropped():
    widget = mounted("a")
    seen = []
    widget.draw.begin(on_change=seen.append)
    report(widget, [drawn(polygon())], view="b")
    msg(widget, type="view_close", view_id="a", side="main")
    report(widget, [drawn(polygon())], view="a")
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert seen == []


@pytest.mark.parametrize(
    "content",
    [
        {"request_seq": -1},
        {"request_seq": True},
        {"request_seq": 2},
        {"cause": "resize"},
        {"features": "x"},
        {"features": None},
        {"side": "left"},
        {"view_id": None},
    ],
)
def test_malformed_draw_reports_are_ignored(content):
    widget = mounted()
    seen = []
    widget.draw.begin(on_change=seen.append)
    base = {
        "type": "draw_report",
        "view_id": "a",
        "side": "main",
        "request_seq": 1,
        "cause": "user",
        "features": [drawn(polygon())],
    }
    msg(widget, **{**base, **content})
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert seen == []


def test_invalid_report_features_are_dropped():
    widget = mounted()
    widget.draw.begin()
    good = drawn(polygon())
    line = drawn({"type": "LineString", "coordinates": [[0, 0], [1, 1]]}, mode="linestring")
    bad = [
        "x",
        {"type": "Foo", "geometry": polygon(), "properties": {}},
        drawn({"type": "MultiPolygon", "coordinates": [[ring()]]}),
        drawn(polygon([[0, 0], [190, 0], [1, 1], [0, 0]])),
        drawn(polygon(ring()[:-1])),
        drawn(polygon(ring(), ring(0.2, 0.2, 0.4, 0.4))),
        drawn({"type": "LineString", "coordinates": [[0, 0]]}),
        drawn({"type": "Point", "coordinates": [math.nan, 0]}),
        drawn(None),
    ]
    report(widget, [bad[0], good, *bad[1:], line])
    assert widget.drawn["features"] == [good, line]


def test_report_features_keep_their_ids_and_properties():
    widget = mounted()
    widget.draw.begin()
    rectangle = drawn(polygon(), mode="rectangle", name="r")
    other = drawn(polygon(), mode="point")
    report(widget, [rectangle, other])
    assert widget.drawn["features"] == [rectangle, other]


def test_a_failing_on_change_is_logged(caplog):
    widget = mounted()

    def boom(_):
        raise RuntimeError("boom")

    widget.draw.begin(on_change=boom)
    report(widget, [drawn(polygon())])
    assert "a callback failed" in caplog.text
    assert len(widget.drawn["features"]) == 1


def test_closed_widget_drops_draw_reports():
    widget = mounted()
    widget.draw.begin()
    widget.close()
    report(widget, [drawn(polygon())], seq=1)
    assert widget.drawn == {"request_seq": 0, "features": []}
