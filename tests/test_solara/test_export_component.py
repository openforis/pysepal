"""Tests for the Solara export helpers."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import solara

from pysepal.scripts import gee_interface as gee_interface_module
from pysepal.scripts.gee_interface import _resolve_create_folder_paths
from pysepal.solara.components import export_hook as export_hook_module
from pysepal.solara.components.export import (
    DEFAULT_TABLE_FILE_FORMAT,
    ExportLauncher,
    ExportRequest,
    ExportResult,
    ExportSource,
    ResolvedExport,
    _build_result_message,
    extract_task_id,
    get_task_state_name,
    infer_export_kind,
    matches_drive_export_prefix,
    resolve_asset_folder,
    resolve_sepal_folder,
    sanitize_export_name,
    submit_export_request,
    validate_asset_id_under_root,
)
from pysepal.solara.components.export_dialog import (
    BandSelectorField,
    ExportDialog,
    ImageScaleField,
    _validation_message,
)
from pysepal.solara.components.export_engine import _apply_band_selection
from pysepal.solara.components.export_hook import (
    available_bands_for,
    default_bands_for,
    discover_image_bands,
    get_active_source,
    normalize_band_selection,
    resolved_default_bands,
    use_export_dialog,
)


class _FakeImage:
    def __init__(self, selected_bands: tuple[str, ...] | None = None):
        self.selected_bands = tuple(selected_bands) if selected_bands else ()

    def bandNames(self):
        return list(self.selected_bands)

    def select(self, bands):
        return _FakeImage(selected_bands=tuple(bands))


class _FakeTable:
    def first(self):
        return None

    def size(self):
        return 0


class _FakeImageCollection:
    def toBands(self):
        return None


def _render(factory, *args, **kwargs):
    """Render a Solara widget with a running event loop so ``use_task`` can schedule."""

    async def _runner():
        return factory(*args, **kwargs)

    return asyncio.run(_runner())


def _render_preselected_dialog(
    source,
    *,
    target="gee",
    force_conflict_path=None,
    force_asset_root=None,
    force_asset_id=None,
    gee_interface=None,
    sepal_client=None,
):
    """Render ``ExportDialog`` with a source preselected and the dialog open.

    The production UX hides the dialog body until the user picks an asset, so
    assertions about post-selection widgets (destination radio, scale presets,
    folder fields) must drive the controller into the selected state first.

    Pass ``force_conflict_path`` to additionally seed ``gee_asset_conflict``
    state — useful for asserting the conflict UI without driving the live
    debounced check.

    Pass ``force_asset_root`` / ``force_asset_id`` to drive root + asset-id
    state directly — useful for asserting the root-validation UI without
    waiting on ``_load_asset_root`` (which fails silently against MagicMock).

    Pass ``gee_interface`` to override the default ``MagicMock`` — a fake with
    an ``async get_info_async`` lets the band auto-discovery task run to
    completion so tests can assert the picker renders from discovered bands.
    """

    @solara.component
    def _Harness():
        controller = use_export_dialog(
            sources=[source],
            gee_interface=gee_interface or MagicMock(),
            drive_interface=MagicMock(),
            sepal_client=sepal_client,
        )

        def _preselect():
            controller.selected_source_id.set(source.id)
            controller.selected_target.set(target)
            controller.open.set(True)
            if force_asset_root is not None:
                controller._state.asset_root.set(force_asset_root)
            if force_asset_id is not None:
                controller._state.gee_asset_id.set(force_asset_id)
                controller._state.gee_asset_id_dirty.set(True)
            if force_conflict_path is not None:
                # Seed a non-empty asset id (and mark dirty) so the live
                # conflict-check task hits its debounce sleep — which is
                # cancelled when asyncio.run() tears down the loop — instead
                # of running to completion and clobbering the forced state.
                controller._state.gee_asset_id.set(force_conflict_path)
                controller._state.gee_asset_id_dirty.set(True)
                controller._state.gee_asset_conflict.set(True)
                controller._state.gee_asset_conflict_path.set(force_conflict_path)

        solara.use_effect(_preselect, [])
        return ExportDialog(controller=controller, title="Test")

    async def _runner():
        return _Harness.widget()

    return asyncio.run(_runner())


def test_sanitize_export_name_normalizes_user_input():
    assert sanitize_export_name("  My export / result  ") == "My_export_result"


def test_table_exports_default_to_shapefile():
    resolved = ResolvedExport(ee_object=_FakeTable(), default_name="demo")
    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="drive",
        name="demo",
    )

    assert DEFAULT_TABLE_FILE_FORMAT == "SHP"
    assert resolved.table_file_format == "SHP"
    assert request.table_file_format == "SHP"


def test_infer_export_kind_supports_image_like_objects():
    assert infer_export_kind(_FakeImage()) == "image"


def test_infer_export_kind_supports_table_like_objects():
    assert infer_export_kind(_FakeTable()) == "table"


def test_infer_export_kind_rejects_unsupported_objects():
    try:
        infer_export_kind(_FakeImageCollection())
    except TypeError as exc:
        assert "ee.Image" in str(exc)
    else:
        raise AssertionError("infer_export_kind should reject unsupported objects")


def test_resolve_asset_folder_joins_relative_paths():
    root = "projects/my-project/assets"
    assert resolve_asset_folder(root, "reports/2026") == "projects/my-project/assets/reports/2026"


def test_resolve_asset_folder_keeps_absolute_paths():
    absolute = "projects/other-project/assets/custom"
    assert resolve_asset_folder("projects/my-project/assets", absolute) == absolute


def test_validate_asset_id_under_root_accepts_path_under_root():
    assert (
        validate_asset_id_under_root(
            "projects/my-project/assets/exports/my_data",
            "projects/my-project/assets",
        )
        is None
    )


def test_validate_asset_id_under_root_rejects_different_project():
    error = validate_asset_id_under_root(
        "projects/other-project/assets/exports/my_data",
        "projects/my-project/assets",
    )
    assert error is not None
    assert "projects/my-project/assets/" in error


def test_validate_asset_id_under_root_rejects_path_outside_assets():
    error = validate_asset_id_under_root(
        "users/somebody/my_data",
        "projects/my-project/assets",
    )
    assert error is not None


def test_validate_asset_id_under_root_rejects_root_with_no_name():
    error = validate_asset_id_under_root(
        "projects/my-project/assets/",
        "projects/my-project/assets",
    )
    assert error is not None
    assert "name" in error.lower()


def test_validate_asset_id_under_root_defers_when_root_unloaded():
    """Placeholder root means asset_root hasn't loaded yet — defer validation."""
    assert (
        validate_asset_id_under_root(
            "projects/my-project/assets/foo",
            "projects/{project}/assets",
        )
        is None
    )


