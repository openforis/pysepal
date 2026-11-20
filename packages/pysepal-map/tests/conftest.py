"""Shared fixtures, and the browser tests moved to the end of the run."""

import dataclasses
from pathlib import Path

import pytest

BROWSER = Path(__file__).parent / "browser"


def pytest_collection_modifyitems(items):
    """Run the browser tests last.

    Once Playwright's sync API has started, its loop counts as running in the
    main thread, and pytest-asyncio can no longer run a test there.
    """
    items.sort(key=lambda item: item.path.is_relative_to(BROWSER))


@dataclasses.dataclass
class FakeHandle:
    when: float
    callback: object
    cancelled: bool = False

    def cancel(self):
        self.cancelled = True


@dataclasses.dataclass
class FakeLoop:
    """The parts of an event loop the widget uses; it runs nothing by itself.

    ``call_soon_threadsafe`` runs its callback at once, so callbacks reach the
    test synchronously.
    """

    now: float = 0.0
    handles: list = dataclasses.field(default_factory=list)

    def time(self):
        return self.now

    def is_running(self):
        return False

    def is_closed(self):
        return False

    def call_later(self, delay, callback, *args):
        handle = FakeHandle(self.now + delay, lambda: callback(*args))
        self.handles.append(handle)
        return handle

    def call_soon_threadsafe(self, callback, *args):
        callback(*args)

    def pending(self):
        return [h for h in self.handles if not h.cancelled]

    def advance(self, seconds):
        target = self.now + seconds
        while due := sorted((h for h in self.pending() if h.when <= target), key=lambda h: h.when):
            handle = due[0]
            self.handles.remove(handle)
            self.now = handle.when
            handle.callback()
        self.now = target


@pytest.fixture
def loop():
    return FakeLoop()
