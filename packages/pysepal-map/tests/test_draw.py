"""Drawing: the tools Python declares, and the features the views report."""

import math
import re
import uuid

import pytest
import traitlets
from pysepal_map import DRAW_MODES, Draw, MapWidget

UUID4 = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")


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


def recorded(widget):
    seen = []
    widget.on_draw(seen.append)
    return seen


def test_drawing_starts_off_and_empty():
    widget = MapWidget()
    assert isinstance(widget.draw, Draw)
    assert DRAW_MODES == ("polygon", "rectangle", "circle", "linestring", "point")
    assert widget.drawing == {"modes": [], "mode": "static", "color": "#3388ff"}
    assert widget.draw_request == {"seq": 0, "features": []}
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert (widget.draw.modes, widget.draw.mode, widget.draw.color) == ((), "static", "#3388ff")
    assert widget.draw.features == collection([])


@pytest.mark.parametrize("name", ["drawing", "draw_request", "drawn"])
def test_drawing_traits_are_read_only(name):
    with pytest.raises(traitlets.TraitError):
        setattr(MapWidget(), name, {})


def test_each_widget_has_its_own_drawing():
    one, two = MapWidget(), MapWidget()
    one.draw.enable()
    assert one.draw is not two.draw and two.draw.modes == ()


@pytest.mark.parametrize("modes", [(), ("hexagon",), ("polygon", "polygon"), "polygon"])
def test_enable_validates_modes(modes):
    widget = MapWidget()
    with pytest.raises(ValueError):
        widget.draw.enable(modes)
    assert widget.drawing["modes"] == []


def test_enable_offers_the_tools_with_select_last():
    widget = MapWidget()
    widget.draw.enable()
    assert widget.draw.modes == ("polygon", "rectangle", "circle", "select")
    widget.draw.start("circle")
    widget.draw.enable(("point", "linestring"), edit=False)
    assert widget.draw.modes == ("point", "linestring")
    assert widget.draw.mode == "static"
    assert widget.drawing == {
        "modes": ["point", "linestring"],
        "mode": "static",
        "color": "#3388ff",
    }


def test_start_requires_enabled_mode():
    widget = MapWidget()
    with pytest.raises(ValueError):
        widget.draw.start("polygon")
    widget.draw.enable(("point",), edit=False)
    for mode in ("polygon", "select", "static"):
        with pytest.raises(ValueError):
            widget.draw.start(mode)
    widget.draw.start("point")
    assert widget.draw.mode == "point"
    widget.draw.stop()
    assert widget.draw.mode == "static"
    widget.draw.enable(("point",))
    widget.draw.start("select")
    assert widget.drawing["mode"] == "select"


def test_disable_keeps_features():
    widget = MapWidget()
    widget.draw.enable()
    widget.draw.start("polygon")
    widget.draw.set(feature(polygon()))
    before = widget.draw.features
    widget.draw.disable()
    assert (widget.draw.modes, widget.draw.mode) == ((), "static")
    assert widget.draw.features == before
    assert widget.draw_request["seq"] == 1


def test_set_color():
    widget = MapWidget()
    widget.draw.set_color("#ff0000")
    assert widget.draw.color == "#ff0000" == widget.drawing["color"]
    for bad in ("", None, 3):
        with pytest.raises(ValueError):
            widget.draw.set_color(bad)
    assert widget.draw.color == "#ff0000"


def test_set_splits_multipolygon_and_tags_mode():
    widget = MapWidget()
    original = str(uuid.uuid4())
    multi = {"type": "MultiPolygon", "coordinates": [[ring(0, 0, 1, 1)], [ring(2, 2, 3, 3)]]}
    lines = {"type": "MultiLineString", "coordinates": [[[0, 0], [1, 1]], [[2, 2], [3, 3]]]}
    points = {"type": "MultiPoint", "coordinates": [[0, 0], [1, 1]]}
    widget.draw.set(
        [
            feature(multi, {"name": "x", "mode": "circle", "selected": True}, id=original),
            feature(lines),
            feature(points, {"n": 1}),
        ]
    )
    features = widget.draw_request["features"]
    assert [f["geometry"]["type"] for f in features] == ["Polygon"] * 2 + ["LineString"] * 2 + [
        "Point"
    ] * 2
    assert [f["properties"] for f in features] == [
        {"name": "x", "mode": "polygon"},
        {"name": "x", "mode": "polygon"},
        {"mode": "linestring"},
        {"mode": "linestring"},
        {"n": 1, "mode": "point"},
        {"n": 1, "mode": "point"},
    ]
    assert features[1]["geometry"]["coordinates"] == [ring(2, 2, 3, 3)]
    ids = [f["id"] for f in features]
    assert ids[0] == original
    assert len(set(ids)) == 6 and all(UUID4.fullmatch(i) for i in ids)
    assert all(f["type"] == "Feature" for f in features)