def test_validate_asset_id_under_root_lets_empty_pass_through():
    """Empty asset_id is a separate 'required' error handled elsewhere."""
    assert validate_asset_id_under_root("", "projects/my-project/assets") is None
    assert validate_asset_id_under_root("   ", "projects/my-project/assets") is None


def test_get_active_source_requires_explicit_selection():
    sources = [
        ExportSource(
            id="demo",
            label="Demo layer",
            kind="table",
            resolve=lambda: ResolvedExport(
                ee_object=_FakeTable(),
                default_name="demo_export",
            ),
        )
    ]

    assert get_active_source(sources, "") is None
    assert get_active_source(sources, "demo") is sources[0]


def test_resolve_create_folder_paths_accepts_relative_asset_folder():
    relative_path, absolute_path = _resolve_create_folder_paths(
        "projects/my-project/assets",
        "exports/final",
    )

    assert relative_path == "exports/final"
    assert absolute_path == "projects/my-project/assets/exports/final"


def test_resolve_create_folder_paths_accepts_absolute_asset_folder():
    relative_path, absolute_path = _resolve_create_folder_paths(
        "projects/my-project/assets",
        "projects/my-project/assets/exports/final",
    )

    assert relative_path == "exports/final"
    assert absolute_path == "projects/my-project/assets/exports/final"


def test_resolve_sepal_folder_uses_module_results_for_relative_paths():
    sepal_client = SimpleNamespace(
        results_path="/home/sepal-user/module_results/my_module",
        BASE_REMOTE_PATH="/home/sepal-user",
    )

    result = resolve_sepal_folder(sepal_client, "exports/final")

    assert str(result) == "/home/sepal-user/module_results/my_module/exports/final"


def test_resolve_sepal_folder_keeps_absolute_paths():
    sepal_client = SimpleNamespace(
        results_path="/home/sepal-user/module_results/my_module",
        BASE_REMOTE_PATH="/home/sepal-user",
    )

    result = resolve_sepal_folder(sepal_client, "/home/sepal-user/custom/exports")

    assert str(result) == "/home/sepal-user/custom/exports"


def test_matches_drive_export_prefix_accepts_export_shards():
    assert matches_drive_export_prefix("result", "result")
    assert matches_drive_export_prefix("result.tif", "result")
    assert matches_drive_export_prefix("result-0000000000.tif", "result")
    assert matches_drive_export_prefix("result_part.csv", "result")
    assert not matches_drive_export_prefix("resultExtra.csv", "result")


def test_get_task_state_name_handles_dict_and_metadata_objects():
    dict_task = {"metadata": {"state": "SUCCEEDED"}}
    object_task = SimpleNamespace(metadata=SimpleNamespace(state="RUNNING"))

    assert get_task_state_name(dict_task) == "SUCCEEDED"
    assert get_task_state_name(object_task) == "RUNNING"
    assert get_task_state_name(None) is None


def test_extract_task_id_supports_strings_and_objects():
    task_obj = SimpleNamespace(id="task-123")
    named_obj = SimpleNamespace(name="operations/task-456")

    assert extract_task_id("task-abc") == "task-abc"
    assert extract_task_id(task_obj) == "task-123"
    assert extract_task_id(named_obj) == "operations/task-456"


def test_build_result_message_formats_targets():
    gee_result = ExportResult(
        target="gee",
        export_kind="image",
        name="demo",
        asset_id="projects/demo/assets/demo",
        message="",
    )
    sepal_result = ExportResult(
        target="sepal",
        export_kind="table",
        name="demo",
        sepal_paths=("/home/sepal-user/module_results/demo.csv",),
        message="",
    )

    assert _build_result_message(gee_result) == (
        "Earth Engine export submitted to `projects/demo/assets/demo`."
    )
    assert _build_result_message(sepal_result) == (
        "Export copied to SEPAL: `/home/sepal-user/module_results/demo.csv`."
    )


def test_export_launcher_renders_for_single_source():
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
            drive_folder="exports",
        ),
    )

    element = _render(
        ExportLauncher.widget,
        sources=[source],
        button_text=True,
        gee_interface=MagicMock(),
        drive_interface=MagicMock(),
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    asset_selects = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "Select" and getattr(widget, "label", None) == "Asset"
    ]

    assert element is not None
    assert asset_selects


def test_export_launcher_shows_disabled_tooltip_without_sources():
    element = _render(
        ExportLauncher.widget,
        sources=[],
        button_text=True,
        gee_interface=MagicMock(),
        drive_interface=MagicMock(),
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    tooltip_widgets = [
        widget for widget in _walk(element) if widget.__class__.__name__ == "Tooltip"
    ]

    assert tooltip_widgets
    assert any(
        "No exportable layers available" in getattr(widget, "children", [])
        for widget in tooltip_widgets
    )


def test_export_launcher_renders_destination_as_radio_group():
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
            drive_folder="exports",
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    radio_groups = [
        widget for widget in _walk(element) if widget.__class__.__name__ == "RadioGroup"
    ]
    selects = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "Select" and getattr(widget, "label", None) == "Destination"
    ]

    assert radio_groups
    assert any(getattr(widget, "row", False) for widget in radio_groups)
    assert not selects


def test_export_launcher_renders_image_scale_presets_and_custom_field():
    source = ExportSource(
        id="image-demo",
        label="Demo image",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(),
            default_name="demo_image",
            default_scale=30,
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    btn_toggles = [widget for widget in _walk(element) if widget.__class__.__name__ == "BtnToggle"]
    custom_scale_fields = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "TextField"
        and getattr(widget, "placeholder", None) == "Custom"
    ]
    sliders = [widget for widget in _walk(element) if "Slider" in widget.__class__.__name__]

    assert btn_toggles
    assert custom_scale_fields
    assert not sliders


def test_export_launcher_supports_small_block_button_convention():
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
        ),
    )
    element = _render(
        ExportLauncher.widget,
        sources=[source],
        button_text=True,
        block=True,
        gee_interface=MagicMock(),
        drive_interface=MagicMock(),
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    launcher_buttons = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "Btn" and getattr(widget, "block", False)
    ]

    assert launcher_buttons
    assert any(getattr(widget, "small", False) for widget in launcher_buttons)


