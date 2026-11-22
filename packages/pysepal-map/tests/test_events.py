"""Clicks, the cursor and the highlight marker."""

import asyncio
import math

import pytest
import traitlets
from pysepal_map import (
    ClickEvent,
    Controls,
    FeatureHit,
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
)


def msg(widget, **content):
    widget._handle_custom_msg(content, [])


def mounted(view="a"):
    widget = MapWidget()
    msg(widget, type="view_open", view_id=view, side="main")
    return widget


def publish(widget, layer_id="v"):
    widget.publish(MapState(layers=(Layer(layer_id, GeoJSONSource(widget.add_payload(b"{}"))),)))
    return next(x for x in widget.state["layers"] if x["id"] == layer_id)["instance"]


def click(widget, view="a", **change):
    content = {
        "type": "click",
        "view_id": view,
        "side": "main",
        "lnglat": [10.0, 20.0],
        "zoom": 4.0,
        "settled": True,
        "features": [],
    }
    msg(widget, **{**content, **change})


def recorded(widget):
    seen = []
    widget.on_click(seen.append)
    return seen


def test_click_from_mounted_view_reaches_callback():
    widget = mounted()
    instance = publish(widget)
    seen = recorded(widget)
    click(widget, features=[{"id": "v", "instance": instance, "properties": {"name": "a"}}])
    assert len(seen) == 1
    event = seen[0]
    assert isinstance(event, ClickEvent)
    assert (event.lng, event.lat, event.view_id) == (10.0, 20.0, "a")
    assert event.features == (FeatureHit("v", instance, {"name": "a"}),)
    assert event.hits("v") == ({"name": "a"},)
    assert event.hits("other") == ()
    with pytest.raises(TypeError):
        event.features[0].properties["name"] = "b"


def test_click_from_unknown_view_is_dropped():
    widget = mounted("a")
    seen = recorded(widget)
    click(widget, view="b")
    assert seen == []


@pytest.mark.parametrize(
    "lnglat", [None, [1], [0, 91], [0, -91], ["a", 0], [math.nan, 0], [0, math.inf], "ab"]
)
def test_click_with_bad_lnglat_is_dropped(lnglat):
    widget = mounted()
    seen = recorded(widget)
    click(widget, lnglat=lnglat)
    assert seen == []


def test_hit_on_retired_instance_is_dropped():
    widget = mounted()
    old = publish(widget)
    widget.publish(
        MapState(layers=(Layer("v", GeoJSONSource(widget.add_payload(b"{}")), token=1),))
    )
    seen = recorded(widget)
    click(widget, features=[{"id": "v", "instance": old, "properties": {}}])
    assert seen[0].features == ()


def test_retired_hit_marks_layer_stale():
    widget = mounted()
    old = publish(widget)
    widget.publish(MapState())
    seen = recorded(widget)
    click(
        widget,
        features=[
            {"id": "v", "instance": old, "properties": {}},
            "junk",
            {"id": "v", "instance": "x", "properties": {}},
            {"id": "v", "instance": 1, "properties": []},
        ],
    )
    assert seen[0].features == ()
    assert seen[0].stale == frozenset({"v"})


def test_click_carries_view_zoom_and_settled():
    widget = mounted()
    seen = recorded(widget)
    click(widget, zoom=7.5, settled=False)
    assert (seen[0].zoom, seen[0].settled) == (7.5, False)


@pytest.mark.parametrize(
    "change",
    [{"zoom": "a"}, {"zoom": math.nan}, {"zoom": None}, {"settled": 1}, {"settled": None}],
)
def test_click_with_bad_zoom_or_settled_is_dropped(change):
    widget = mounted()
    seen = recorded(widget)
    click(widget, **change)
    assert seen == []


def test_click_registration_rules():
    widget = mounted()
    seen = []
    widget.on_click(seen.append)
    widget.on_click(seen.append)
    click(widget)
    assert len(seen) == 1
    widget.on_click(seen.append, remove=True)
    click(widget)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_async_click_callback_runs_on_loop():
    widget = mounted()
    done = asyncio.Event()
    ran = []

    async def callback(event):
        await asyncio.sleep(0)
        ran.append((asyncio.get_running_loop(), event.lng))
        done.set()

    widget.on_click(callback)
    click(widget)
    await asyncio.wait_for(done.wait(), 5)
    assert ran == [(asyncio.get_running_loop(), 10.0)]
    widget.close()


def test_set_marker_validates_and_publishes():
    widget = MapWidget()
    assert widget.marker == {}
    widget.set_marker(10, 20)
    assert widget.marker == {"lnglat": [10.0, 20.0], "color": "#3388ff"}
    widget.set_marker(-3.5, 90, color="#ff0000")
    assert widget.marker == {"lnglat": [-3.5, 90.0], "color": "#ff0000"}
    for lng, lat in [(math.nan, 0), (0, math.inf), (0, 91), (0, -91)]:
        with pytest.raises(ValueError):
            widget.set_marker(lng, lat)
    assert widget.marker["lnglat"] == [-3.5, 90.0]
    with pytest.raises(traitlets.TraitError):
        widget.marker = {}


def test_clear_marker():
    widget = MapWidget()
    widget.set_marker(1, 2)
    widget.clear_marker()
    assert widget.marker == {}


def test_cursor_rejects_unknown_value():
    widget = MapWidget()
    assert widget.cursor == ""
    widget.cursor = "crosshair"
    with pytest.raises(traitlets.TraitError):
        widget.cursor = "grab"


def test_controls_json_has_coordinates():
    assert Controls().to_json()["coordinates"] is False
    assert Controls(coordinates=True).to_json()["coordinates"] is True
