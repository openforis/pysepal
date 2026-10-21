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
    from pysepal_api.endpoints import ee_exports

    from pysepal.solara.components import export_engine

    image = MagicMock()
    styled = MagicMock()
    monkeypatch.setattr(export_engine, "set_viz_params", lambda obj, **kwargs: styled)
    monkeypatch.setattr(ee_exports, "serialize_ee_object", lambda value: value)
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


# --- backend selection ------------------------------------------------------


def sync_client(**kwargs):
    from pysepal_api import SepalClient
    from pysepal_api.auth import NoAuth

    return SepalClient(auth=NoAuth(), base_url="https://sepal.test", module_name="demo", **kwargs)


@pytest.mark.parametrize(
    ("backend", "kwargs", "clients", "opted_in", "expected"),
    [
        ("auto", {}, ("sync",), True, "taskmanager"),
        ("auto", {}, ("sync",), False, "direct"),
        ("auto", {}, ("async",), False, "taskmanager"),
        ("auto", {}, (), True, "direct"),
        ("auto", {"target": "gee"}, ("async",), True, "direct"),
        # TaskManager rejects priority; the direct path still honours it.
        ("auto", {"priority": 100}, ("sync",), True, "direct"),
        ("auto", {"priority": 100}, ("async",), False, "taskmanager"),
        ("direct", {}, ("async",), True, "direct"),
        ("taskmanager", {"target": "gee"}, ("sync",), False, "taskmanager"),
    ],
)
def test_select_backend(backend, kwargs, clients, opted_in, expected):
    from pysepal.solara.components.export_taskmanager import select_backend

    req = replace(request(), **kwargs)
    selected = select_backend(
        backend,
        req,
        sepal_client=object() if "sync" in clients else None,
        async_sepal_client=object() if "async" in clients else None,
        opted_in=opted_in,
    )
    assert selected == expected


def test_select_backend_rejects_unknown_backend():
    from pysepal.solara.components.export_taskmanager import select_backend

    with pytest.raises(ValueError, match="Unknown export backend"):
        select_backend(
            "bogus", request(), sepal_client=None, async_sepal_client=None, opted_in=False
        )


def test_flag_does_not_reroute_standalone_engine_calls(monkeypatch):
    monkeypatch.setenv("PYSEPAL_TASKMANAGER_EXPORTS", "1")
    gee = SimpleNamespace(
        export_image_to_drive_async=AsyncMock(side_effect=RuntimeError("direct path"))
    )
    with pytest.raises(RuntimeError, match="direct path"):
        asyncio.run(
            submit_export_request(
                request(),
                gee_interface=gee,
                drive_interface=MagicMock(),
                sepal_client=sync_client(),
            )
        )


# --- submission outcome -----------------------------------------------------


@pytest.mark.parametrize(
    ("error", "match"),
    [
        ("BadRequest", "may not support TaskManager"),
        ("NotFound", "may not support TaskManager"),
        ("Unauthorized", "no task was created"),
    ],
)
def test_definite_rejection_is_not_reported_as_unknown(error, match):
    from pysepal_api import errors

    api = client()
    status = {"BadRequest": 400, "NotFound": 404, "Unauthorized": 401}[error]
    api.ee_exports.submit_image.side_effect = getattr(errors, error)(
        status, url="https://sepal.test/api/tasks"
    )
    with pytest.raises(RuntimeError, match=match) as info:
        asyncio.run(submit(request(), api))
    assert "unknown" not in str(info.value)


@pytest.mark.parametrize("error", ["server", "transport", "timeout"])
def test_lost_or_failed_response_is_unknown(error):
    from pysepal_api import errors

    api = client()
    api.ee_exports.submit_image.side_effect = {
        "server": errors.ServerError(502, url="https://sepal.test/api/tasks"),
        "transport": errors.TransportError("ReadTimeout"),
        "timeout": TimeoutError("lost response"),
    }[error]
    with pytest.raises(RuntimeError, match="outcome is unknown"):
        asyncio.run(submit(request(), api))


def test_local_encoding_error_surfaces_before_submission(monkeypatch):
    from pysepal_api.endpoints import ee_exports

    def fail(value):
        raise TypeError("cannot encode")

    monkeypatch.setattr(ee_exports, "serialize_ee_object", fail)
    api = client()
    with pytest.raises(TypeError, match="cannot encode"):
        asyncio.run(submit(request(), api))
    api.ee_exports.submit_image.assert_not_called()


def test_slow_status_request_is_a_timeout():
    async def hang(*args, **kwargs):
        await asyncio.Event().wait()

    api = client()
    api.tasks.get.side_effect = hang
    with pytest.raises(TimeoutError, match="Stopped waiting for SEPAL task `sepal-123`"):
        asyncio.run(submit(request(timeout_seconds=0.05), api))


# --- per-export client ------------------------------------------------------


def derived_clients(monkeypatch):
    from pysepal.solara.components import export_taskmanager

    made = []

    def make(**kwargs):
        api = client()
        api.kwargs = kwargs
        api.aclose = AsyncMock()
        made.append(api)
        return api

    monkeypatch.setattr(export_taskmanager, "AsyncSepalClient", make)
    return made