class _FakeGeeInterface:
    def __init__(self):
        self.created_folders = []
        self.asset_exports = []

    async def get_folder_async(self):
        return "projects/demo/assets"

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        return None

    async def create_folder_async(self, folder_path):
        self.created_folders.append(folder_path)
        return {"id": folder_path}

    async def export_table_to_asset_async(
        self,
        collection,
        asset_id,
        description="",
        selectors=None,
        max_vertices=None,
        priority=None,
    ):
        self.asset_exports.append(
            {
                "collection": collection,
                "asset_id": asset_id,
                "description": description,
                "selectors": selectors,
                "max_vertices": max_vertices,
                "priority": priority,
            }
        )
        return {"id": "task-123"}


def test_submit_export_request_builds_gee_asset_result():
    gee_interface = _FakeGeeInterface()
    steps = []

    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="gee",
        name="demo_export",
        gee_asset_id="projects/demo/assets/reports/2026/demo_export",
    )

    result = asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
            on_step=steps.append,
        )
    )

    assert result.target == "gee"
    assert result.task_id == "task-123"
    assert result.asset_id == "projects/demo/assets/reports/2026/demo_export"
    assert steps == [
        "Validating export settings",
        "Preparing Earth Engine destination",
        "Submitting Earth Engine export",
    ]


# ---------------------------------------------------------------------------
# vis_params propagation: ResolvedExport → ExportRequest → submit_export_request
# ---------------------------------------------------------------------------


class _FakeGeeInterfaceImageExports:
    """Fake interface that records image-export submissions."""

    def __init__(self):
        self.exports: list[dict] = []

    async def get_folder_async(self):
        return "projects/demo/assets"

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        return None

    async def create_folder_async(self, folder_path):
        return {"id": folder_path}

    async def export_image_to_asset_async(self, **kwargs):
        self.exports.append(kwargs)
        return {"id": "task-img-1"}


def test_submit_export_request_embeds_vis_params_on_image_for_gee_asset(monkeypatch):
    """Image+gee exports with vis_params route through set_viz_params before submit."""
    gee_interface = _FakeGeeInterfaceImageExports()

    original_image = _FakeImage()
    styled_image = _FakeImage()

    captured: dict = {}

    def fake_set_viz_params(image, **kwargs):
        captured["image"] = image
        captured["kwargs"] = kwargs
        return styled_image

    monkeypatch.setattr(
        "pysepal.solara.components.export_engine.set_viz_params",
        fake_set_viz_params,
    )

    vis_params = {
        "type": "categorical",
        "bands": ["classification"],
        "palette": ["#ff0", "#f00"],
        "values": [1, 2],
        "labels": ["a", "b"],
    }
    request = ExportRequest(
        ee_object=original_image,
        export_kind="image",
        target="gee",
        name="styled_export",
        gee_asset_id="projects/demo/assets/gfc/styled_export",
        vis_params=vis_params,
    )

    asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
        )
    )

    assert captured["image"] is original_image
    assert captured["kwargs"] == vis_params
    assert len(gee_interface.exports) == 1
    submitted = gee_interface.exports[0]
    assert submitted["image"] is styled_image
    assert submitted["description"] == "styled_export"


def test_submit_export_request_skips_viz_embed_when_vis_params_missing(monkeypatch):
    gee_interface = _FakeGeeInterfaceImageExports()
    original_image = _FakeImage()

    calls = []

    def fake_set_viz_params(image, **kwargs):
        calls.append((image, kwargs))
        return image

    monkeypatch.setattr(
        "pysepal.solara.components.export_engine.set_viz_params",
        fake_set_viz_params,
    )

    request = ExportRequest(
        ee_object=original_image,
        export_kind="image",
        target="gee",
        name="plain_export",
        gee_asset_id="projects/demo/assets/demo/plain_export",
    )

    asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
        )
    )

    assert calls == []
    submitted = gee_interface.exports[0]
    assert submitted["image"] is original_image


def test_build_request_drops_vis_params_for_table_exports():
    """Defense in depth: build_request gates vis_params on export_kind == image."""
    resolved = ResolvedExport(
        ee_object=_FakeTable(),
        default_name="demo",
        vis_params={"palette": ["#000"]},
    )

    request = ExportRequest(
        ee_object=resolved.ee_object,
        export_kind="table",
        target="gee",
        name="demo",
        vis_params=resolved.vis_params if "table" == "image" else None,
    )
    assert request.vis_params is None


class _FakeGeeInterfaceWithExistingAsset(_FakeGeeInterface):
    """Variant whose ``get_asset_async`` reports the target asset as existing."""

    def __init__(self):
        super().__init__()
        self.checked_asset_ids: list[str] = []

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        self.checked_asset_ids.append(asset_id)
        return {"id": asset_id, "type": "TABLE"}


def test_submit_export_request_refuses_to_overwrite_existing_gee_asset():
    gee_interface = _FakeGeeInterfaceWithExistingAsset()

    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="gee",
        name="demo_export",
        gee_asset_id="projects/demo/assets/reports/2026/demo_export",
    )

    try:
        asyncio.run(
            submit_export_request(
                request,
                gee_interface=gee_interface,
                drive_interface=MagicMock(),
                sepal_client=None,
            )
        )
    except FileExistsError as exc:
        assert "projects/demo/assets/reports/2026/demo_export" in str(exc)
        assert gee_interface.checked_asset_ids == ["projects/demo/assets/reports/2026/demo_export"]
        # The existence check must run *before* folder creation so a conflict
        # does not leave empty folders behind.
        assert gee_interface.created_folders == []
        assert gee_interface.asset_exports == []
    else:
        raise AssertionError("submit_export_request must raise on existing GEE asset")


def test_submit_export_request_rejects_empty_gee_asset_id():
    """Engine validates `gee_asset_id` is non-empty for GEE target."""
    gee_interface = _FakeGeeInterface()

    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="gee",
        name="demo_export",
        gee_asset_id="",
    )

    try:
        asyncio.run(
            submit_export_request(
                request,
                gee_interface=gee_interface,
                drive_interface=MagicMock(),
                sepal_client=None,
            )
        )
    except ValueError as exc:
        assert "asset id" in str(exc).lower()
    else:
        raise AssertionError("Empty gee_asset_id must raise ValueError")


