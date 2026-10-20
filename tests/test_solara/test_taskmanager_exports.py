"""TaskManager export contract, without Earth Engine or SEPAL network calls."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from pysepal.solara.components.export_engine import submit_export_request
from pysepal.solara.components.export_models import ExportRequest


def client():
    return SimpleNamespace(
        results_path="/home/sepal-user/module_results/demo",
        BASE_REMOTE_PATH="/home/sepal-user",
        ee_exports=SimpleNamespace(
            submit_image=AsyncMock(return_value=SimpleNamespace(id="sepal-123", state="PENDING")),
            submit_table=AsyncMock(return_value=SimpleNamespace(id="sepal-123", state="PENDING")),
        ),
        tasks=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="sepal-123", state="COMPLETED")),
            cancel=AsyncMock(),
        ),
    )


def request(**kwargs):
    return ExportRequest(
        ee_object={"result": "image"},
        export_kind="image",
        target="sepal",
        name="demo",
        poll_interval_seconds=0,
        **kwargs,
    )


def submit(req, api, **kwargs):
    return submit_export_request(
        req,
        gee_interface=MagicMock(),
        drive_interface=MagicMock(),
        sepal_client=None,
        async_sepal_client=api,
        backend="taskmanager",
        **kwargs,
    )


def test_workspace_completion_has_sepal_id_and_output_directory():
    api = client()
    accepted = []
    result = asyncio.run(
        submit(request(sepal_folder="exports"), api, on_remote_submitted=accepted.append)
    )
    payload = api.ee_exports.submit_image.call_args.kwargs
    assert payload["destination"].value == "SEPAL"
    assert payload["workspace_path"] == "module_results/demo/exports"
    assert result.status == "completed"
    assert result.sepal_task_id == "sepal-123"
    assert result.task_id is None
    assert result.output_directory == "/home/sepal-user/module_results/demo/exports"
    assert result.sepal_paths == ()
    assert accepted == ["sepal-123"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"priority": 100},
        {"sepal_folder": "../escape"},
        {"sepal_folder": "/etc/exports"},
    ],
)
def test_invalid_options_never_submit(kwargs):
    api = client()
    with pytest.raises(ValueError):
        asyncio.run(submit(request(**kwargs), api))
    api.ee_exports.submit_image.assert_not_called()


def test_table_geojson_and_selectors():
    api = client()
    req = replace(
        request(),
        export_kind="table",
        table_file_format="GEO_JSON",
        selectors=("name",),
    )
    asyncio.run(submit(req, api))
    payload = api.ee_exports.submit_table.call_args.kwargs
    assert payload["file_format"] == "GeoJSON"
    assert payload["selectors"] == ["name"]
    with pytest.raises(ValueError, match="max_vertices"):
        asyncio.run(submit(replace(req, max_vertices=100), api))
    assert api.ee_exports.submit_table.await_count == 1


def test_submission_failure_does_not_fall_back():
    api = client()
    api.ee_exports.submit_image.side_effect = TimeoutError("lost response")
    gee = MagicMock()
    with pytest.raises(RuntimeError, match="unknown"):
        asyncio.run(
            submit_export_request(
                request(),
                gee_interface=gee,
                drive_interface=MagicMock(),
                sepal_client=None,
                async_sepal_client=api,
                backend="taskmanager",
            )
        )
    assert gee.mock_calls == []
    api.tasks.get.assert_not_called()


@pytest.mark.parametrize("state", ["FAILED", "CANCELED"])
def test_remote_failure_is_not_success(state):
    api = client()
    api.tasks.get.return_value = SimpleNamespace(id="sepal-123", state=state)
    with pytest.raises(RuntimeError, match="sepal-123"):
        asyncio.run(submit(request(), api))


def test_local_monitor_cancel_does_not_cancel_remote_task():
    async def run():
        api = client()
        polling = asyncio.Event()

        async def wait(*args, **kwargs):
            polling.set()
            await asyncio.Event().wait()

        api.tasks.get.side_effect = wait
        task = asyncio.create_task(submit(request(), api))
        await asyncio.wait_for(polling.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        api.tasks.cancel.assert_not_called()

    asyncio.run(run())


def test_timeout_preserves_remote_task_and_identifies_it():
    api = client()
    with pytest.raises(TimeoutError, match="sepal-123"):
        asyncio.run(submit(request(timeout_seconds=0), api))
    api.tasks.cancel.assert_not_called()


def test_remote_cancellation_is_explicit():
    from pysepal.solara.components.export import cancel_taskmanager_export

    api = client()
    asyncio.run(cancel_taskmanager_export(api, "sepal-123"))
    api.tasks.cancel.assert_awaited_once_with("sepal-123")


def test_image_selection_and_visualization_reach_taskmanager(monkeypatch):
    from pysepal.solara.components import export_engine

    image = MagicMock()
    styled = MagicMock()
    monkeypatch.setattr(export_engine, "set_viz_params", lambda obj, **kwargs: styled)
    api = client()
    req = replace(
        request(),
        ee_object=image,
        selectors=("red", "green"),
        vis_params={"bands": ["red"]},
    )
    asyncio.run(submit(req, api))
    styled.select.assert_called_once_with(["red", "green"])
    assert api.ee_exports.submit_image.call_args.kwargs["image"] is styled.select.return_value


def test_explicit_direct_backend_ignores_taskmanager_flag(monkeypatch):
    monkeypatch.setenv("PYSEPAL_TASKMANAGER_EXPORTS", "1")
    gee = SimpleNamespace(export_image_to_drive_async=AsyncMock(return_value="ee-123"))
    api = client()
    result = asyncio.run(
        submit_export_request(
            replace(request(), target="drive"),
            gee_interface=gee,
            drive_interface=None,
            sepal_client=None,
            async_sepal_client=api,
            backend="direct",
        )
    )
    assert result.status == "submitted"
    assert result.ee_task_id == "ee-123"
    assert result.sepal_task_id is None
    api.ee_exports.submit_image.assert_not_called()


def test_missing_workspace_client_fails_before_direct_submission():
    gee = MagicMock()
    with pytest.raises(ValueError, match="SepalClient"):
        asyncio.run(
            submit_export_request(
                request(),
                gee_interface=gee,
                drive_interface=None,
                sepal_client=None,
                backend="direct",
            )
        )
    assert gee.mock_calls == []