def test_set_accepts_a_collection_a_feature_or_a_sequence():
    widget = MapWidget()
    one = feature(polygon())
    widget.draw.set(collection([one, one]))
    assert len(widget.draw_request["features"]) == 2
    widget.draw.set(one)
    assert len(widget.draw_request["features"]) == 1
    widget.draw.set((one,))
    assert widget.draw_request["seq"] == 3
    for bad in ("polygon", {"type": "Polygon", "coordinates": [ring()]}, 3, [3]):
        with pytest.raises(ValueError):
            widget.draw.set(bad)
    assert widget.draw_request["seq"] == 3


def test_set_drops_the_property_names_terra_draw_reserves():
    widget = MapWidget()
    reserved = {
        "mode": "select",
        "selected": True,
        "midPoint": True,
        "selectionPoint": True,
        "selectionPointFeatureId": "x",
        "currentlyDrawing": True,
        "edited": True,
        "closingPoint": True,
        "snappingPoint": True,
        "coordinatePoint": True,
        "coordinatePointFeatureId": "x",
        "coordinatePointIds": ["x"],
        "provisionalCoordinateCount": 1,
        "committedCoordinateCount": 1,
        "marker": True,
    }
    widget.draw.set(feature(polygon(), {**reserved, "keep": [1, {"a": None}]}))
    assert widget.draw_request["features"][0]["properties"] == {
        "keep": [1, {"a": None}],
        "mode": "polygon",
    }


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
    widget.draw.set(feature(polygon()))
    before = widget.draw_request
    with pytest.raises(ValueError):
        widget.draw.set([feature(polygon()), feature(polygon()), feature(bad)])
    assert widget.draw_request == before


def test_set_rejects_properties_json_cannot_carry():
    widget = MapWidget()
    for properties in ({"x": math.nan}, {"x": object()}, "props"):
        with pytest.raises(ValueError):
            widget.draw.set(feature(polygon(), properties))
    assert widget.draw_request["seq"] == 0


def test_set_replaces_non_uuid_ids():
    widget = MapWidget()
    kept = str(uuid.uuid4())
    ids = ["a", 7, kept, kept, str(uuid.uuid1()), None, kept.upper()]
    widget.draw.set([feature(polygon(), id=i) for i in ids])
    out = [f["id"] for f in widget.draw_request["features"]]
    assert out[2] == kept and out[6] == kept.upper()
    assert len(set(out)) == len(ids)
    assert all(UUID4.fullmatch(i.lower()) for i in out)


def test_set_rounds_precision():
    widget = MapWidget()
    # Terra Draw keeps 9 decimals the way Math.round(x * 1e9) / 1e9 does,
    # which differs from Python's round() for some values.
    widget.draw.set(
        feature(
            {"type": "LineString", "coordinates": [[-1.0000000005, 12.3456789015], [1.5e-9, 0]]}
        )
    )
    assert widget.draw_request["features"][0]["geometry"]["coordinates"] == [
        [-1.0, 12.345678902],
        [2e-9, 0.0],
    ]
    widget.draw.set(feature({"type": "Point", "coordinates": [360.1 - 360, 1 / 3]}))
    assert widget.draw_request["features"][0]["geometry"]["coordinates"] == [0.1, 0.333333333]


def test_set_checks_the_ring_after_rounding():
    widget = MapWidget()
    almost = [[0, 0], [1, 0], [1, 1], [1e-10, 0]]
    widget.draw.set(feature(polygon(almost)))
    assert widget.draw_request["features"][0]["geometry"]["coordinates"][0][-1] == [0.0, 0.0]


def test_clear_empties_the_drawing():
    widget = MapWidget()
    widget.draw.set(feature(polygon()))
    widget.draw.clear()
    assert widget.draw_request == {"seq": 2, "features": []}
    assert widget.draw.features == collection([])


def test_features_follow_request_until_acknowledged():
    widget = mounted()
    widget.draw.set(feature(polygon()))
    assert widget.draw.features == collection(widget.draw_request["features"])
    b = drawn(polygon(ring(5, 5, 6, 6)))
    report(widget, [b], cause="request")
    assert widget.draw.features == collection([b])
    assert widget.drawn == {"request_seq": 1, "features": [b]}


def test_a_report_drops_a_feature_with_an_out_of_range_coordinate():
    widget = mounted()
    widget.draw.set(feature(polygon()))
    good = drawn(polygon(ring(5, 5, 6, 6)))
    for huge in (1e300, 10**400):
        bad = drawn({"type": "Point", "coordinates": [huge, 0]}, mode="point")
        report(widget, [bad, good], cause="request")
        assert widget.draw.features == collection([good])