def submit_with_sync(req, sync):
    return submit_export_request(
        req,
        gee_interface=MagicMock(),
        drive_interface=None,
        sepal_client=sync,
        backend="taskmanager",
    )


def test_derived_client_has_the_sync_identity_and_is_closed(monkeypatch):
    made = derived_clients(monkeypatch)
    sync = sync_client()
    result = asyncio.run(submit_with_sync(request(), sync))
    assert result.sepal_task_id == "sepal-123"
    (api,) = made
    assert api.kwargs == {
        "auth": sync._http.auth,
        "module_name": "demo",
        "base_url": sync.base_url,
        "verify": sync.verify,
    }
    api.aclose.assert_awaited_once()


def test_each_export_gets_a_fresh_client_on_its_own_loop(monkeypatch):
    made = derived_clients(monkeypatch)
    sync = sync_client()
    asyncio.run(submit_with_sync(request(), sync))
    asyncio.run(submit_with_sync(request(), sync))
    assert len(made) == 2
    assert all(api.aclose.await_count == 1 for api in made)


def test_caller_owned_async_client_is_not_closed():
    api = client()
    api.aclose = AsyncMock()
    asyncio.run(submit(request(), api))
    api.aclose.assert_not_awaited()


def test_closed_session_refuses_before_submission(monkeypatch):
    from pysepal.solara.errors import SessionScopeClosedError

    made = derived_clients(monkeypatch)
    sync = sync_client()
    sync.close()
    with pytest.raises(SessionScopeClosedError):
        asyncio.run(submit_with_sync(request(), sync))
    assert made == []


def test_session_close_stops_monitoring(monkeypatch):
    from pysepal.solara.errors import SessionScopeClosedError

    made = derived_clients(monkeypatch)
    sync = sync_client()

    async def pending_then_close(*args, **kwargs):
        sync.close()
        return SimpleNamespace(id="sepal-123", state="ACTIVE")

    async def run():
        task = asyncio.create_task(submit_with_sync(request(timeout_seconds=2), sync))
        while not made and not task.done():
            await asyncio.sleep(0)
        if made:
            made[0].tasks.get.side_effect = pending_then_close
        return await task

    with pytest.raises(SessionScopeClosedError, match="sepal-123"):
        asyncio.run(run())
    made[0].aclose.assert_awaited_once()
    made[0].tasks.cancel.assert_not_called()


def test_remote_cancellation_accepts_the_session_sync_client():
    from pysepal.solara.components.export import cancel_taskmanager_export

    sync = sync_client()
    sync.tasks = MagicMock()
    asyncio.run(cancel_taskmanager_export(sync, "sepal-123"))
    sync.tasks.cancel.assert_called_once_with("sepal-123")


# --- dialog wiring ----------------------------------------------------------


@pytest.mark.parametrize(
    ("backend", "clients", "expected"),
    [
        ("auto", ("sync",), {"gee", "drive", "sepal"}),
        ("auto", ("async",), {"gee", "drive", "sepal"}),
        ("auto", (), {"gee", "drive"}),
        ("direct", ("async",), {"gee", "drive"}),
        ("taskmanager", ("sync",), {"sepal"}),
        ("taskmanager", (), set()),
    ],
)
def test_dialog_offers_only_targets_the_backend_serves(backend, clients, expected):
    from pysepal.solara.components.export_hook import (
        _available_targets,
        get_target_items,
    )

    available = _available_targets(
        backend,
        object() if "sync" in clients else None,
        object() if "async" in clients else None,
    )
    assert available == expected
    items = get_target_items(None, available=available)
    assert {item["value"] for item in items if not item["disabled"]} == expected


def test_default_target_moves_to_an_available_one():
    from pysepal.solara.components.export_hook import _coerce_default_target

    assert _coerce_default_target("gee", frozenset({"sepal"})) == "sepal"
    assert _coerce_default_target("sepal", frozenset({"gee", "drive"})) == "gee"
    assert _coerce_default_target("drive", frozenset({"gee", "drive"})) == "drive"


def test_tracker_counts_taskmanager_steps():
    from pysepal.solara.components.export_hook import _tracker_step_count

    assert _tracker_step_count(request(), "taskmanager") == 3
    assert _tracker_step_count(request(), "direct") == 5


def test_submit_clears_the_previous_remote_task_id():
    import solara

    from pysepal.solara.components.export_hook import use_export_dialog

    seen = []

    @solara.component
    def Harness():
        controller = use_export_dialog(
            sources=[], gee_interface=MagicMock(), drive_interface=MagicMock()
        )

        def drive():
            controller._state.remote_task_id_ref.current = "SEPAL task `old`"
            controller._state.remote_submitted_ref.current = True
            controller.submit_export()
            seen.append(
                (
                    controller._state.remote_task_id_ref.current,
                    controller._state.remote_submitted_ref.current,
                )
            )

        solara.use_effect(drive, [])
        return solara.Text("driven")

    async def run():
        return Harness.widget()

    asyncio.run(run())
    assert seen == [(None, False)]
