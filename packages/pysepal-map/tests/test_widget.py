"""Test the MapWidget snapshot bookkeeping, payload replies and layer status."""

import asyncio
import dataclasses
import gc
import hashlib
import json
import os
import sys
import threading
import weakref

import ipywidgets
import ipywidgets.widgets.widget as widget_registry
import pytest
from pysepal_map import (
    GeoJSONSource,
    Layer,
    LayerStatus,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)


def geo(widget, data=b"{}", **kw):
    return Layer("v", GeoJSONSource(widget.add_payload(data)), **kw)


def instance(widget, layer_id="v"):
    return next(x for x in widget.state["layers"] if x["id"] == layer_id)["instance"]


def test_add_payload_returns_the_sha256():
    widget = MapWidget()
    digest = widget.add_payload(b"abc")
    assert digest == hashlib.sha256(b"abc").hexdigest()
    assert widget.add_payload(b"abc") == digest
    assert widget._payloads == {digest: b"abc"}


def test_publish_increments_revision():
    widget = MapWidget()
    widget.publish(MapState())
    assert widget.state["revision"] == 1
    widget.publish(MapState())
    assert widget.state["revision"] == 2


def test_publish_with_unknown_digest_raises_keyerror():
    widget = MapWidget()
    with pytest.raises(KeyError, match="deadbeef"):
        widget.publish(MapState(layers=(Layer("v", GeoJSONSource("deadbeef")),)))
    assert widget.state == {}


def test_publish_drops_unreferenced_payloads():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.add_payload(b"orphan")
    widget.publish(MapState(layers=(layer,)))
    assert list(widget._payloads) == [layer.source.digest]
    widget.publish(MapState())
    assert widget._payloads == {}


def test_invalid_publish_preserves_previous_snapshot_and_bytes():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.publish(MapState(layers=(layer,)))
    before = dict(widget.state)
    extra = widget.add_payload(b"new")
    with pytest.raises(ValueError):
        MapState(layers=(dataclasses.replace(layer, opacity=float("nan")),))
    with pytest.raises(KeyError):
        widget.publish(MapState(layers=(layer, Layer("w", GeoJSONSource("nope")))))
    with pytest.raises(TypeError):
        widget.publish({"layers": []})
    assert widget.state == before
    assert set(widget._payloads) == {layer.source.digest, extra}
    widget.publish(MapState(layers=(layer,)))
    assert widget.state["revision"] == 2
    assert instance(widget) == 1


def test_readd_with_default_token_allocates_new_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.publish(MapState(layers=(layer,)))
    assert instance(widget) == 1
    widget.publish(MapState())
    widget.add_payload(b"{}")
    widget.publish(MapState(layers=(layer,)))
    assert instance(widget) == 2


def test_paint_only_changes_preserve_the_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.publish(MapState(layers=(layer,)))
    changed = dataclasses.replace(
        layer, paint=VectorPaint(stroke="#f00"), opacity=0.5, visible=False
    )
    widget.publish(MapState(layers=(changed,)))
    assert instance(widget) == 1


@pytest.mark.parametrize("change", ["digest", "url", "attribution", "token"])
def test_source_attribution_and_token_changes_retire_the_instance(change):
    widget = MapWidget()
    if change == "digest":
        layer = geo(widget, b"1")
        new = None
    else:
        layer = Layer("v", PMTilesSource("https://x/a.pmtiles", "roads"))
        new = {
            "url": dataclasses.replace(layer, source=PMTilesSource("https://x/b.pmtiles", "roads")),
            "attribution": dataclasses.replace(layer, attribution="x"),
            "token": dataclasses.replace(layer, token=1),
        }[change]
    widget.publish(MapState(layers=(layer,)))
    if change == "digest":
        new = geo(widget, b"2")
    widget.publish(MapState(layers=(new,)))
    assert instance(widget) == 2


def capture_sends(monkeypatch, widget):
    sent = []
    monkeypatch.setattr(
        widget, "send", lambda content, buffers=None: sent.append((content, buffers))
    )
    return sent


