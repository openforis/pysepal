"""Progress from worker threads reaches the pill of the kernel that owns the task.

Under ``solara run`` a reactive write lands in the store of the *calling*
thread's kernel context. A worker thread has none, so before the bus bound its
own context the write went to Solara's global store and the pill never moved.
"""

import asyncio
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from solara.server.kernel_context import has_current_context

from pysepal.solara.notifications.bus import cleanup_bus, create_bus
from pysepal.solara.notifications.notifier import Notifier


def _via_to_thread(fn):
    asyncio.run(asyncio.to_thread(fn))


def _via_run_in_executor(fn):
    async def main():
        await asyncio.get_running_loop().run_in_executor(None, fn)

    asyncio.run(main())


def _via_thread(fn):
    thread = threading.Thread(target=fn)
    thread.start()
    thread.join()


def _via_pool(fn):
    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(fn).result()


def _via_thread_with_context(context):
    """What ``use_task(prefer_threaded=True)`` does: a thread carrying the context."""

    def run(fn):
        def target():
            with context:
                fn()

        _via_thread(target)

    return run


def _mount(context):
    """Create the context's bus, a subscriber, and a running tracker on it."""
    seen = []
    with context:
        bus = create_bus()
        bus.tasks.subscribe(seen.append)
        tracker = Notifier(bus).track("Downloading").__enter__()
    return bus, tracker, seen


@pytest.mark.parametrize(
    "runner",
    [_via_to_thread, _via_run_in_executor, _via_thread, _via_pool, "with_context"],
)
def test_worker_progress_reaches_the_owning_kernel(kernel_contexts, runner):
    context = kernel_contexts()
    bus, tracker, seen = _mount(context)
    run = _via_thread_with_context(context) if runner == "with_context" else runner

    run(lambda: tracker.set_progress(0.5, detail="tile 5/10"))

    assert seen[-1][0].progress == 0.5
    assert seen[-1][0].progress_detail == "tile 5/10"
    with context:
        assert bus.tasks.value[0].progress == 0.5
        cleanup_bus()


def test_a_worker_thread_keeps_no_kernel_context(kernel_contexts):
    """Publishing must not leave the kernel attached to a pooled thread."""
    _, tracker, _ = _mount(kernel_contexts())
    attached = []

    def work():
        tracker.step("Started")
        attached.append(has_current_context())

    _via_pool(work)

    assert attached == [False]


def test_two_kernels_sharing_a_pool_thread_see_only_their_own_task(kernel_contexts):
    first, second = kernel_contexts(), kernel_contexts()
    _, first_tracker, first_seen = _mount(first)
    _, second_tracker, second_seen = _mount(second)

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(first_tracker.set_progress, 0.25).result()
        pool.submit(second_tracker.set_progress, 0.75).result()

    assert [t.progress for t in first_seen[-1]] == [0.25]
    assert [t.progress for t in second_seen[-1]] == [0.75]


def test_a_closed_kernel_does_not_break_the_worker(kernel_contexts):
    """A job can outlive its browser tab; its last updates must not raise."""
    context = kernel_contexts()
    bus, tracker, _ = _mount(context)
    context.close()

    _via_pool(lambda: tracker.set_progress(0.9))

    assert bus.find_task(tracker._task_id).progress == 0.9


def test_parallel_steps_on_one_tracker_are_all_kept(kernel_contexts):
    """step() appends under the bus lock, so parallel workers lose no milestone."""
    context = kernel_contexts()
    bus, tracker, _ = _mount(context)
    # Switch threads as often as possible, so a read-then-write race shows up.
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda i: tracker.step(f"layer {i} done"), range(200)))
    finally:
        sys.setswitchinterval(previous)

    task = bus.find_task(tracker._task_id)
    assert len(task.milestones) == 200
    assert task.current_step == 200