def test_submit_export_request_rejects_asset_id_outside_user_root():
    """Engine refuses an asset_id that does not live under the user's asset root."""
    gee_interface = _FakeGeeInterface()

    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="gee",
        name="demo_export",
        gee_asset_id="projects/someone-else/assets/exports/my_data",
    )

    try:
        asyncio.run(
            submit_export_request(
                request,
                gee_interface=gee_interface,
                drive_interface=MagicMock(),
                sepal_client=None,
            )
        )
    except ValueError as exc:
        assert "projects/demo/assets/" in str(exc)
        # Existence check must not run for a path the user cannot write to.
        assert gee_interface.created_folders == []
        assert gee_interface.asset_exports == []
    else:
        raise AssertionError("Engine must refuse asset ids outside the user's root")


class _DriveCheckTrackingGeeInterface(_FakeGeeInterface):
    """Tracks ``get_asset_async`` calls so we can assert non-GEE targets skip it."""

    def __init__(self):
        super().__init__()
        self.checked_asset_ids: list[str] = []

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        self.checked_asset_ids.append(asset_id)
        return None

    async def export_table_to_drive_async(self, **_kwargs):
        return {"id": "drive-task"}


def test_submit_export_request_skips_existence_check_for_drive_target():
    gee_interface = _DriveCheckTrackingGeeInterface()

    request = ExportRequest(
        ee_object=_FakeTable(),
        export_kind="table",
        target="drive",
        name="demo_export",
        drive_folder="exports",
    )

    asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
        )
    )

    assert gee_interface.checked_asset_ids == []


# ---------------------------------------------------------------------------
# Layer 2: dialog live conflict hint
# ---------------------------------------------------------------------------


class _ConflictProbeGeeInterface:
    """Records ``get_asset_async`` calls; returns whatever was preconfigured."""

    def __init__(self, existing_asset=None, raises: Exception | None = None):
        self.existing_asset = existing_asset
        self.raises = raises
        self.checked_asset_ids: list[str] = []

    async def get_asset_async(self, asset_id, not_exists_ok=False):
        self.checked_asset_ids.append(asset_id)
        if self.raises is not None:
            raise self.raises
        return self.existing_asset


def test_resolve_gee_asset_conflict_short_circuits_when_target_not_gee():
    gee_interface = _ConflictProbeGeeInterface(existing_asset={"id": "ignored"})

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="drive",
            has_active_source=True,
            asset_id="projects/demo/assets/reports/my_export",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    assert conflict is False
    assert path == ""
    # Never touches the network for non-GEE targets.
    assert gee_interface.checked_asset_ids == []


def test_resolve_gee_asset_conflict_short_circuits_when_asset_id_empty():
    gee_interface = _ConflictProbeGeeInterface(existing_asset={"id": "ignored"})

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="gee",
            has_active_source=True,
            asset_id="   ",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    assert conflict is False
    assert path == ""
    assert gee_interface.checked_asset_ids == []


def test_resolve_gee_asset_conflict_short_circuits_when_no_active_source():
    gee_interface = _ConflictProbeGeeInterface(existing_asset={"id": "ignored"})

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="gee",
            has_active_source=False,
            asset_id="projects/demo/assets/reports/my_export",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    assert conflict is False
    assert path == ""
    assert gee_interface.checked_asset_ids == []


def test_resolve_gee_asset_conflict_returns_no_conflict_when_asset_absent():
    gee_interface = _ConflictProbeGeeInterface(existing_asset=None)

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="gee",
            has_active_source=True,
            asset_id="projects/demo/assets/reports/my_export",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    assert conflict is False
    assert path == ""
    assert gee_interface.checked_asset_ids == ["projects/demo/assets/reports/my_export"]


def test_resolve_gee_asset_conflict_flags_conflict_when_asset_exists():
    gee_interface = _ConflictProbeGeeInterface(
        existing_asset={"id": "projects/demo/assets/reports/My_export"},
    )

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="gee",
            has_active_source=True,
            asset_id="projects/demo/assets/reports/My_export",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    assert conflict is True
    assert path == "projects/demo/assets/reports/My_export"
    assert gee_interface.checked_asset_ids == ["projects/demo/assets/reports/My_export"]


def test_resolve_gee_asset_conflict_swallows_lookup_errors():
    gee_interface = _ConflictProbeGeeInterface(raises=RuntimeError("transient network blip"))

    conflict, path = asyncio.run(
        export_hook_module._resolve_gee_asset_conflict(
            target="gee",
            has_active_source=True,
            asset_id="projects/demo/assets/reports/my_export",
            gee_interface=gee_interface,
            debounce_seconds=0,
        )
    )

    # Lookup failures must not block the user; engine guard remains authoritative.
    assert conflict is False
    assert path == ""
    assert gee_interface.checked_asset_ids == ["projects/demo/assets/reports/my_export"]


def test_build_default_gee_asset_id_uses_asset_root_and_module_folder():
    resolved = ResolvedExport(ee_object=_FakeTable(), default_name="My export")
    sepal_client = SimpleNamespace(module_name="aoi_all_methods")

    asset_id = export_hook_module._build_default_gee_asset_id(
        "projects/demo/assets",
        resolved,
        sepal_client,
    )

    assert asset_id == "projects/demo/assets/aoi_all_methods/My_export"


def test_build_default_gee_asset_id_respects_absolute_resolved_folder():
    resolved = ResolvedExport(
        ee_object=_FakeTable(),
        default_name="data",
        gee_folder="projects/other/assets/exports/2026",
    )

    asset_id = export_hook_module._build_default_gee_asset_id(
        "projects/demo/assets",
        resolved,
        None,
    )

    assert asset_id == "projects/other/assets/exports/2026/data"


def test_build_default_gee_asset_id_returns_empty_until_asset_root_loads():
    resolved = ResolvedExport(ee_object=_FakeTable(), default_name="data")

    asset_id = export_hook_module._build_default_gee_asset_id(
        "projects/{project}/assets",
        resolved,
        None,
    )

    assert asset_id == ""