def test_pull_answers_with_buffers(monkeypatch):
    widget = MapWidget()
    data = b'{"type": "FeatureCollection", "features": []}'
    layer = geo(widget, data)
    widget.publish(MapState(layers=(layer,)))
    sent = capture_sends(monkeypatch, widget)
    digest = layer.source.digest
    widget._handle_custom_msg({"type": "pull", "digests": [digest]}, [])
    assert sent == [({"type": "data", "digest": digest}, [data])]


def test_pull_of_a_dropped_digest_answers_missing(monkeypatch):
    widget = MapWidget()
    kept = geo(widget, b"kept")
    dropped = Layer("w", GeoJSONSource(widget.add_payload(b"dropped")))
    widget.publish(MapState(layers=(kept, dropped)))
    widget.publish(MapState(layers=(kept,)))
    sent = capture_sends(monkeypatch, widget)
    digests = [dropped.source.digest, kept.source.digest]
    widget._handle_custom_msg({"type": "pull", "digests": digests}, [])
    assert sent == [
        ({"type": "data", "digest": dropped.source.digest, "missing": True}, []),
        ({"type": "data", "digest": kept.source.digest}, [b"kept"]),
    ]


def test_pull_after_close_does_not_raise(monkeypatch):
    widget = MapWidget()
    layer = geo(widget)
    widget.publish(MapState(layers=(layer,)))
    sent = capture_sends(monkeypatch, widget)
    widget.close()
    widget._handle_custom_msg({"type": "pull", "digests": [layer.source.digest]}, [])
    assert sent == []


@pytest.mark.parametrize(
    "content",
    [{"type": "pull"}, {"type": "pull", "digests": "abc"}, {"type": "other"}, []],
)
def test_malformed_messages_are_ignored(monkeypatch, content):
    widget = MapWidget()
    sent = capture_sends(monkeypatch, widget)
    widget._handle_custom_msg(content, [])
    assert sent == []


GEOJSON_A = b'{"type": "FeatureCollection", "features": []}'
GEOJSON_B = b'{"type": "Point", "coordinates": [1, 2]}'


def pulled(monkeypatch, widget, digest):
    """Send a pull for ``digest``: the bytes of the data reply, or None if missing."""
    sent = capture_sends(monkeypatch, widget)
    widget._handle_custom_msg({"type": "pull", "digests": [digest]}, [])
    [(content, buffers)] = sent
    return None if content.get("missing") else buffers[0]


def test_nested_publish_keeps_its_payloads(monkeypatch):
    """A draw made by a `state` observer during an outer draw keeps the payloads it references."""
    w = MapWidget()
    outer = w.add_payload(GEOJSON_A)
    inner = {}

    def nested(_change):
        if not inner:
            inner["d"] = w.add_payload(GEOJSON_B)
            w.publish(MapState(layers=(Layer("b", GeoJSONSource(inner["d"])),)))

    w.observe(nested, "state")
    w.publish(MapState(layers=(Layer("a", GeoJSONSource(outer)),)))
    assert [layer["id"] for layer in w.state["layers"]] == ["b"]
    assert pulled(monkeypatch, w, inner["d"]) == GEOJSON_B


def test_instances_follow_input_order_and_keep_across_reorder():
    widget = MapWidget()
    a = Layer("a", RasterSource(("t",)))
    b = Layer("b", RasterSource(("u",)))
    widget.publish(MapState(layers=(a, b)))
    widget.publish(MapState(layers=(b, a)))
    assert instance(widget, "a") == 1
    assert instance(widget, "b") == 2


@pytest.fixture
def frequent_switches():
    """Switch threads as often as the interpreter allows."""
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    yield
    sys.setswitchinterval(previous)


