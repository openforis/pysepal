"""Test the camera requests and reports, and how callbacks reach Python code."""

import asyncio
import threading

import pytest
from pysepal_map import Layer, LayerStatus, MapState, MapWidget, RasterSource
from pysepal_map._callbacks import dispatch
from pysepal_map.widget import VIEW_EXPIRY_S, VIEW_GRACE_S

VIEW = {"center": [1.0, 2.0], "zoom": 3.0, "bounds": [0.0, 1.0, 2.0, 3.0]}


def msg(widget, **content):
    widget._handle_custom_msg(content, [])


def open_view(widget, view="a"):
    msg(widget, type="view_open", view_id=view, side="main")


def close_view(widget, view="a"):
    msg(widget, type="view_close", view_id=view, side="main")


def report(widget, view="a", seq=1, cause="request", **change):
    content = {"type": "view_report", "view_id": view, **VIEW, "request_seq": seq}
    msg(widget, **{**content, "cause": cause, **change})


def in_thread(scenario):
    """Run ``scenario`` in a new thread and return what it returns."""
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
    return out.get("value")


def test_init_issues_request_seq_1():
    widget = MapWidget()
    assert widget.view_request == {"seq": 1, "center": [0.0, 0.0], "zoom": 2.0}
    assert widget.view == {}
    widget = MapWidget(center=(10, -5.5), zoom=4)
    assert widget.view_request == {"seq": 1, "center": [10.0, -5.5], "zoom": 4.0}


def test_requests_increment_seq():
    widget = MapWidget()
    widget.set_center(30, 10, zoom=3)
    assert widget.view_request == {"seq": 2, "center": [30.0, 10.0], "zoom": 3.0}
    widget.set_center(30, 10, zoom=5)
    assert widget.view_request == {"seq": 3, "center": [30.0, 10.0], "zoom": 5.0}
    widget.fit_bounds((10, 10, 20, 20))
    assert widget.view_request == {
        "seq": 4,
        "bounds": [10.0, 10.0, 20.0, 20.0],
        "padding": 20,
        "max_zoom": None,
    }
    # West east of east crosses the antimeridian.
    widget.fit_bounds((170, -10, -170, 10), padding=0)
    assert widget.view_request == {
        "seq": 5,
        "bounds": [170.0, -10.0, -170.0, 10.0],
        "padding": 0,
        "max_zoom": None,
    }


def test_a_zoomless_center_keeps_the_last_zoom_until_a_view_reports(loop):
    widget = MapWidget(zoom=6, loop=loop)
    # A view mounted now has no reported camera whose zoom it could keep.
    widget.set_center(10, 10)
    assert widget.view_request == {"seq": 2, "center": [10.0, 10.0], "zoom": 6.0}
    widget.fit_bounds((0, 0, 1, 1))
    widget.set_center(1, 1, zoom=8)
    widget.set_center(2, 2)
    assert widget.view_request["zoom"] == 8.0
    open_view(widget)
    report(widget, seq=5)
    # Now a new view restores the reported zoom first.
    widget.set_center(3, 3)
    assert widget.view_request == {"seq": 6, "center": [3.0, 3.0], "zoom": None}


@pytest.mark.parametrize(
    "request_",
    [
        lambda w: w.set_center(float("nan"), 0),
        lambda w: w.set_center(0, 90.5),
        lambda w: w.set_center(True, 0),
        lambda w: w.set_center(0, 0, zoom=24.5),
        lambda w: w.set_center(0, 0, zoom=-1),
        lambda w: w.fit_bounds((0, 10, 1, 5)),
        lambda w: w.fit_bounds((0, -91, 1, 0)),
        lambda w: w.fit_bounds((0, 0, 1)),
        lambda w: w.fit_bounds((0, 0, 1, float("inf"))),
        lambda w: w.fit_bounds((0, 0, 1, 1), padding=-1),
        lambda w: w.fit_bounds((0, 0, 1, 1), padding=1.5),
        lambda w: w.fit_bounds((0, 0, 1, 1), padding=True),
    ],
)
def test_an_invalid_request_raises_and_issues_nothing(request_):
    widget = MapWidget()
    with pytest.raises(ValueError):
        request_(widget)
    assert widget.view_request["seq"] == 1