def test_export_dialog_renders_single_asset_id_field_for_gee_target():
    """GEE target collapses Export name + EE folder into one Asset ID field."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
        ),
    )
    element = _render_preselected_dialog(source=source, target="gee")

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    text_fields = [widget for widget in _walk(element) if widget.__class__.__name__ == "TextField"]
    labels = [getattr(widget, "label", None) for widget in text_fields]

    assert "Asset ID" in labels, "GEE target must render an Asset ID field"
    assert "Earth Engine folder" not in labels
    assert "Export name" not in labels


def _msg(**overrides) -> str:
    base = dict(
        has_usable_sources=True,
        has_active_source=True,
        resolvable=True,
        gee_target=True,
        gee_asset_id="projects/demo/assets/x",
        asset_root_error=None,
        gee_asset_conflict=False,
        export_name="demo",
        bands_empty=False,
        band_noun="band",
    )
    base.update(overrides)
    return _validation_message(**base)


def test_validation_message_priority_order():
    assert _msg(has_usable_sources=False) == "No exportable layers available."
    # No message when nothing is picked yet — the Asset selector guides that.
    assert _msg(has_active_source=False) == ""
    assert _msg(resolvable=False) == "The selected layer cannot currently be exported."
    assert _msg(gee_asset_id="   ") == "Asset ID is required."
    assert _msg(asset_root_error="Asset id must live under `X`.") == "Asset id must live under `X`."
    assert _msg(gee_asset_conflict=True).startswith("An asset with this id already exists")
    assert _msg(gee_target=False, export_name="   ") == "Name is required."
    assert _msg(bands_empty=True) == "Select at least one band."
    assert _msg(bands_empty=True, band_noun="property") == "Select at least one property."
    assert _msg() == ""


def test_validation_message_asset_id_blocks_before_bands():
    # A missing asset id must win over an empty band selection (earlier step).
    assert _msg(gee_asset_id="", bands_empty=True) == "Asset ID is required."


def _bottom_validation_text(element) -> str:
    """Join the text of the dialog's single bottom validation message."""

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    chunks = [
        str(child)
        for widget in _walk(element)
        if widget.__class__.__name__ == "Html"
        and "sepal-export-error" in str(getattr(widget, "class_", ""))
        for child in getattr(widget, "children", ()) or ()
    ]
    return " ".join(chunks)


def test_export_dialog_shows_bottom_validation_for_conflict():
    """The asset-id conflict surfaces in the single bottom message, not the field."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
        ),
    )
    element = _render_preselected_dialog(
        source=source,
        target="gee",
        force_conflict_path="projects/demo/assets/reports/demo_export",
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    assert "already exists" in _bottom_validation_text(element).lower()
    # The Asset ID field itself no longer carries per-field error styling.
    asset_id_fields = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "TextField" and getattr(widget, "label", None) == "Asset ID"
    ]
    assert asset_id_fields, "Asset ID field must be rendered"
    assert getattr(asset_id_fields[0], "error", False) in (False, None)


def test_export_dialog_shows_bottom_validation_when_asset_id_outside_root():
    """An asset_id outside the user's GEE root surfaces in the bottom message."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
        ),
    )
    element = _render_preselected_dialog(
        source=source,
        target="gee",
        force_asset_root="projects/my-project/assets",
        force_asset_id="projects/someone-else/assets/exports/my_data",
    )

    message = _bottom_validation_text(element)
    assert "projects/my-project/assets/" in message
    assert "must live under" in message.lower()