def test_concurrent_draws_publish_whole_ordered_snapshots(frequent_switches):
    widget = MapWidget()
    shared = widget.add_payload(b"{}")
    published = []
    widget.observe(lambda change: published.append(change["new"]), "state")
    threads, draws = 8, 25
    barrier = threading.Barrier(threads)

    def draw_many(n):
        barrier.wait()
        for i in range(draws):
            raster = Layer("r", RasterSource((f"https://t/{n}/{i}/{{z}}/{{x}}/{{y}}.png",)))
            vector = Layer("g", GeoJSONSource(shared), token=n * draws + i)
            widget.publish(MapState(layers=(raster, vector)))

    workers = [threading.Thread(target=draw_many, args=(n,)) for n in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert [state["revision"] for state in published] == list(range(1, threads * draws + 1))
    descriptors: dict[int, set] = {}
    for state in published:
        for layer in state["layers"]:
            source = json.dumps(layer["source"], sort_keys=True)
            descriptor = (layer["id"], source, layer["attribution"], layer["token"])
            descriptors.setdefault(layer["instance"], set()).add(descriptor)
    assert all(len(shared_by) == 1 for shared_by in descriptors.values())
    assert widget.state == published[-1]
    current = {x["id"]: (x["token"], x["instance"]) for x in widget.state["layers"]}
    assert widget._current == current


@pytest.fixture
def board(monkeypatch, loop):
    """A widget with one raster layer, its outgoing messages and callbacks."""
    widget = MapWidget(loop=loop)
    sent = capture_sends(monkeypatch, widget)
    calls = []
    widget.on_status(lambda status: calls.append(dict(status)))
    widget.publish(MapState(layers=(Layer("r", RasterSource(("t",))),)))
    return widget, sent, calls


def msg(widget, **content):
    widget._handle_custom_msg(content, [])


def open_view(widget, view, side="main"):
    msg(widget, type="view_open", view_id=view, side=side)


def close_view(widget, view, side="main"):
    msg(widget, type="view_close", view_id=view, side=side)


def report(widget, view, status, layer_id="r", side="main", error=None, **kw):
    current = next(x for x in widget.state["layers"] if x["id"] == layer_id)
    content = {
        "type": "status",
        "view_id": view,
        "side": side,
        "id": layer_id,
        "token": current["token"],
        "instance": current["instance"],
        "status": status,
        "error": error,
    }
    msg(widget, **{**content, **kw})


def status_of(widget, layer_id="r"):
    status = widget.layer_status.get(layer_id)
    return None if status is None else (status.status, status.error)


def test_layer_status_is_empty_without_views(board):
    widget, _, calls = board
    assert widget.layer_status == {}
    report(widget, "a", "ready")
    assert widget.layer_status == {}
    assert calls == []


def test_an_enrolled_view_is_loading_until_it_reports(board):
    widget, sent, calls = board
    open_view(widget, "a")
    assert sent == [({"type": "status_request", "view_id": "a", "side": "main"}, None)]
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 1)}
    report(widget, "a", "ready")
    assert widget.layer_status == {"r": LayerStatus("ready", None, 0, 1)}
    assert calls == [
        {"r": LayerStatus("loading", None, 0, 1)},
        {"r": LayerStatus("ready", None, 0, 1)},
    ]


def test_layer_status_is_read_only(board):
    widget, _, _ = board
    open_view(widget, "a")
    with pytest.raises(AttributeError):
        widget.layer_status = {}
    with pytest.raises(TypeError):
        widget.layer_status["r"] = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        widget.layer_status["r"].status = "ready"


def test_same_token_remove_and_readd_ignores_the_old_instance(board):
    widget, _, _ = board
    layer = Layer("r", RasterSource(("t",)))
    open_view(widget, "a")
    report(widget, "a", "ready")
    old = {"token": 0, "instance": 1}
    widget.publish(MapState())
    assert widget.layer_status == {}
    widget.publish(MapState(layers=(layer,)))
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}
    report(widget, "a", "error", error="late", **old)
    report(widget, "a", "ready", **old)
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}
    report(widget, "a", "ready")
    assert widget.layer_status == {"r": LayerStatus("ready", None, 0, 2)}


def test_publish_retires_a_replaced_instance_before_publishing(board):
    widget, _, _ = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    published = []
    widget.observe(
        lambda _: published.append({k: dict(v) for k, v in widget._reports.items()}),
        "state",
    )
    widget.publish(MapState(layers=(Layer("r", RasterSource(("u",))),)))
    assert published == [{("a", "main"): {}}]
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}