def test_an_invalid_initial_camera_raises():
    with pytest.raises(ValueError):
        MapWidget(center=(0, 100))
    with pytest.raises(ValueError):
        MapWidget(zoom=float("nan"))


def test_sync_callback_gets_the_view(loop):
    widget = MapWidget(loop=loop)
    seen = []
    widget.on_view(seen.append)
    open_view(widget)
    report(widget)
    expected = {**VIEW, "request_seq": 1, "cause": "request"}
    assert widget.view == expected
    assert seen == [expected]
    # Each callback gets its own copy.
    seen[0]["center"].append(9)
    assert widget.view == expected

    widget.on_view(seen.append, remove=True)
    report(widget, zoom=4)
    assert widget.view["zoom"] == 4.0
    assert len(seen) == 1


def test_reports_of_views_that_are_not_mounted_are_ignored(loop):
    widget = MapWidget(loop=loop)
    seen = []
    widget.on_view(seen.append)
    report(widget, "ghost")
    open_view(widget, "gone")
    close_view(widget, "gone")
    report(widget, "gone")
    open_view(widget, "silent")
    loop.advance(VIEW_EXPIRY_S + VIEW_GRACE_S + 1)
    report(widget, "silent")
    assert widget.view == {} and seen == []


def test_a_report_past_the_grace_expires_the_last_view_and_clears_the_status(loop):
    widget = MapWidget(loop=loop)
    widget.publish(MapState(layers=(Layer("r", RasterSource(("t",))),)))
    open_view(widget)
    loading = {"r": LayerStatus("loading", None, 0, 1)}
    assert widget.layer_status == loading
    # Its deadline and then its grace pass before the timer gets to run;
    # reports from a view never opened find it late, then gone.
    loop.block(VIEW_EXPIRY_S + 1)
    report(widget, "other")
    assert widget.layer_status == loading
    loop.block(VIEW_GRACE_S)
    report(widget, "other")
    assert widget.view == {}
    assert widget.layer_status == {}


def test_an_older_report_never_rolls_the_view_back(loop):
    widget = MapWidget(loop=loop)
    widget.set_center(5, 5)
    open_view(widget, "a")
    open_view(widget, "b")
    report(widget, "a", seq=2, center=[5.0, 5.0])
    # b moved before it took request 2; its report arrives last.
    report(widget, "b", seq=1, cause="user", center=[-50.0, -20.0])
    assert widget.view["center"] == [5.0, 5.0]
    assert widget.view["request_seq"] == 2
    # Among user moves on the same request, the last one wins.
    report(widget, "b", seq=2, cause="user", center=[6.0, 6.0])
    report(widget, "a", seq=2, cause="user", center=[7.0, 7.0])
    assert widget.view["center"] == [7.0, 7.0]


def test_a_resize_report_updates_the_bounds(loop):
    widget = MapWidget(loop=loop)
    seen = []
    widget.on_view(seen.append)
    open_view(widget)
    report(widget)
    report(widget, cause="resize", bounds=[-1.0, 0.0, 3.0, 4.0])
    assert widget.view["bounds"] == [-1.0, 0.0, 3.0, 4.0]
    assert [v["bounds"] for v in seen] == [VIEW["bounds"], [-1.0, 0.0, 3.0, 4.0]]


