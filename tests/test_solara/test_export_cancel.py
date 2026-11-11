"""A local cancel of an export also cancels its Earth Engine task (#984).

Each test drives ``submit_export_request`` (or the dialog hook) on a fake GEE
interface and cancels it at one phase: before the submission, while the
submission is in flight, while Earth Engine runs, or after Earth Engine
finished (SEPAL target: waiting for Drive, copying to SEPAL).
"""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest
import solara

from pysepal.solara.components import export_engine
from pysepal.solara.components.export import (
    ExportDialog,
    ExportRequest,
    RemoteCancelOutcome,
    submit_export_request,
    use_export_dialog,
)
from pysepal.solara.components.export_engine import cancel_export_task


class _FakeTable:
    pass


class _CancelGee:
    """GEE interface fake whose tasks run until something cancels them."""

    def __init__(self, *, state="RUNNING", cancel_error=None, submit_gate=None, folder_gate=None):
        self.state = state
        self.cancel_error = cancel_error
        self.submit_gate = submit_gate
        self.folder_gate = folder_gate
        self.submitted = []
        self.cancelled = []
        self.submit_started = asyncio.Event()
        self.folder_requested = asyncio.Event()
        self.polled = asyncio.Event()

    async def get_folder_async(self):
        self.folder_requested.set()
        if self.folder_gate is not None:
            await self.folder_gate.wait()
        return "projects/demo/assets"

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        return None

    async def create_folder_async(self, folder_path):
        return {"id": folder_path}

    async def _submit(self, destination):
        self.submitted.append(destination)
        self.submit_started.set()
        if self.submit_gate is not None:
            await self.submit_gate.wait()
        return {"id": "task-1"}

    async def export_table_to_asset_async(self, **_kwargs):
        return await self._submit("asset")

    async def export_table_to_drive_async(self, **_kwargs):
        return await self._submit("drive")

    async def get_task_async(self, task_id):
        self.polled.set()
        return {"state": self.state}

    async def cancel_task_async(self, task_id):
        if self.cancel_error is not None:
            raise self.cancel_error
        self.cancelled.append(task_id)
        self.state = "CANCEL_REQUESTED"


def _request(target, **overrides):
    values = dict(
        ee_object=_FakeTable(),
        export_kind="table",
        target=target,
        name="demo_export",
        gee_asset_id="projects/demo/assets/demo_export" if target == "gee" else None,
        poll_interval_seconds=0.01,
        timeout_seconds=5.0,
    )
    values.update(overrides)
    return ExportRequest(**values)


@pytest.fixture
def drive(monkeypatch):
    """Drive staging files, faked at the engine's Drive helpers."""
    state = {"items": [], "deleted": [], "polled": None}

    def _find(_drive_interface, prefix, modified_after=None):
        state["polled"].set()
        return list(state["items"])

    def _delete(_drive_interface, items):
        state["deleted"].extend(item["name"] for item in items)

    monkeypatch.setattr(export_engine, "_find_drive_items_by_prefix", _find)
    monkeypatch.setattr(export_engine, "_delete_drive_items", _delete)
    return state


async def _start(gee, request, outcomes, submitted=None):
    return asyncio.ensure_future(
        submit_export_request(
            request,
            gee_interface=gee,
            drive_interface=MagicMock(),
            sepal_client=MagicMock(),
            on_remote_submitted=(submitted.append if submitted is not None else None),
            on_remote_cancel=outcomes.append,
        )
    )