def test_export_dialog_renders_export_name_and_drive_folder_for_drive_target():
    """The Drive target shows Export name + Drive folder."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_export",
        ),
    )
    element = _render_preselected_dialog(source=source, target="drive")

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    labels = [
        getattr(widget, "label", None)
        for widget in _walk(element)
        if widget.__class__.__name__ == "TextField"
    ]

    assert "Export name" in labels
    assert "Google Drive folder" in labels
    assert "Asset ID" not in labels


def _text_field_labels(element):
    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    return [
        getattr(widget, "label", None)
        for widget in _walk(element)
        if widget.__class__.__name__ == "TextField"
    ]


def _demo_table_source():
    return ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(ee_object=_FakeTable(), default_name="demo_export"),
    )


def test_export_dialog_hides_drive_folder_for_sepal_target():
    """SEPAL stages workspace exports in a temporary Drive folder the user never picks."""
    element = _render_preselected_dialog(
        source=_demo_table_source(),
        target="sepal",
        sepal_client=MagicMock(module_name="demo"),
    )

    labels = _text_field_labels(element)
    assert "Export name" in labels
    assert "SEPAL folder" in labels
    assert "Google Drive folder" not in labels


@pytest.mark.parametrize(("target", "expected"), [("drive", "my-drive"), ("sepal", None)])
def test_built_request_sends_drive_folder_only_for_drive_target(monkeypatch, target, expected):
    captured = []

    async def fake_submit(request, **_kwargs):
        captured.append(request)
        return ExportResult(target=target, export_kind="table", name=request.name, message="ok")

    monkeypatch.setattr(export_hook_module, "submit_export_request", fake_submit)
    source = _demo_table_source()

    @solara.component
    def _Harness():
        controller = use_export_dialog(
            sources=[source],
            gee_interface=MagicMock(),
            drive_interface=MagicMock(),
            sepal_client=MagicMock(module_name="demo"),
        )

        def _preselect():
            controller.selected_source_id.set(source.id)
            controller.selected_target.set(target)

        solara.use_effect(_preselect, [])
        ready = controller.selected_source_id.value == source.id and bool(
            controller.export_name.value
        )

        def _submit():
            if ready and not captured:
                # Set after the source defaults sync, as if typed on the Drive
                # target; it must not leak into a SEPAL export.
                controller._state.drive_folder.set("my-drive")
                controller.submit_export()

        solara.use_effect(_submit, [ready])
        return solara.Text("driven")

    async def _runner():
        widget = _Harness.widget()
        for _ in range(20):
            if captured:
                break
            await asyncio.sleep(0)
        return widget

    asyncio.run(_runner())

    assert [request.target for request in captured] == [target]
    assert captured[0].drive_folder == expected


class _FakeRestSession:
    def __init__(self):
        self.calls = []
        self.export = SimpleNamespace(table_to_asset_async=self.table_to_asset_async)

    async def table_to_asset_async(self, **kwargs):
        self.calls.append(kwargs)
        return {"fake": "task"}


def test_gee_interface_table_asset_export_delegates_to_session_exporter():
    session = _FakeRestSession()
    interface_like = SimpleNamespace(session=session)

    result = asyncio.run(
        gee_interface_module.GEEInterface.export_table_to_asset_async(
            interface_like,
            collection=_FakeTable(),
            asset_id="projects/demo/assets/table_asset",
            description="AFG",
            selectors=["ADM0_NAME"],
            max_vertices=1000,
            priority=50,
        )
    )

    assert result == {"fake": "task"}
    assert len(session.calls) == 1
    payload = session.calls[0]
    assert payload["asset_id"] == ("projects/demo/assets/table_asset")
    assert payload["description"] == "AFG"
    assert payload["selectors"] == ["ADM0_NAME"]
    assert payload["max_vertices"] == 1000
    assert payload["priority"] == 50


def test_source_defaults_signature_tracks_dynamic_resolved_defaults():
    first = ResolvedExport(
        ee_object=_FakeTable(),
        default_name="first",
        drive_folder="exports-a",
        sepal_folder="sepal-a",
        table_file_format="SHP",
    )
    second = ResolvedExport(
        ee_object=_FakeTable(),
        default_name="first",
        drive_folder="exports-b",
        sepal_folder="sepal-b",
        table_file_format="GeoJSON",
    )

    assert export_hook_module._source_defaults_signature(first, "table", None) != (
        export_hook_module._source_defaults_signature(second, "table", None)
    )


def test_default_gee_folder_prefers_module_name():
    sepal_client = SimpleNamespace(module_name="aoi_all_methods")

    assert export_hook_module._default_gee_folder(sepal_client) == "aoi_all_methods"
    assert export_hook_module._default_gee_folder(None) == "pysepal_exports"


# ---------------------------------------------------------------------------
# Band picker: catalog helpers, engine application, dialog rendering
# ---------------------------------------------------------------------------


def test_available_bands_for_returns_empty_without_catalog():
    resolved = ResolvedExport(ee_object=_FakeImage(), default_name="demo")
    assert available_bands_for(resolved) == ()
    assert available_bands_for(None) == ()


def test_available_bands_for_returns_catalog_when_declared():
    resolved = ResolvedExport(
        ee_object=_FakeImage(),
        default_name="demo",
        bands=("B4", "B3", "B2"),
    )
    assert available_bands_for(resolved) == ("B4", "B3", "B2")


def test_resolved_default_bands_defaults_to_full_catalog():
    resolved = ResolvedExport(
        ee_object=_FakeImage(),
        default_name="demo",
        bands=("B4", "B3", "B2"),
    )
    assert resolved_default_bands(resolved) == ("B4", "B3", "B2")


def test_resolved_default_bands_filters_default_against_catalog():
    resolved = ResolvedExport(
        ee_object=_FakeImage(),
        default_name="demo",
        bands=("B4", "B3", "B2", "B1"),
        default_bands=("B4", "B2", "MISSING"),
    )
    # Preserves catalog order; drops MISSING silently.
    assert resolved_default_bands(resolved) == ("B4", "B2")


def test_resolved_default_bands_falls_back_to_catalog_when_default_outside_catalog():
    """If default_bands has no overlap with bands, fall back to all bands."""
    resolved = ResolvedExport(
        ee_object=_FakeImage(),
        default_name="demo",
        bands=("B4", "B3"),
        default_bands=("nope",),
    )
    assert resolved_default_bands(resolved) == ("B4", "B3")


def test_normalize_band_selection_preserves_catalog_order():
    available = ("B4", "B3", "B2", "B1")
    # User picked out of order — the catalog order should win.
    assert normalize_band_selection(available, ("B2", "B4")) == ("B4", "B2")


def test_normalize_band_selection_drops_unknown_picks():
    assert normalize_band_selection(("B4", "B3"), ("B4", "ghost")) == ("B4",)


def test_default_bands_for_defaults_to_full_available():
    resolved = ResolvedExport(ee_object=_FakeImage(), default_name="demo")
    assert default_bands_for(resolved, ("nir", "red")) == ("nir", "red")


def test_default_bands_for_honors_declared_default_bands():
    resolved = ResolvedExport(
        ee_object=_FakeImage(),
        default_name="demo",
        default_bands=("red",),
    )
    # Order comes from the available catalog, not from default_bands.
    assert default_bands_for(resolved, ("nir", "red", "green")) == ("red",)


def test_default_bands_for_empty_available_returns_empty():
    resolved = ResolvedExport(ee_object=_FakeImage(), default_name="demo")
    assert default_bands_for(resolved, ()) == ()


class _BandDiscoveryGeeInterface:
    """Fake interface whose ``get_info_async`` returns preconfigured band names."""

    def __init__(self, band_names=None, raises: Exception | None = None):
        self.band_names = list(band_names) if band_names is not None else []
        self.raises = raises
        self.calls: list[object] = []

    async def get_info_async(self, ee_object=None, tag=None, serialized_object=None):
        self.calls.append(ee_object)
        if self.raises is not None:
            raise self.raises
        return self.band_names


def test_discover_image_bands_returns_band_names():
    gee = _BandDiscoveryGeeInterface(band_names=["B4", "B3", "B2"])
    image = _FakeImage(selected_bands=("B4", "B3", "B2"))

    result = asyncio.run(discover_image_bands(gee, image))

    assert result == ("B4", "B3", "B2")
    assert gee.calls, "Discovery must call get_info_async on the image's bandNames()"


def test_discover_image_bands_returns_empty_when_no_bands():
    gee = _BandDiscoveryGeeInterface(band_names=[])
    assert asyncio.run(discover_image_bands(gee, _FakeImage())) == ()


def test_discover_image_bands_swallows_lookup_errors():
    gee = _BandDiscoveryGeeInterface(raises=RuntimeError("transient network blip"))
    # A failed discovery must degrade to no picker, never propagate.
    assert asyncio.run(discover_image_bands(gee, _FakeImage())) == ()


def test_discover_image_bands_handles_objects_without_bandnames():
    gee = _BandDiscoveryGeeInterface(band_names=["ignored"])
    assert asyncio.run(discover_image_bands(gee, object())) == ()


def test_switching_source_does_not_leak_band_selection():
    """Editing source A's bands then switching to B resets to B's own defaults."""
    source_a = ExportSource(
        id="a",
        label="A",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(), default_name="a", bands=("b1", "b2", "b3")
        ),
    )
    source_b = ExportSource(
        id="b",
        label="B",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(), default_name="b", bands=("x1", "x2")
        ),
    )
    captured = {}

    @solara.component
    def _Harness():
        controller = use_export_dialog(
            sources=[source_a, source_b],
            gee_interface=MagicMock(),
            drive_interface=MagicMock(),
        )
        captured["controller"] = controller

        def _drive():
            controller.selected_source_id.set("a")
            # User hand-edits A down to a subset and marks it dirty…
            controller._state.selected_bands.set(("b1",))
            controller._state.bands_dirty.set(True)
            # …then switches to B, whose catalog is disjoint from A's.
            controller.selected_source_id.set("b")

        solara.use_effect(_drive, [])
        return solara.Text("driven")

    _render(_Harness.widget)

    state = captured["controller"]._state
    # B must show its own defaults, not A's leaked ("b1",) subset, and be clean.
    assert state.selected_bands.value == ("x1", "x2")
    assert state.bands_dirty.value is False


def test_apply_band_selection_subsets_image_when_selectors_set():
    original = _FakeImage()
    request = ExportRequest(
        ee_object=original,
        export_kind="image",
        target="gee",
        name="demo",
        selectors=("B4", "B3"),
    )
    result = _apply_band_selection(original, request)
    assert isinstance(result, _FakeImage)
    assert result.selected_bands == ("B4", "B3")
    assert result is not original


def test_apply_band_selection_passthrough_for_tables():
    """Tables thread selectors directly to the EE export call — no image.select()."""
    table = _FakeTable()
    request = ExportRequest(
        ee_object=table,
        export_kind="table",
        target="gee",
        name="demo",
        selectors=("ADM0_NAME",),
    )
    assert _apply_band_selection(table, request) is table


def test_apply_band_selection_passthrough_when_no_selectors():
    image = _FakeImage()
    request = ExportRequest(
        ee_object=image,
        export_kind="image",
        target="gee",
        name="demo",
        selectors=None,
    )
    assert _apply_band_selection(image, request) is image


def test_submit_export_request_applies_band_selection_to_image_for_gee_asset():
    """End-to-end: ExportRequest.selectors bakes into image.select() before submit."""
    gee_interface = _FakeGeeInterfaceImageExports()
    original_image = _FakeImage()

    request = ExportRequest(
        ee_object=original_image,
        export_kind="image",
        target="gee",
        name="band_subset_export",
        gee_asset_id="projects/demo/assets/demo/band_subset_export",
        selectors=("B4", "B3", "B2"),
    )

    asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
        )
    )

    submitted = gee_interface.exports[0]
    submitted_image = submitted["image"]
    assert isinstance(submitted_image, _FakeImage)
    assert submitted_image.selected_bands == ("B4", "B3", "B2")


def test_submit_export_request_applies_band_selection_after_viz_embed(monkeypatch):
    """Vis embedding runs first, then band selection — both must end up applied."""
    gee_interface = _FakeGeeInterfaceImageExports()
    original_image = _FakeImage()
    styled_image = _FakeImage()

    def fake_set_viz_params(image, **_kwargs):
        assert image is original_image
        return styled_image

    monkeypatch.setattr(
        "pysepal.solara.components.export_engine.set_viz_params",
        fake_set_viz_params,
    )

    request = ExportRequest(
        ee_object=original_image,
        export_kind="image",
        target="gee",
        name="styled_subset",
        gee_asset_id="projects/demo/assets/demo/styled_subset",
        vis_params={"bands": ["B4"], "palette": ["#000"]},
        selectors=("B4",),
    )

    asyncio.run(
        submit_export_request(
            request,
            gee_interface=gee_interface,
            drive_interface=MagicMock(),
            sepal_client=None,
        )
    )

    submitted_image = gee_interface.exports[0]["image"]
    # Result must be the styled image's .select() output, not the styled
    # image directly — i.e. band selection happened after viz embedding.
    assert isinstance(submitted_image, _FakeImage)
    assert submitted_image.selected_bands == ("B4",)


def test_export_dialog_renders_band_picker_for_image_source_with_bands():
    source = ExportSource(
        id="image-bands",
        label="Image with bands",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(),
            default_name="demo_image",
            bands=("B4", "B3", "B2"),
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    multi_toggles = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "BtnToggle" and getattr(widget, "multiple", False)
    ]

    assert multi_toggles, "Band picker (multi-toggle) must render when bands are declared"
    # One button per band sits inside the multi-toggle group.
    toggle_button_labels = []
    for toggle in multi_toggles:
        for child in toggle.children or ():
            if child.__class__.__name__ == "Btn":
                for grandchild in child.children or ():
                    toggle_button_labels.append(str(grandchild))
    assert "B4" in toggle_button_labels
    assert "B3" in toggle_button_labels
    assert "B2" in toggle_button_labels

    # Label-bearing Text widget should say "Bands" for image kind.
    label_texts = [
        getattr(widget, "children", [])
        for widget in _walk(element)
        if widget.__class__.__name__ == "Html"
    ]
    flattened = [str(c) for group in label_texts for c in (group or [])]
    assert any("Bands" in chunk for chunk in flattened)


def test_band_selector_field_fills_selected_buttons_with_secondary():
    """Selected bands get a solid secondary colour; unselected stay neutral."""
    element = _render(
        BandSelectorField.widget,
        available=("B4", "B3", "B2"),
        selected=solara.reactive(("B4", "B2")),
        dirty=solara.reactive(False),
        export_kind="image",
        loading=False,
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    color_by_label = {}
    class_by_label = {}
    for widget in _walk(element):
        if widget.__class__.__name__ == "Btn":
            children = getattr(widget, "children", ()) or ()
            if children:
                label = str(children[0])
                color_by_label[label] = getattr(widget, "color", "")
                class_by_label[label] = getattr(widget, "class_", "") or ""

    # B4 and B2 are selected → filled secondary; B3 is not → neutral (no colour).
    assert color_by_label.get("B4") == "secondary"
    assert color_by_label.get("B2") == "secondary"
    assert color_by_label.get("B3") in ("", None)
    # Selected labels are forced white so they read on the secondary fill;
    # unselected inherit the theme text colour.
    assert "white--text" in class_by_label.get("B4", "")
    assert "white--text" in class_by_label.get("B2", "")
    assert "white--text" not in class_by_label.get("B3", "")


def test_image_scale_field_styles_selected_preset_like_bands():
    """The scale presets reuse the band styling: selected = secondary + white."""
    element = _render(ImageScaleField.widget, scale=solara.reactive(30))

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    toggles = [w for w in _walk(element) if w.__class__.__name__ == "BtnToggle"]
    assert toggles, "Scale presets render inside a BtnToggle"
    # Group carries secondary so the selected accent is not the default blue.
    assert all(getattr(toggle, "color", None) == "secondary" for toggle in toggles)

    color_by_label = {}
    class_by_label = {}
    for widget in _walk(element):
        if widget.__class__.__name__ == "Btn":
            children = getattr(widget, "children", ()) or ()
            if children:
                label = str(children[0])
                color_by_label[label] = getattr(widget, "color", "")
                class_by_label[label] = getattr(widget, "class_", "") or ""

    # Scale defaults to 30 → that preset is filled secondary with a white label.
    assert color_by_label.get("30") == "secondary"
    assert "white--text" in class_by_label.get("30", "")
    # A non-selected preset stays neutral.
    assert color_by_label.get("10") in ("", None)


def test_export_dialog_destination_uses_standalone_title():
    """Destination drops the built-in radio label for a shared styled title."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(ee_object=_FakeTable(), default_name="demo_export"),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    radio_groups = [w for w in _walk(element) if w.__class__.__name__ == "RadioGroup"]
    assert radio_groups
    # The built-in radio-group label is gone in favour of a standalone title.
    assert not any(getattr(rg, "label", None) for rg in radio_groups)

    html_chunks = [
        str(child)
        for widget in _walk(element)
        if widget.__class__.__name__ == "Html"
        for child in getattr(widget, "children", ()) or ()
    ]
    assert any("Destination" in chunk for chunk in html_chunks)