COMPARE = {"main": ("main", "main"), "compare": ("main", "right")}


@pytest.fixture(params=list(COMPARE))
def pair(request, monkeypatch, loop):
    """Two views on the same reducer: both ``main``, or ``main`` and ``right``."""
    widget = MapWidget(loop=loop)
    capture_sends(monkeypatch, widget)
    calls = []
    widget.on_status(lambda status: calls.append(dict(status)))
    widget.publish(
        MapState(layers=(Layer("r", RasterSource(("t",))),), compare=request.param == "compare")
    )
    return widget, COMPARE[request.param], calls


def test_conflicting_views_reduce_to_error_then_loading_then_ready(pair):
    widget, (one, two), _ = pair
    open_view(widget, "a", one)
    open_view(widget, "b", two)
    report(widget, "a", "ready", side=one)
    assert status_of(widget) == ("loading", None)
    report(widget, "b", "error", side=two, error="tile failed")
    assert status_of(widget) == ("error", "tile failed")
    report(widget, "a", "loading", side=one)
    assert status_of(widget) == ("error", "tile failed")
    report(widget, "b", "ready", side=two)
    assert status_of(widget) == ("loading", None)
    report(widget, "a", "ready", side=one)
    assert status_of(widget) == ("ready", None)


def test_closing_the_failed_view_drops_its_reports_for_good(pair):
    widget, (one, two), calls = pair
    open_view(widget, "a", one)
    open_view(widget, "b", two)
    report(widget, "a", "ready", side=one)
    report(widget, "b", "error", side=two, error="tile failed")
    close_view(widget, "b", two)
    assert status_of(widget) == ("ready", None)
    count = len(calls)
    report(widget, "b", "error", side=two, error="late")
    report(widget, "b", "loading", side=two)
    assert status_of(widget) == ("ready", None)
    assert len(calls) == count
    close_view(widget, "a", one)
    assert widget.layer_status == {}


def layer_on(side, layer_id="r"):
    return Layer(layer_id, RasterSource(("t",)), side=side)


@pytest.fixture
def sides(monkeypatch, loop):
    """A widget with a ``main`` and a ``right`` view of the same ``v`` open."""
    widget = MapWidget(loop=loop)
    capture_sends(monkeypatch, widget)
    open_view(widget, "v", "main")
    open_view(widget, "v", "right")
    return widget


def test_side_change_keeps_instance():
    widget = MapWidget()
    widget.publish(MapState(layers=(layer_on("both"),), compare=True))
    first = instance(widget, "r")
    for side in ("left", "right", "both"):
        widget.publish(MapState(layers=(layer_on(side),), compare=True))
        assert instance(widget, "r") == first


def test_view_open_with_left_side_is_ignored(board):
    widget, sent, _ = board
    open_view(widget, "a", "left")
    assert widget._views == {}
    assert sent == []
    assert widget.layer_status == {}


def test_status_follows_sides(sides):
    widget = sides
    widget.publish(MapState(layers=(layer_on("right"),), compare=True))
    # The main view does not draw it: its report is ignored.
    report(widget, "v", "ready", side="main")
    assert status_of(widget) == ("loading", None)
    report(widget, "v", "ready", side="right")
    assert status_of(widget) == ("ready", None)

    widget.publish(MapState(layers=(layer_on("both"),), compare=True))
    report(widget, "v", "error", side="right", error="x")
    report(widget, "v", "ready", side="main")
    assert status_of(widget) == ("error", "x")
    report(widget, "v", "ready", side="right")
    assert status_of(widget) == ("ready", None)

    widget.publish(MapState(layers=(layer_on("left"),), compare=True))
    report(widget, "v", "ready", side="main")
    assert status_of(widget) == ("ready", None)
    report(widget, "v", "error", side="right", error="ignored")
    assert status_of(widget) == ("ready", None)

    # Compare off: everything is on main, and right reports are ignored.
    widget.publish(MapState(layers=(layer_on("right", "o"),), compare=False))
    report(widget, "v", "error", layer_id="o", side="right", error="ignored")
    assert status_of(widget, "o") == ("loading", None)
    report(widget, "v", "ready", layer_id="o", side="main")
    assert status_of(widget, "o") == ("ready", None)