def test_only_a_user_report_replaces_a_user_camera_on_the_same_request(loop):
    widget = MapWidget(loop=loop)
    seen = []
    widget.on_view(seen.append)
    open_view(widget, "a")
    open_view(widget, "b")
    report(widget, "a", cause="user", center=[5.0, 5.0])
    # An acknowledgement keeps it, from either view; so does b's resize.
    report(widget, "a", cause="request", center=[6.0, 6.0])
    report(widget, "b", cause="request", center=[6.0, 6.0])
    report(widget, "b", cause="resize", center=[7.0, 7.0])
    assert widget.view == {
        **VIEW,
        "center": [5.0, 5.0],
        "request_seq": 1,
        "cause": "user",
    }
    assert len(seen) == 1
    report(widget, "b", cause="user", center=[8.0, 8.0])
    assert widget.view["center"] == [8.0, 8.0]
    # A newer request's camera replaces it, whatever moved it.
    widget.set_center(0, 0)
    report(widget, "b", seq=2, cause="resize", center=[0.0, 0.0])
    assert widget.view["center"] == [0.0, 0.0]
    assert len(seen) == 3


def test_the_user_views_own_resize_updates_the_user_camera(loop):
    widget = MapWidget(loop=loop)
    open_view(widget, "a")
    open_view(widget, "b")
    report(widget, "a", cause="user", center=[5.0, 5.0])
    # a goes fullscreen: its bounds follow, and the camera is still a's pan.
    wide = [-9.0, -9.0, 9.0, 9.0]
    report(widget, "a", cause="resize", center=[5.0, 5.0], bounds=wide)
    assert widget.view == {
        **VIEW,
        "center": [5.0, 5.0],
        "bounds": wide,
        "request_seq": 1,
        "cause": "resize",
    }
    report(widget, "b", cause="resize", center=[7.0, 7.0])
    report(widget, "b", cause="request", center=[7.0, 7.0])
    assert widget.view["bounds"] == wide and widget.view["center"] == [5.0, 5.0]
    # Once b moves it, a's resize no longer counts.
    report(widget, "b", cause="user", center=[8.0, 8.0])
    report(widget, "a", cause="resize", center=[5.0, 5.0])
    assert widget.view["center"] == [8.0, 8.0]


def test_a_report_on_a_request_never_issued_is_ignored(loop):
    widget = MapWidget(loop=loop)
    open_view(widget)
    report(widget, seq=2)
    assert widget.view == {}


@pytest.mark.parametrize(
    "change",
    [
        {"view_id": 3},
        {"view_id": ""},
        {"center": "x"},
        {"center": [1.0]},
        {"center": [1.0, "2"]},
        {"center": [1.0, float("nan")]},
        {"zoom": None},
        {"zoom": float("inf")},
        {"zoom": True},
        {"bounds": [0.0, 1.0, 2.0]},
        {"bounds": None},
        {"request_seq": "1"},
        {"request_seq": True},
        {"request_seq": 1.0},
        {"request_seq": -1},
        {"cause": "pan"},
        {"cause": None},
    ],
)
def test_malformed_reports_are_ignored(loop, change):
    widget = MapWidget(loop=loop)
    open_view(widget)
    report(widget, **change)
    assert widget.view == {}


def test_failing_callback_is_logged_and_the_next_runs(loop, caplog):
    widget = MapWidget(loop=loop)
    seen = []

    def broken(view):
        raise RuntimeError("callback broke")

    widget.on_view(broken)
    widget.on_view(seen.append)
    open_view(widget)
    with caplog.at_level("ERROR", logger="pysepal_map"):
        report(widget)
    assert "callback broke" in caplog.text
    assert [v["request_seq"] for v in seen] == [1]


async def test_async_callback_runs_on_the_running_loop():
    widget = MapWidget()
    done = asyncio.Event()
    ran = []

    async def callback(view):
        await asyncio.sleep(0)
        ran.append((asyncio.get_running_loop(), view["request_seq"]))
        done.set()

    widget.on_view(callback)
    open_view(widget)
    report(widget)
    await asyncio.wait_for(done.wait(), 5)
    assert ran == [(asyncio.get_running_loop(), 1)]
    widget.close()


