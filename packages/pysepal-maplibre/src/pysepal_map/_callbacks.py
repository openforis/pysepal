"""Run user callbacks on the session loop."""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
from collections import deque
from collections.abc import Callable
from typing import TypeGuard

logger = logging.getLogger("pysepal_map")

#: Tasks of awaitables callbacks returned, kept alive until they finish:
#: the loop only holds a weak reference to a task.
_running: set[asyncio.Future] = set()


def running_loop() -> asyncio.AbstractEventLoop | None:
    """The loop running in this thread, if any."""
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def _usable(loop: asyncio.AbstractEventLoop | None) -> TypeGuard[asyncio.AbstractEventLoop]:
    return loop is not None and not loop.is_closed()


def dispatch(cb: Callable, *args, loop: asyncio.AbstractEventLoop | None) -> None:
    """Call ``cb(*args)`` on ``loop``, and run an awaitable it returns there too.

    From another thread the call is queued with ``loop.call_soon_threadsafe``,
    even if that thread runs a loop of its own. Without a session loop it
    happens now, and an awaitable runs on this thread's running loop, else to
    completion. A failure is logged to ``pysepal_map``.
    """
    if _usable(loop) and running_loop() is not loop:
        try:
            loop.call_soon_threadsafe(_call, cb, args, loop, None)
            return
        except RuntimeError:
            loop = None  # it closed meanwhile
    _call(cb, args, loop, None)


def _call(
    cb: Callable,
    args: tuple,
    loop: asyncio.AbstractEventLoop | None,
    track: Callable[[asyncio.Future], None] | None,
) -> None:
    try:
        result = cb(*args)
    except Exception:
        logger.exception("pysepal-map: a callback failed")
        return
    if inspect.isawaitable(result):
        _await(result, loop, track)


def _await(awaitable, loop, track) -> None:
    target = loop if _usable(loop) else running_loop()
    if target is None:
        try:
            asyncio.run(_wait(awaitable))
        except Exception:
            logger.exception("pysepal-map: a callback failed")
        return
    try:
        task = asyncio.ensure_future(awaitable, loop=target)
    except Exception:
        if inspect.iscoroutine(awaitable):
            awaitable.close()
        logger.exception("pysepal-map: a callback failed")
        return
    _running.add(task)
    task.add_done_callback(_finished)
    if track is not None:
        track(task)


async def _wait(awaitable):
    return await awaitable


def _finished(task: asyncio.Future) -> None:
    _running.discard(task)
    error = None if task.cancelled() else task.exception()
    if error is not None:
        logger.error("pysepal-map: a callback failed", exc_info=error)


def _cancel(task: asyncio.Future) -> None:
    loop = task.get_loop()
    if loop.is_closed():
        return
    if running_loop() is loop:
        task.cancel()
    else:
        loop.call_soon_threadsafe(task.cancel)


class CallbackQueue:
    """One owner's callbacks, run on its session loop in the order queued.

    The owner queues with ``put`` under its own lock, right where it takes
    the snapshot a callback gets, so the queue order is the snapshot order.
    ``flush`` then runs the queue without that lock. One drain at a time
    empties it front to back on the loop, so a call queued later, from any
    thread or from a callback such as one that draws, never runs before an
    earlier one. ``close`` drops the calls still queued and cancels the
    tasks of the awaitables the callbacks returned.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: deque[tuple[Callable, tuple]] = deque()
        self._draining = False
        self._closed = False
        self._tasks: set[asyncio.Future] = set()

    def put(self, cb: Callable, *args) -> None:
        """Queue ``cb(*args)``; the next ``flush`` runs it."""
        with self._lock:
            if not self._closed:
                self._queue.append((cb, args))

    def flush(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Run the queued calls on ``loop``, as ``dispatch`` would run one."""
        with self._lock:
            # Whoever queues a call flushes after it, so nothing is left behind.
            if not self._queue:
                return
        # A drain that runs after close() finds nothing to do.
        dispatch(self._drain, loop, loop=loop)

    def close(self) -> None:
        """Drop the queued calls and cancel what the callbacks left running."""
        with self._lock:
            self._closed = True
            self._queue.clear()
            tasks, self._tasks = self._tasks, set()
        for task in tasks:
            _cancel(task)

    def _drain(self, loop: asyncio.AbstractEventLoop | None) -> None:
        with self._lock:
            if self._draining:
                # The running drain, further up this stack or on another
                # thread, takes what was just queued.
                return
            self._draining = True
        try:
            while True:
                with self._lock:
                    if self._closed or not self._queue:
                        self._draining = False
                        return
                    cb, args = self._queue.popleft()
                _call(cb, args, loop, self._track)
        except BaseException:
            with self._lock:
                self._draining = False
            raise

    def _track(self, task: asyncio.Future) -> None:
        with self._lock:
            closed = self._closed
            if not closed:
                self._tasks.add(task)
        if closed:
            _cancel(task)
        else:
            task.add_done_callback(self._untrack)

    def _untrack(self, task: asyncio.Future) -> None:
        with self._lock:
            self._tasks.discard(task)
