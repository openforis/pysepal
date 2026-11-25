"""The layer store calls its subscribers on its loop, whichever thread wrote."""

import asyncio
import threading
import time

import pytest

from pysepal.layers import LayerStore, StoreEvent


def recorder(store: LayerStore) -> list:
    """Subscribe and record each event with the thread that received it."""
    seen: list = []
    store.subscribe(lambda event: seen.append((event, threading.get_ident())))
    return seen


def run_in_thread(target, *args) -> int:
    thread = threading.Thread(target=target, args=args)
    thread.start()
    thread.join()
    return thread.ident


@pytest.mark.asyncio
async def test_events_from_a_worker_reach_subscribers_on_the_loop(raster_spec, raster_spec_b):
    store = LayerStore()
    seen = recorder(store)

    def write():
        store.add(raster_spec)
        store.add(raster_spec_b)
        store.set_opacity(raster_spec.id, 0.5)

    await asyncio.to_thread(write)
    await asyncio.sleep(0)
    here = threading.get_ident()
    assert seen == [
        (StoreEvent("added", raster_spec.id), here),
        (StoreEvent("added", raster_spec_b.id), here),
        (StoreEvent("opacity", raster_spec.id), here),
    ]
    assert store.pending_events == 0


@pytest.mark.asyncio
async def test_a_write_on_the_loop_comes_after_the_events_handed_over(raster_spec, raster_spec_b):
    store = LayerStore()
    seen = recorder(store)
    run_in_thread(store.add, raster_spec)  # blocks the loop: the event waits for it
    assert seen == [] and store.pending_events == 1
    store.add(raster_spec_b)
    assert [event for event, _ in seen] == [
        StoreEvent("added", raster_spec.id),
        StoreEvent("added", raster_spec_b.id),
    ]
    await asyncio.sleep(0)
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_a_subscriber_write_is_delivered_at_once(raster_spec, raster_spec_b):
    """A write made by a subscriber reaches every subscriber before the event that caused it."""
    store = LayerStore()

    def chain(event):
        if event == StoreEvent("added", raster_spec.id):
            store.add(raster_spec_b)

    store.subscribe(chain)
    seen = recorder(store)
    await asyncio.to_thread(store.add, raster_spec)
    await asyncio.sleep(0)
    assert [event.layer_id for event, _ in seen] == [raster_spec_b.id, raster_spec.id]
    assert {thread for _, thread in seen} == {threading.get_ident()}


def test_without_a_loop_subscribers_run_on_the_writer(raster_spec):
    store = LayerStore()
    seen = recorder(store)
    writer = run_in_thread(store.add, raster_spec)
    assert seen == [(StoreEvent("added", raster_spec.id), writer)]


def test_the_owner_loop_is_followed_across_a_reconnect(raster_spec, raster_spec_b):
    class Owner:
        loop = None

    owner, store = Owner(), LayerStore()
    store.follow_loop(owner)
    seen = recorder(store)
    for spec in (raster_spec, raster_spec_b):
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_forever)
        thread.start()
        owner.loop = loop
        assert store.loop is loop
        store.add(spec)  # from this thread, off the owner's loop
        loop.call_soon_threadsafe(loop.stop)
        thread.join()
        loop.close()
        assert seen[-1] == (StoreEvent("added", spec.id), thread.ident)
    assert store.loop is None


def test_a_closed_loop_gives_way_to_the_next_one_the_store_runs_on(raster_spec, raster_spec_b):
    store = LayerStore()
    seen: list = []

    async def subscribe():
        store.subscribe(lambda event: seen.append((event.layer_id, threading.get_ident())))

    async def reconnected():
        store.add(raster_spec)  # on the new loop: the store adopts it
        await asyncio.to_thread(store.add, raster_spec_b)
        await asyncio.sleep(0)

    asyncio.run(subscribe())
    asyncio.run(reconnected())
    here = threading.get_ident()
    assert seen == [(raster_spec.id, here), (raster_spec_b.id, here)]


def test_an_owner_is_held_weakly():
    import gc
    import weakref

    class Owner:
        loop = None

    owner, store = Owner(), LayerStore()
    store.follow_loop(owner)
    reference = weakref.ref(owner)
    del owner
    gc.collect()
    assert reference() is None


def test_events_left_on_a_stopped_loop_are_not_pending(raster_spec):
    """A loop stopped before its drain ran never delivers them, so nothing should wait on them."""
    store = LayerStore()
    loop = asyncio.new_event_loop()
    subscribed, written = threading.Event(), threading.Event()

    def block():
        store.subscribe(lambda event: None)  # captures the running loop
        subscribed.set()
        loop.stop()  # ends with this batch: the drain the write schedules never runs
        written.wait(5)

    loop.call_soon(block)
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    subscribed.wait(5)
    store.add(raster_spec)
    written.set()
    thread.join(5)
    try:
        assert not loop.is_running() and not loop.is_closed()
        assert store.pending_events == 0
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_a_writer_in_a_tight_loop_does_not_hold_the_loop(raster_spec):
    store = LayerStore()
    store.subscribe(lambda event: time.sleep(0.001))
    store.add(raster_spec)
    stop = threading.Event()

    def write():
        # Writes outpace the subscriber for 2 s, so the queue never empties.
        opacity, deadline = 0.5, time.monotonic() + 2
        while time.monotonic() < deadline and not stop.is_set():
            opacity = 1.5 - opacity
            store.set_opacity(raster_spec.id, opacity)
            time.sleep(0.0005)

    writer = threading.Thread(target=write, daemon=True)
    writer.start()
    try:
        start = time.monotonic()
        await asyncio.sleep(0.01)
        assert time.monotonic() - start < 1
    finally:
        stop.set()
        writer.join()
