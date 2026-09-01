"""Tests for NotificationBus: mutations, dedup, queue limits, thread safety."""

import threading
import time
from unittest.mock import patch

import pytest

from pysepal import _scope_registry as scope_registry
from pysepal.solara.notifications.bus import (
    DEDUP_WINDOW_SECONDS,
    MAX_TOAST_QUEUE,
    NotificationBus,
    _refcounts,
    _registry,
    cleanup_bus,
    create_bus,
    get_current_bus,
)
from pysepal.solara.notifications.state import (
    TaskMilestone,
    TaskStatus,
    Toast,
    ToastType,
    TrackedTask,
)
from pysepal.solara.runtime_context import PROCESS_SCOPE


@pytest.fixture
def bus():
    return NotificationBus()


# Toasts ---------------------------------------------------------------------


def test_add_and_remove_toast(bus):
    toast = Toast(message="hello", type=ToastType.SUCCESS)
    bus.add_toast(toast)
    assert len(bus.toasts.value) == 1
    bus.remove_toast(toast.id)
    assert len(bus.toasts.value) == 0


def test_dedup_merges_identical_toasts(bus):
    now = time.time()
    bus.add_toast(Toast(message="dup", type=ToastType.INFO, created_at=now))
    bus.add_toast(Toast(message="dup", type=ToastType.INFO, created_at=now + 0.5))
    assert len(bus.toasts.value) == 1
    assert bus.toasts.value[0].count == 2


def test_dedup_refreshes_identity_and_timestamp(bus):
    now = time.time()
    first = Toast(message="dup", type=ToastType.INFO, created_at=now)
    second = Toast(message="dup", type=ToastType.INFO, created_at=now + 0.5)

    bus.add_toast(first)
    bus.add_toast(second)

    merged = bus.toasts.value[0]
    assert merged.count == 2
    assert merged.id == second.id
    assert merged.created_at == second.created_at


def test_no_dedup_after_window(bus):
    now = time.time()
    bus.add_toast(Toast(message="dup", type=ToastType.INFO, created_at=now))
    bus.add_toast(
        Toast(message="dup", type=ToastType.INFO, created_at=now + DEDUP_WINDOW_SECONDS + 1)
    )
    assert len(bus.toasts.value) == 2


def test_queue_limit(bus):
    for i in range(MAX_TOAST_QUEUE + 5):
        bus.add_toast(Toast(message=f"msg-{i}", type=ToastType.INFO, created_at=time.time() + i))
    assert len(bus.toasts.value) <= MAX_TOAST_QUEUE


def test_new_error_replaces_previous_errors(bus):
    for i in range(5):
        bus.add_toast(Toast(message=f"err-{i}", type=ToastType.ERROR))
    errors = [t for t in bus.toasts.value if t.type == ToastType.ERROR]
    assert len(errors) == 1
    assert errors[0].message == "err-4"


def test_error_replacement_preserves_non_errors(bus):
    bus.add_toast(Toast(message="info", type=ToastType.INFO))
    bus.add_toast(Toast(message="err1", type=ToastType.ERROR))
    bus.add_toast(Toast(message="err2", type=ToastType.ERROR))
    non_errors = [t for t in bus.toasts.value if t.type != ToastType.ERROR]
    errors = [t for t in bus.toasts.value if t.type == ToastType.ERROR]
    assert len(non_errors) == 1
    assert len(errors) == 1
    assert errors[0].message == "err2"


# Tasks ----------------------------------------------------------------------


def test_add_update_remove_task(bus):
    task = TrackedTask(title="Processing")
    bus.add_task(task)
    assert bus.tasks.value[0].title == "Processing"

    bus.update_task(task.id, status=TaskStatus.RUNNING, progress=0.5)
    assert bus.tasks.value[0].status == TaskStatus.RUNNING

    bus.remove_task(task.id)
    assert len(bus.tasks.value) == 0


def test_add_milestone_via_update(bus):
    task = TrackedTask(title="Processing")
    bus.add_task(task)
    ms = TaskMilestone(message="step 1")
    bus.update_task(task.id, milestones=(ms,), current_step=1, status=TaskStatus.RUNNING)
    assert bus.tasks.value[0].milestones[0].message == "step 1"


# Thread safety --------------------------------------------------------------


def test_concurrent_toast_adds():
    bus = NotificationBus()
    errors = []

    def add_toasts(start):
        try:
            for i in range(50):
                bus.add_toast(Toast(message=f"t-{start}-{i}", created_at=time.time() + start + i))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=add_toasts, args=(n * 100,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(bus.toasts.value) <= MAX_TOAST_QUEUE


# Scope registry ------------------------------------------------------------


@pytest.fixture
def clean_bus_registry():
    _registry.clear()
    _refcounts.clear()
    yield
    _registry.clear()
    _refcounts.clear()


@patch.object(scope_registry, "current_scope_id", return_value="kernel-1")
def test_create_get_cleanup(mock_scope, clean_bus_registry):
    bus = create_bus()
    assert get_current_bus() is bus
    cleanup_bus()
    assert get_current_bus() is None


@patch.object(scope_registry, "current_scope_id")
def test_different_kernels_isolated(mock_scope, clean_bus_registry):
    mock_scope.return_value = "kernel-1"
    bus1 = create_bus()
    mock_scope.return_value = "kernel-2"
    bus2 = create_bus()
    assert bus1 is not bus2
    mock_scope.return_value = "kernel-1"
    assert get_current_bus() is bus1


@patch.object(scope_registry, "current_scope_id", return_value="kernel-1")
def test_refcount_prevents_premature_removal(mock_scope, clean_bus_registry):
    first = create_bus()
    assert create_bus() is first  # refcount = 2
    cleanup_bus()  # refcount = 1
    assert get_current_bus() is first
    cleanup_bus()  # refcount = 0
    assert get_current_bus() is None


@patch.object(scope_registry, "current_scope_id", return_value="kernel-1")
def test_cleanup_without_a_bus_is_a_no_op(mock_scope, clean_bus_registry):
    cleanup_bus()
    assert get_current_bus() is None


def test_get_bus_returns_none_without_kernel_context(clean_bus_registry):
    assert get_current_bus() is None


def test_bus_is_available_in_a_script(clean_bus_registry):
    """No per-connection runtime is the process scope, not an error."""
    with patch.object(scope_registry, "current_scope_id", return_value=PROCESS_SCOPE):
        created = create_bus()
        assert get_current_bus() is created
        cleanup_bus()
        assert get_current_bus() is None


def test_get_current_bus_does_not_swallow_programming_errors(clean_bus_registry):
    """A resolver exception must reach the caller, not become a None return.

    ``TypeError`` is an honest choice here only because ``resolve_scope_id``
    absorbs the *runtime* TypeError a kernel with no connection file produces
    (see ``test_runtime_context``). What can still surface at this level is a
    bug in our own resolution path, and a bug must not be hidden.
    """
    with patch.object(scope_registry, "current_scope_id", side_effect=TypeError("boom")):
        with pytest.raises(TypeError):
            get_current_bus()