def test_right_view_closing_drops_its_reports(sides):
    widget = sides
    widget.publish(MapState(layers=(layer_on("both"),), compare=True))
    report(widget, "v", "ready", side="main")
    report(widget, "v", "error", side="right", error="x")
    assert status_of(widget) == ("error", "x")
    close_view(widget, "v", "right")
    assert status_of(widget) == ("ready", None)
    report(widget, "v", "error", side="right", error="late")
    assert status_of(widget) == ("ready", None)
    assert ("v", "right") not in widget._reports


def test_report_of_a_side_that_stopped_drawing_is_dropped(sides):
    widget = sides
    widget.publish(MapState(layers=(layer_on("left"),), compare=True))
    report(widget, "v", "error", side="main", error="old")
    assert status_of(widget) == ("error", "old")
    widget.publish(MapState(layers=(layer_on("right"),), compare=True))
    widget.publish(MapState(layers=(layer_on("left"),), compare=True))
    assert status_of(widget) == ("loading", None)
    report(widget, "v", "ready", side="main")
    assert status_of(widget) == ("ready", None)


def test_a_right_report_is_dropped_when_compare_turns_off(sides):
    widget = sides
    widget.publish(MapState(layers=(layer_on("right"),), compare=True))
    report(widget, "v", "error", side="right", error="old")
    assert status_of(widget) == ("error", "old")
    widget.publish(MapState(layers=(layer_on("right"),), compare=False))
    widget.publish(MapState(layers=(layer_on("right"),), compare=True))
    assert status_of(widget) == ("loading", None)


def test_a_silent_failed_view_expires_after_150_s_and_a_grace(board, loop):
    widget, sent, calls = board
    open_view(widget, "ok")
    report(widget, "ok", "ready")
    loop.advance(10)
    open_view(widget, "bad")
    report(widget, "bad", "error", error="tile failed")
    assert status_of(widget) == ("error", "tile failed")
    loop.advance(139.9)
    open_view(widget, "ok")
    # No message arrives from here on: the timer alone expires the view.
    loop.advance(10)
    assert status_of(widget) == ("error", "tile failed")
    loop.advance(10)
    assert status_of(widget) == ("error", "tile failed")
    loop.advance(0.2)
    assert status_of(widget) == ("ready", None)
    assert calls[-1] == {"r": LayerStatus("ready", None, 0, 1)}

    # The unchanged view comes back: Python asks it to replay, and it does.
    sent.clear()
    open_view(widget, "bad")
    assert sent == [({"type": "status_request", "view_id": "bad", "side": "main"}, None)]
    assert status_of(widget) == ("loading", None)
    report(widget, "bad", "error", error="tile failed")
    assert status_of(widget) == ("error", "tile failed")

    loop.advance(161)
    assert widget.layer_status == {}
    assert loop.pending() == []


def view_report(widget, view, seq=1, cause="request"):
    camera = {"center": [0, 0], "zoom": 2, "bounds": [-1, -1, 1, 1]}
    msg(widget, type="view_report", view_id=view, request_seq=seq, cause=cause, **camera)


def pull(widget, view, side="main"):
    msg(widget, type="pull", view_id=view, side=side, digests=[])


#: One view per kind of message a view sends, and how it sends it.
SENDERS = {
    "heartbeat": open_view,
    "status": lambda widget, view: report(widget, view, "ready"),
    "view_report": view_report,
    "pull": pull,
}