async def test_a_failing_async_callback_is_logged(caplog):
    widget = MapWidget()

    async def broken(view):
        raise RuntimeError("async callback broke")

    widget.on_view(broken)
    open_view(widget)
    with caplog.at_level("ERROR", logger="pysepal_map"):
        report(widget)
        for _ in range(5):
            await asyncio.sleep(0)
    assert "async callback broke" in caplog.text
    assert widget._callbacks._tasks == set()
    widget.close()


async def test_callbacks_from_a_thread_with_its_own_loop_run_on_the_session_loop():
    session = asyncio.get_running_loop()
    main = threading.current_thread()
    widget = MapWidget(loop=session)
    widget.publish(MapState(layers=(Layer("r", RasterSource(("t",))),)))
    seen = []
    done = asyncio.Event()

    def on_status(status):
        seen.append(("status", asyncio.get_running_loop(), threading.current_thread()))

    def on_view(view):
        seen.append(("sync", asyncio.get_running_loop(), threading.current_thread()))

    async def on_view_async(view):
        seen.append(("async", asyncio.get_running_loop(), threading.current_thread()))
        done.set()

    widget.on_status(on_status)
    widget.on_view(on_view)
    widget.on_view(on_view_async)

    async def deliver():
        open_view(widget)
        report(widget)

    in_thread(lambda: asyncio.run(deliver()))
    assert seen == []
    await asyncio.wait_for(done.wait(), 5)
    assert seen == [
        ("status", session, main),
        ("sync", session, main),
        ("async", session, main),
    ]
    widget.close()


async def test_callbacks_arrive_in_order_across_threads():
    widget = MapWidget()
    seen = []
    widget.on_view(lambda view: seen.append(view["zoom"]))
    open_view(widget)
    # Handled off the loop: its callback waits for the loop to run.
    in_thread(lambda: report(widget, zoom=1))
    # Handled on the loop while the first callback still waits.
    report(widget, zoom=2)
    await asyncio.sleep(0)
    assert seen == [1.0, 2.0]
    widget.close()


def test_a_callback_that_draws_does_not_reorder_the_others(loop):
    widget = MapWidget(loop=loop)
    layer = Layer("r", RasterSource(("t",)))
    widget.publish(MapState(layers=(layer,)))
    first, second = [], []

    def redraw(status):
        first.append(dict(status))
        if len(first) == 1:
            widget.publish(MapState())

    widget.on_status(redraw)
    widget.on_status(lambda status: second.append(dict(status)))
    open_view(widget)
    loading = {"r": LayerStatus("loading", None, 0, 1)}
    assert first == [loading, {}]
    assert second == [loading, {}]


async def test_close_cancels_pending_callbacks():
    widget = MapWidget()
    started = asyncio.Event()
    cancelled = []
    late = []

    async def slow(view):
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.append(view["zoom"])
            raise

    widget.on_view(slow)
    open_view(widget)
    report(widget)
    await asyncio.wait_for(started.wait(), 5)
    widget.on_view(late.append)
    in_thread(lambda: report(widget, zoom=5))
    widget.close()
    for _ in range(5):
        await asyncio.sleep(0)
    assert cancelled == [3.0]
    assert late == []


def test_without_any_loop_an_async_callback_runs_to_completion():
    def scenario():
        widget = MapWidget()
        seen = []

        async def callback(view):
            await asyncio.sleep(0)
            seen.append(view["zoom"])

        widget.on_view(callback)
        open_view(widget)
        report(widget)
        return widget.loop, seen

    assert in_thread(scenario) == (None, [3.0])


def test_dispatch_without_a_loop_calls_now():
    seen = []
    dispatch(lambda *args: seen.append(args), 1, 2, loop=None)
    assert seen == [(1, 2)]


async def test_dispatch_from_another_running_loop_queues_on_the_session_loop():
    session = asyncio.get_running_loop()
    seen = []

    async def callback(value):
        seen.append((value, asyncio.get_running_loop()))

    async def other():
        dispatch(callback, "x", loop=session)

    in_thread(lambda: asyncio.run(other()))
    for _ in range(5):
        await asyncio.sleep(0)
    assert seen == [("x", session)]