def test_features_are_a_copy():
    widget = mounted()
    widget.draw.set(feature(polygon()))
    widget.draw.features["features"][0]["properties"]["x"] = 1
    assert "x" not in widget.draw_request["features"][0]["properties"]


def test_report_on_older_request_is_dropped():
    widget = mounted()
    seen = recorded(widget)
    widget.draw.set(feature(polygon()))
    request = widget.draw_request["features"]
    report(widget, [drawn(polygon(ring(5, 5, 6, 6)))], seq=0, cause="user")
    assert widget.draw.features == collection(request)
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert seen == []


def test_user_edit_beats_late_ack():
    widget = mounted("a", "b")
    seen = recorded(widget)
    widget.draw.set(feature(polygon()))
    seed = widget.draw_request["features"]
    report(widget, seed, view="a", cause="request")
    edit = drawn(polygon(ring(0, 0, 2, 2)))
    report(widget, [edit], view="a", cause="user")
    report(widget, seed, view="b", cause="request")
    assert widget.draw.features == collection([edit])
    assert widget.drawn["request_seq"] == 1
    assert seen == [collection([edit])]


def test_a_later_user_edit_replaces_an_earlier_one():
    widget = mounted("a", "b")
    first, second = drawn(polygon()), drawn(polygon(ring(3, 3, 4, 4)))
    report(widget, [first], view="a")
    report(widget, [second], view="b")
    assert widget.draw.features == collection([second])


def test_user_report_fires_on_draw_and_request_ack_does_not():
    widget = mounted()
    seen = recorded(widget)
    widget.draw.set(feature(polygon()))
    report(widget, widget.draw_request["features"], cause="request")
    assert seen == []
    edit = drawn(polygon(ring(0, 0, 3, 3)))
    report(widget, [edit])
    assert seen == [collection([edit])]
    seen[0]["features"].clear()
    assert widget.drawn["features"] == [edit]
    widget.on_draw(seen.append, remove=True)
    report(widget, [])
    assert len(seen) == 1


def test_reentrant_observer_keeps_callback_order():
    widget = mounted()
    seen = recorded(widget)
    first, second = drawn(polygon()), drawn(polygon(ring(4, 4, 5, 5)))
    fed = []

    def feed(change):
        if not fed:
            fed.append(True)
            content = {
                "type": "draw_report",
                "view_id": "a",
                "side": "main",
                "request_seq": 0,
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
    seen = recorded(widget)
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
        {"request_seq": 1},
        {"cause": "resize"},
        {"features": "x"},
        {"features": None},
        {"side": "left"},
        {"view_id": None},
    ],
)
def test_malformed_draw_reports_are_ignored(content):
    widget = mounted()
    seen = recorded(widget)
    base = {
        "type": "draw_report",
        "view_id": "a",
        "side": "main",
        "request_seq": 0,
        "cause": "user",
        "features": [drawn(polygon())],
    }
    msg(widget, **{**base, **content})
    assert widget.drawn == {"request_seq": 0, "features": []}
    assert seen == []


def test_invalid_report_features_are_dropped():
    widget = mounted()
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


def test_report_features_keep_a_drawing_mode_that_fits_their_geometry():
    widget = mounted()
    rectangle = drawn(polygon(), mode="rectangle", name="r")
    wrong = drawn(polygon(), mode="point")
    unknown = drawn({"type": "Point", "coordinates": [0, 0]}, mode="select", selected=True)
    report(widget, [rectangle, wrong, unknown])
    modes = [f["properties"] for f in widget.drawn["features"]]
    assert modes == [{"mode": "rectangle", "name": "r"}, {"mode": "polygon"}, {"mode": "point"}]


def test_report_features_get_new_ids_where_terra_draw_would_reject_theirs():
    widget = mounted()
    one = drawn(polygon())
    report(widget, [one, {**one}, {**one, "id": 3}])
    ids = [f["id"] for f in widget.drawn["features"]]
    assert ids[0] == one["id"] and len(set(ids)) == 3


def test_a_failing_draw_callback_is_logged(caplog):
    widget = mounted()

    def boom(_):
        raise RuntimeError("boom")

    widget.on_draw(boom)
    report(widget, [drawn(polygon())])
    assert "a callback failed" in caplog.text
    assert len(widget.drawn["features"]) == 1


def test_closed_widget_drops_draw_reports():
    widget = mounted()
    widget.close()
    report(widget, [drawn(polygon())])
    assert widget.drawn == {"request_seq": 0, "features": []}