@pytest.mark.parametrize("timer_first", [False, True], ids=["messages-first", "timer-first"])
def test_messages_queued_behind_a_long_cell_keep_their_views(board, loop, timer_first):
    widget, sent, calls = board
    for view in SENDERS:
        open_view(widget, view)
        report(widget, view, "ready")
    open_view(widget, "silent")
    report(widget, "silent", "error", error="tile failed")
    sent.clear()
    count = len(calls)

    # A cell holds the loop past every deadline; then the overdue timer and
    # the messages the views sent meanwhile run, in either order.
    loop.block(200)
    if timer_first:
        loop.advance(0)
    for view, send in SENDERS.items():
        send(widget, view)
    loop.advance(0)
    views = {(view, "main") for view in SENDERS}
    assert set(widget._views) == views | {("silent", "main")}
    assert status_of(widget) == ("error", "tile failed")
    assert len(calls) == count
    assert sent == []

    # Only the view that stayed silent through the grace expires.
    loop.advance(10)
    assert set(widget._views) == views
    assert status_of(widget) == ("ready", None)
    loop.advance(140)
    assert set(widget._views) == views


def test_a_message_during_the_grace_renews_the_view(board, loop):
    widget, sent, _ = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    loop.advance(150)
    assert ("a", "main") in widget._views
    loop.advance(9)
    view_report(widget, "a")
    loop.advance(149)
    assert status_of(widget) == ("ready", None)
    loop.advance(11)
    assert widget.layer_status == {}


def test_a_heartbeat_keeps_status_and_sends_nothing(board, loop):
    widget, sent, calls = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    sent.clear()
    count = len(calls)
    for _ in range(10):
        loop.advance(20)
        open_view(widget, "a")
    assert status_of(widget) == ("ready", None)
    assert len(calls) == count
    assert sent == []
    assert len(loop.pending()) == 1


def test_style_errors_count_only_for_the_current_draw(board):
    widget, _, _ = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    report(widget, "a", "error", error="old paint", style_revision=0)
    assert status_of(widget) == ("ready", None)
    report(widget, "a", "error", error="paint", style_revision=1)
    assert status_of(widget) == ("error", "paint")
    widget.publish(MapState(layers=(Layer("r", RasterSource(("t",)), opacity=0.5),)))
    assert status_of(widget) == ("error", "paint")
    report(widget, "a", "error", error="late paint", style_revision=1)
    assert status_of(widget) == ("error", "paint")
    report(widget, "a", "ready")
    assert status_of(widget) == ("ready", None)


@pytest.mark.parametrize(
    "change",
    [
        {"view_id": "nobody"},
        {"view_id": None},
        {"side": "top"},
        {"id": "nope"},
        {"token": 5},
        {"instance": 9},
        {"instance": True},
        {"status": "done"},
        {"error": 3},
        {"style_revision": "1"},
    ],
)
def test_reports_that_do_not_match_are_ignored(board, change):
    widget, _, _ = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    report(widget, "a", **{"status": "error", "error": "bad", **change})
    assert status_of(widget) == ("ready", None)


@pytest.mark.parametrize(
    "content",
    [
        {"type": "view_open"},
        {"type": "view_open", "view_id": "a", "side": "top"},
        {"type": "view_open", "view_id": "", "side": "main"},
        {"type": "view_open", "view_id": 3, "side": "main"},
        {"type": "view_close", "view_id": "zzz", "side": "main"},
    ],
)
def test_malformed_view_messages_are_ignored(board, content):
    widget, sent, calls = board
    msg(widget, **content)
    assert widget.layer_status == {}
    assert sent == [] and calls == []


def test_close_cancels_expiry_and_late_messages_do_nothing(board, loop):
    widget, sent, calls = board
    open_view(widget, "a")
    report(widget, "a", "error", error="x")
    assert loop.pending()
    count = len(calls)
    widget.close()
    assert loop.pending() == []
    assert widget.layer_status == {}
    sent.clear()
    open_view(widget, "b")
    report(widget, "a", "ready")
    assert widget.layer_status == {} and sent == []
    assert len(calls) == count


def test_the_expiry_timer_stops_with_the_last_view(board, loop):
    widget, _, _ = board
    open_view(widget, "a")
    assert len(loop.pending()) == 1
    close_view(widget, "a")
    assert loop.pending() == []