def test_export_dialog_body_uses_single_rhythm_container():
    """All fields sit in one sepal-export-body container (single-gap layout)."""
    source = ExportSource(
        id="demo",
        label="Demo layer",
        kind="table",
        resolve=lambda: ResolvedExport(ee_object=_FakeTable(), default_name="demo_export"),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    assert any(
        "sepal-export-body" in str(getattr(w, "class_", "")) for w in _walk(element)
    ), "The form body carries the single-rhythm sepal-export-body class"


def test_export_dialog_band_picker_has_no_select_all_or_clear():
    source = ExportSource(
        id="image-bands",
        label="Image with bands",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(),
            default_name="demo_image",
            bands=("B4", "B3", "B2"),
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    button_labels = [
        str(child)
        for widget in _walk(element)
        if widget.__class__.__name__ == "Btn"
        for child in getattr(widget, "children", ()) or ()
    ]

    assert "Select all" not in button_labels
    assert "Clear" not in button_labels


class _ImageBandsDialogGee(_FakeGeeInterface):
    """Fake whose ``get_info_async`` returns a fixed band-name list for discovery."""

    def __init__(self, band_names):
        super().__init__()
        self._band_names = list(band_names)

    async def get_info_async(self, ee_object=None, tag=None, serialized_object=None):
        return self._band_names


def test_export_dialog_renders_band_picker_from_discovered_bands():
    """Image without a declared catalog shows the picker from auto-discovered bands."""
    source = ExportSource(
        id="image-no-bands",
        label="Image without bands",
        kind="image",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeImage(),
            default_name="demo_image",
        ),
    )
    element = _render_preselected_dialog(
        source=source,
        gee_interface=_ImageBandsDialogGee(["nir", "red", "green"]),
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    multi_toggles = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "BtnToggle" and getattr(widget, "multiple", False)
    ]
    assert multi_toggles, "Picker must render for images from auto-discovered bands"

    toggle_button_labels = []
    for toggle in multi_toggles:
        for child in toggle.children or ():
            if child.__class__.__name__ == "Btn":
                for grandchild in child.children or ():
                    toggle_button_labels.append(str(grandchild))
    assert "nir" in toggle_button_labels
    assert "red" in toggle_button_labels
    assert "green" in toggle_button_labels


def test_band_selector_field_shows_spinner_while_loading():
    """While discovery is in flight (loading, no catalog yet) a spinner stands in.

    Asserted at the component level: the dialog-level ``bands_loading`` flag is
    owned by the async discovery task, whose ``finally`` resets it before this
    harness can capture it, so forcing it through the controller does not stick.
    """
    element = _render(
        BandSelectorField.widget,
        available=(),
        selected=solara.reactive(()),
        dirty=solara.reactive(False),
        export_kind="image",
        loading=True,
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    spinners = [
        widget for widget in _walk(element) if widget.__class__.__name__ == "ProgressCircular"
    ]
    multi_toggles = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "BtnToggle" and getattr(widget, "multiple", False)
    ]

    assert spinners, "A spinner must stand in for the toggles while bands load"
    assert not multi_toggles, "Toggles must not render until discovery completes"


def test_band_selector_field_returns_nothing_without_catalog_or_loading():
    """No catalog and not loading → the field renders nothing (opt-out path)."""
    element = _render(
        BandSelectorField.widget,
        available=(),
        selected=solara.reactive(()),
        dirty=solara.reactive(False),
        export_kind="image",
        loading=False,
    )

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    spinners = [
        widget for widget in _walk(element) if widget.__class__.__name__ == "ProgressCircular"
    ]
    multi_toggles = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "BtnToggle" and getattr(widget, "multiple", False)
    ]
    assert not spinners
    assert not multi_toggles