async def _cancel_and_join(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_cancel_while_earth_engine_runs_cancels_the_task():
    outcomes = []

    async def scenario():
        gee = _CancelGee()
        task = await _start(gee, _request("sepal"), outcomes)
        await gee.polled.wait()
        await _cancel_and_join(task)
        return gee

    gee = asyncio.run(scenario())

    assert gee.cancelled == ["task-1"]
    assert outcomes == [RemoteCancelOutcome(task_id="task-1", status="cancelled")]


@pytest.mark.parametrize("target", ["gee", "drive"])
def test_cancel_during_submission_cancels_the_task_it_creates(target):
    """The submission may reach Earth Engine after the cancel: its task is cancelled too."""
    outcomes = []
    submitted = []

    async def scenario():
        gate = asyncio.Event()
        gee = _CancelGee(submit_gate=gate)
        task = await _start(gee, _request(target), outcomes, submitted)
        await gee.submit_started.wait()
        task.cancel()
        await asyncio.sleep(0)
        gate.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        return gee

    gee = asyncio.run(scenario())

    assert gee.cancelled == ["task-1"]
    assert submitted == ["task-1"]
    assert outcomes == [RemoteCancelOutcome(task_id="task-1", status="cancelled")]


def test_cancel_before_submission_cancels_nothing():
    outcomes = []

    async def scenario():
        gee = _CancelGee(folder_gate=asyncio.Event())
        task = await _start(gee, _request("gee"), outcomes)
        await gee.folder_requested.wait()
        await _cancel_and_join(task)
        return gee

    gee = asyncio.run(scenario())

    assert gee.submitted == []
    assert gee.cancelled == []
    assert outcomes == []


def test_a_failed_cancel_is_reported_and_the_export_still_ends_cancelled():
    outcomes = []

    async def scenario():
        gee = _CancelGee(cancel_error=RuntimeError("quota exceeded"))
        task = await _start(gee, _request("sepal"), outcomes)
        await gee.polled.wait()
        await _cancel_and_join(task)

    asyncio.run(scenario())

    assert len(outcomes) == 1
    assert outcomes[0].status == "failed"
    assert outcomes[0].task_id == "task-1"
    assert "quota exceeded" in outcomes[0].error


def test_cancel_after_earth_engine_finished_deletes_the_drive_staging_files(drive):
    outcomes = []

    async def scenario():
        drive["polled"] = asyncio.Event()
        gee = _CancelGee(state="COMPLETED")
        task = await _start(gee, _request("sepal"), outcomes)
        await drive["polled"].wait()
        # The files become visible in Drive after the cancel.
        drive["items"] = [{"id": "f1", "name": "demo_export.csv"}]
        await _cancel_and_join(task)
        return gee

    gee = asyncio.run(scenario())

    assert gee.cancelled == []
    assert drive["deleted"] == ["demo_export.csv"]
    assert outcomes == [
        RemoteCancelOutcome(
            task_id="task-1",
            status="finished",
            state="COMPLETED",
            deleted_drive_items=("demo_export.csv",),
        )
    ]


def test_cancel_after_earth_engine_finished_keeps_drive_files_without_cleanup(drive):
    outcomes = []

    async def scenario():
        drive["polled"] = asyncio.Event()
        gee = _CancelGee(state="COMPLETED")
        task = await _start(gee, _request("sepal", cleanup_drive_after_sepal=False), outcomes)
        await drive["polled"].wait()
        drive["items"] = [{"id": "f1", "name": "demo_export.csv"}]
        await _cancel_and_join(task)

    asyncio.run(scenario())

    assert drive["deleted"] == []
    assert outcomes == [RemoteCancelOutcome(task_id="task-1", status="finished", state="COMPLETED")]


def test_cancel_while_copying_to_sepal_deletes_the_drive_staging_files(drive, monkeypatch):
    outcomes = []
    copy_started = threading.Event()
    release_copy = threading.Event()

    def _blocking_copy(*_args):
        copy_started.set()
        release_copy.wait(5)
        return ()

    monkeypatch.setattr(export_engine, "_copy_drive_items_to_sepal", _blocking_copy)
    monkeypatch.setattr(export_engine, "resolve_sepal_folder", lambda *_args: "out")

    async def scenario():
        drive["polled"] = asyncio.Event()
        drive["items"] = [{"id": "f1", "name": "demo_export.csv"}]
        gee = _CancelGee(state="COMPLETED")
        task = await _start(gee, _request("sepal"), outcomes)
        try:
            await asyncio.to_thread(copy_started.wait, 5)
            await _cancel_and_join(task)
        finally:
            release_copy.set()

    asyncio.run(scenario())

    assert drive["deleted"] == ["demo_export.csv"]
    assert outcomes[0].status == "finished"
    assert outcomes[0].deleted_drive_items == ("demo_export.csv",)


def test_cancel_export_task_leaves_a_finished_task_alone():
    gee = _CancelGee(state="COMPLETED")

    outcome = asyncio.run(cancel_export_task(gee, "task-1"))

    assert gee.cancelled == []
    assert outcome == RemoteCancelOutcome(task_id="task-1", status="finished", state="COMPLETED")


def test_cancel_export_task_reports_a_task_that_finished_while_cancelling():
    """Earth Engine refuses to cancel a task that ended between the read and the cancel."""
    gee = _CancelGee(cancel_error=RuntimeError("Operation already done"))
    original_cancel = gee.cancel_task_async

    async def _finish_then_refuse(task_id):
        gee.state = "COMPLETED"
        await original_cancel(task_id)

    gee.cancel_task_async = _finish_then_refuse

    outcome = asyncio.run(cancel_export_task(gee, "task-1"))

    assert outcome == RemoteCancelOutcome(task_id="task-1", status="finished", state="COMPLETED")


def test_cancel_export_task_without_a_task_id_fails():
    outcome = asyncio.run(cancel_export_task(_CancelGee(), None))

    assert outcome.status == "failed"
    assert outcome.task_id is None


# ---------------------------------------------------------------------------
# The dialog hook reports the outcome once, through the notifications
# (inline here, as no NotificationProvider is mounted).
# ---------------------------------------------------------------------------


def _run_hook(gee, scenario):
    captured = {}

    @solara.component
    def _Harness():
        controller = use_export_dialog(
            sources=[],
            gee_interface=gee,
            drive_interface=MagicMock(),
            sepal_client=MagicMock(),
        )
        captured["controller"] = controller
        return ExportDialog(controller=controller, title="Test")

    async def _runner():
        _box, rc = solara.render(_Harness(), handle_error=False)
        try:
            await scenario(captured)
        finally:
            rc.close()

    asyncio.run(_runner())
    state = captured["controller"]._state
    return state.inline_level.value, state.inline_message.value


async def _settle(controller, condition):
    for _ in range(200):
        if condition() and not controller.task.pending:
            break
        await asyncio.sleep(0.01)
    # Let the effects of the last state change run.
    await asyncio.sleep(0.05)


def test_hook_reports_the_cancelled_earth_engine_task():
    gee = _CancelGee()

    async def scenario(captured):
        controller = captured["controller"]
        controller.task(_request("sepal"))
        await gee.polled.wait()
        controller.cancel_export()
        await _settle(controller, lambda: gee.cancelled)

    level, message = _run_hook(gee, scenario)

    assert gee.cancelled == ["task-1"]
    assert level == "cancel"
    assert message == "Export cancelled. The Earth Engine task was cancelled too."


def test_hook_reports_a_failed_earth_engine_cancel_as_an_error():
    gee = _CancelGee(cancel_error=RuntimeError("quota exceeded"))

    async def scenario(captured):
        controller = captured["controller"]
        controller.task(_request("sepal"))
        await gee.polled.wait()
        controller.cancel_export()
        await _settle(controller, lambda: True)

    level, message = _run_hook(gee, scenario)

    assert level == "error"
    assert "`task-1`" in message
    assert "quota exceeded" in message
    assert "Earth Engine task manager" in message


def test_hook_reports_a_plain_cancel_before_submission():
    gee = _CancelGee(folder_gate=asyncio.Event())

    async def scenario(captured):
        controller = captured["controller"]
        controller.task(_request("gee"))
        await gee.folder_requested.wait()
        controller.cancel_export()
        await _settle(controller, lambda: True)

    level, message = _run_hook(gee, scenario)

    assert gee.submitted == []
    assert (level, message) == ("cancel", "Export cancelled.")