def test_a_failing_status_callback_is_logged(board, caplog):
    widget, _, calls = board

    def broken(status):
        raise RuntimeError("callback broke")

    widget.on_status(broken)
    with caplog.at_level("ERROR", logger="pysepal_map"):
        open_view(widget, "a")
    assert "callback broke" in caplog.text
    assert len(calls) == 1
    widget.on_status(broken, remove=True)
    caplog.clear()
    report(widget, "a", "ready")
    assert caplog.text == ""
    assert len(calls) == 2


def test_the_supplied_loop_runs_the_expiry(loop):
    widget = MapWidget(loop=loop)
    assert widget.loop is loop
    open_view(widget, "a")
    assert [h.when for h in loop.pending()] == [150]


def in_fresh_thread(scenario):
    """Run ``scenario`` where no loop runs yet.

    Once a Playwright browser test ran, its loop counts as running in the
    main thread.
    """
    out = {}

    def target():
        try:
            out["value"] = scenario()
        except BaseException as error:
            out["error"] = error

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if "error" in out:
        raise out["error"]
    return out["value"]


def test_without_a_loop_expiry_binds_the_first_message_loop():
    def scenario():
        widget = MapWidget()
        before = widget.loop

        async def receive():
            open_view(widget, "a")
            when = widget._expiry.when() - asyncio.get_running_loop().time()
            widget.close()
            return asyncio.get_running_loop(), when

        running, when = asyncio.run(receive())
        return before, widget.loop is running, when

    before, bound, when = in_fresh_thread(scenario)
    assert before is None
    assert bound
    assert when == pytest.approx(150, abs=1)


def test_the_loop_running_at_construction_runs_the_expiry():
    async def construct():
        widget = MapWidget()
        loop = asyncio.get_running_loop()
        open_view(widget, "a")
        when = widget._expiry.when() - loop.time()
        widget.close()
        return widget.loop is loop, when, widget._expiry

    captured, when, expiry = in_fresh_thread(lambda: asyncio.run(construct()))
    assert captured
    assert when == pytest.approx(150, abs=1)
    assert expiry is None


def test_loop_follows_a_replacement_after_the_old_loop_closed():
    def scenario():
        widget = MapWidget()

        async def receive():
            open_view(widget, "a")
            return asyncio.get_running_loop()

        first = asyncio.run(receive())
        adopted = widget.loop
        second = asyncio.run(receive())
        replaced = widget.loop
        widget.close()
        return adopted is first, replaced is second

    assert in_fresh_thread(scenario) == (True, True)


# ---------------------------------------------------------------------------
# Release: a closed widget leaves nothing behind
# ---------------------------------------------------------------------------

hot_reload = pytest.mark.skipif(
    os.getenv("ANYWIDGET_HMR") == "1", reason="anywidget watches the asset files"
)


@hot_reload
def test_the_assets_are_text_so_anywidget_does_not_watch_them():
    from pysepal_map import widget as widget_module

    for name, value in [("widget.js", MapWidget._esm), ("widget.css", MapWidget._css)]:
        assert value == (widget_module._STATIC / name).read_text(encoding="utf-8")


def test_hot_reload_keeps_the_asset_paths(monkeypatch):
    from pysepal_map import widget as widget_module

    monkeypatch.setenv("ANYWIDGET_HMR", "1")
    assert widget_module._asset("widget.js") == widget_module._STATIC / "widget.js"


@hot_reload
def test_a_closed_widget_is_collected():
    widget = MapWidget()
    widget.publish(MapState(layers=(geo(widget),)))
    reference = weakref.ref(widget)

    widget.close()
    del widget
    gc.collect()

    assert reference() is None


def test_a_closed_widget_closes_the_layout_it_built():
    before = set(widget_registry._instances)
    widget = MapWidget()
    layout = widget._trait_values["layout"]

    widget.close()

    assert layout.comm is None
    assert set(widget_registry._instances) - before == set()


def test_a_closed_widget_leaves_a_given_layout_open():
    layout = ipywidgets.Layout(width="50%")
    widget = MapWidget(layout=layout)

    widget.close()

    assert layout.comm is not None
    layout.close()