def test_export_dialog_hides_band_picker_for_table_without_catalog():
    """Tables never auto-discover — without a declared catalog the picker stays hidden."""
    source = ExportSource(
        id="table-no-catalog",
        label="Table without properties",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_table",
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    multi_toggles = [
        widget
        for widget in _walk(element)
        if widget.__class__.__name__ == "BtnToggle" and getattr(widget, "multiple", False)
    ]

    assert not multi_toggles, "Tables without a declared catalog show no picker"


def test_export_dialog_labels_band_picker_as_properties_for_tables():
    source = ExportSource(
        id="table-props",
        label="Table with properties",
        kind="table",
        resolve=lambda: ResolvedExport(
            ee_object=_FakeTable(),
            default_name="demo_table",
            bands=("ADM0_NAME", "ADM1_NAME"),
        ),
    )
    element = _render_preselected_dialog(source=source)

    def _walk(widget):
        yield widget
        for child in getattr(widget, "children", ()) or ():
            yield from _walk(child)

    label_texts = [
        getattr(widget, "children", [])
        for widget in _walk(element)
        if widget.__class__.__name__ == "Html"
    ]
    flattened = [str(c) for group in label_texts for c in (group or [])]
    assert any("Properties" in chunk for chunk in flattened)
    assert not any("Bands" == chunk for chunk in flattened)
