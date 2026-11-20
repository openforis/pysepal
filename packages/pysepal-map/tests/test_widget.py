"""Test the MapWidget snapshot bookkeeping, payload replies and layer status."""

import asyncio
import dataclasses
import hashlib
import json
import sys
import threading

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


def test_draw_increments_revision():
    widget = MapWidget()
    widget.draw(MapState())
    assert widget.state["revision"] == 1
    widget.draw(MapState())
    assert widget.state["revision"] == 2


def test_draw_with_unknown_digest_raises_keyerror():
    widget = MapWidget()
    with pytest.raises(KeyError, match="deadbeef"):
        widget.draw(MapState(layers=(Layer("v", GeoJSONSource("deadbeef")),)))
    assert widget.state == {}


def test_draw_drops_unreferenced_payloads():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.add_payload(b"orphan")
    widget.draw(MapState(layers=(layer,)))
    assert list(widget._payloads) == [layer.source.digest]
    widget.draw(MapState())
    assert widget._payloads == {}


def test_invalid_draw_preserves_previous_snapshot_and_bytes():
    widget = MapWidget()
    layer = geo(widget, b"keep")
    widget.draw(MapState(layers=(layer,)))
    before = dict(widget.state)
    extra = widget.add_payload(b"new")
    with pytest.raises(ValueError):
        MapState(layers=(dataclasses.replace(layer, opacity=float("nan")),))
    with pytest.raises(KeyError):
        widget.draw(MapState(layers=(layer, Layer("w", GeoJSONSource("nope")))))
    with pytest.raises(TypeError):
        widget.draw({"layers": []})
    assert widget.state == before
    assert set(widget._payloads) == {layer.source.digest, extra}
    widget.draw(MapState(layers=(layer,)))
    assert widget.state["revision"] == 2
    assert instance(widget) == 1


def test_readd_with_default_token_allocates_new_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.draw(MapState(layers=(layer,)))
    assert instance(widget) == 1
    widget.draw(MapState())
    widget.add_payload(b"{}")
    widget.draw(MapState(layers=(layer,)))
    assert instance(widget) == 2


def test_paint_only_changes_preserve_the_instance():
    widget = MapWidget()
    layer = geo(widget)
    widget.draw(MapState(layers=(layer,)))
    changed = dataclasses.replace(
        layer, paint=VectorPaint(stroke="#f00"), opacity=0.5, visible=False
    )
    widget.draw(MapState(layers=(changed,)))
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
    widget.draw(MapState(layers=(layer,)))
    if change == "digest":
        new = geo(widget, b"2")
    widget.draw(MapState(layers=(new,)))
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
    widget.draw(MapState(layers=(layer,)))
    sent = capture_sends(monkeypatch, widget)
    digest = layer.source.digest
    widget._handle_custom_msg({"type": "pull", "digests": [digest]}, [])
    assert sent == [({"type": "data", "digest": digest}, [data])]


def test_pull_of_a_dropped_digest_answers_missing(monkeypatch):
    widget = MapWidget()
    kept = geo(widget, b"kept")
    dropped = Layer("w", GeoJSONSource(widget.add_payload(b"dropped")))
    widget.draw(MapState(layers=(kept, dropped)))
    widget.draw(MapState(layers=(kept,)))
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
    widget.draw(MapState(layers=(layer,)))
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


def test_instances_follow_input_order_and_keep_across_reorder():
    widget = MapWidget()
    a = Layer("a", RasterSource(("t",)))
    b = Layer("b", RasterSource(("u",)))
    widget.draw(MapState(layers=(a, b)))
    widget.draw(MapState(layers=(b, a)))
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
            widget.draw(MapState(layers=(raster, vector)))

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
    widget.draw(MapState(layers=(Layer("r", RasterSource(("t",))),)))
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
    widget.draw(MapState())
    assert widget.layer_status == {}
    widget.draw(MapState(layers=(layer,)))
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}
    report(widget, "a", "error", error="late", **old)
    report(widget, "a", "ready", **old)
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}
    report(widget, "a", "ready")
    assert widget.layer_status == {"r": LayerStatus("ready", None, 0, 2)}


def test_draw_retires_a_replaced_instance_before_publishing(board):
    widget, _, _ = board
    open_view(widget, "a")
    report(widget, "a", "ready")
    published = []
    widget.observe(
        lambda _: published.append({k: dict(v) for k, v in widget._reports.items()}),
        "state",
    )
    widget.draw(MapState(layers=(Layer("r", RasterSource(("u",))),)))
    assert published == [{("a", "main"): {}}]
    assert widget.layer_status == {"r": LayerStatus("loading", None, 0, 2)}


COMPARE = {"main": ("main", "main"), "compare": ("left", "right")}


class CompareWidget(MapWidget):
    """The compare contract: ``l`` draws on the left only, the rest on both."""

    compare = True

    def _sides_of(self, layer_id):
        if layer_id == "l":
            return ("left",)
        return ("left", "right") if self.compare else ("main",)


@pytest.fixture(params=list(COMPARE))
def pair(request, monkeypatch, loop):
    """Two views on the same reducer: both ``main``, or ``left`` and ``right``."""
    widget = CompareWidget(loop=loop)
    widget.compare = request.param == "compare"
    capture_sends(monkeypatch, widget)
    calls = []
    widget.on_status(lambda status: calls.append(dict(status)))
    widget.draw(MapState(layers=(Layer("r", RasterSource(("t",))),)))
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


def test_a_left_only_layer_is_not_held_by_the_right_view(monkeypatch, loop):
    widget = CompareWidget(loop=loop)
    capture_sends(monkeypatch, widget)
    left, both = Layer("l", RasterSource(("t",))), Layer("r", RasterSource(("u",)))
    widget.draw(MapState(layers=(left, both)))
    open_view(widget, "a", "left")
    open_view(widget, "b", "right")
    report(widget, "a", "ready", layer_id="l", side="left")
    report(widget, "a", "ready", side="left")
    assert status_of(widget, "l") == ("ready", None)
    assert status_of(widget, "r") == ("loading", None)
    # A right view's report about a left-only layer is not its to make.
    report(widget, "b", "error", layer_id="l", side="right", error="x")
    assert status_of(widget, "l") == ("ready", None)
    close_view(widget, "a", "left")
    assert set(widget.layer_status) == {"r"}


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
    widget.draw(MapState(layers=(Layer("r", RasterSource(("t",)), opacity=0.5),)))
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
    assert widget._loop is loop
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
        before = widget._loop

        async def receive():
            open_view(widget, "a")
            when = widget._expiry.when() - asyncio.get_running_loop().time()
            widget.close()
            return asyncio.get_running_loop(), when

        running, when = asyncio.run(receive())
        return before, widget._loop is running, when

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
        return widget._loop is loop, when, widget._expiry

    captured, when, expiry = in_fresh_thread(lambda: asyncio.run(construct()))
    assert captured
    assert when == pytest.approx(150, abs=1)
    assert expiry is None
