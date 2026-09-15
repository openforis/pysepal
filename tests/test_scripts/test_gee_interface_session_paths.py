"""The session paths the GEE lane never reaches, driven against a fake session.

Collapsing ``GEEInterface`` onto its session in 4.0 made twelve previously
optional branches mandatory. The live GEE lane exercises eight of them; these
four it does not touch, so their only coverage before this file was the fact
that nobody had run them. That is exactly the state ``is_running_async`` was in
when it shipped with ``task["state"]`` on a pydantic model -- a live-credential,
six-minute failure for a bug that costs nothing to catch here.

What these assert is narrow on purpose: that the interface calls the ee-client
API it means to, with the arguments the caller gave it. Whether ee-client then
talks to Earth Engine correctly is the GEE lane's job, not this file's.

Real models rather than bare mocks wherever a model is involved. A ``MagicMock``
answers any attribute or subscript you invent, so it would have passed against
the ``task["state"]`` bug too.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from eeclient.tasks import Task

from pysepal.scripts.gee_interface import GEEInterface

ASSET_ROOT = "projects/some-project/assets"


def _task(name: str = "projects/p/operations/ABC123") -> Task:
    return Task.model_validate(
        {
            "name": name,
            "metadata": {
                "@type": "type.googleapis.com/google.earthengine.v1alpha.OperationMetadata",
                "state": "COMPLETED",
                "description": "my-export",
                "priority": 100,
                "createTime": "2026-08-17T10:00:00Z",
                "type": "EXPORT_IMAGE",
            },
        }
    )


@pytest.fixture
def interface():
    """An interface on a fake session, with every awaited call recorded."""
    session = MagicMock()
    session.get_assets_folder = AsyncMock(return_value=ASSET_ROOT)
    session.tasks.get_task_async = AsyncMock(return_value=None)
    session.operations.create_folder_async = AsyncMock(return_value={"id": "created"})
    session.export.table_to_drive_async = AsyncMock(return_value="table-task-id")
    session.export.image_to_drive_async = AsyncMock(return_value="image-task-id")
    session.export.image_to_asset_async = AsyncMock(return_value="asset-task-id")

    interface = GEEInterface(session=session)
    try:
        yield interface
    finally:
        interface.close()


def test_get_task_returns_the_ee_client_task_unchanged(interface):
    """The task object must reach the caller intact, not re-wrapped or coerced.

    ``export_engine`` reads its state through ``get_task_state_name``, which
    accepts a model, a dict or a legacy task -- so a silent change of type here
    would be absorbed there and surface much later as a stuck progress bar.
    """
    expected = _task()
    interface.session.tasks.get_task_async = AsyncMock(return_value=expected)

    assert interface.get_task("ABC123") is expected
    interface.session.tasks.get_task_async.assert_awaited_once_with("ABC123")


def test_get_task_passes_a_missing_task_through_as_none(interface):
    assert interface.get_task("nope") is None


def test_create_folder_sends_the_path_relative_to_the_asset_root(interface):
    """ee-client wants the path relative to the root; ``ee.data`` wanted it absolute.

    The deleted branch passed ``absolute_path`` to ``ee.data.createAsset`` while
    the session branch passes ``relative_path``. Now that only one survives, the
    wrong one would create ``projects/p/assets/projects/p/assets/reports``.
    """
    interface.create_folder("reports/2026")

    interface.session.operations.create_folder_async.assert_awaited_once_with("reports/2026")


def test_create_folder_accepts_an_absolute_path_and_still_sends_it_relative(interface):
    interface.create_folder(f"{ASSET_ROOT}/reports/2026")

    interface.session.operations.create_folder_async.assert_awaited_once_with("reports/2026")


def test_creating_the_asset_root_itself_never_calls_ee_client(interface):
    """An empty relative path is the root, which already exists."""
    result = interface.create_folder("")

    assert result == {"id": ASSET_ROOT}
    interface.session.operations.create_folder_async.assert_not_awaited()


def test_create_folder_refuses_a_path_outside_the_asset_root(interface):
    with pytest.raises(ValueError, match="outside the current asset root"):
        interface.create_folder("projects/someone-else/assets/theirs")

    interface.session.operations.create_folder_async.assert_not_awaited()


def test_export_table_to_drive_forwards_every_argument(interface):
    """The sync wrapper is camelCase while the async method is not.

    ``export_table_to_drive`` takes ``fileFormat`` / ``fileNamePrefix`` to mirror
    the Earth Engine API, and translates them to ``file_format`` /
    ``filename_prefix`` for the async method underneath. That wrapper is the only
    place the translation happens, so it is worth pinning.
    """
    collection = MagicMock()

    result = interface.export_table_to_drive(
        collection=collection,
        fileFormat="CSV",
        fileNamePrefix="prefix",
        folder="my-folder",
        description="my-table",
        selectors=["a", "b"],
        max_vertices=100,
        priority=7,
    )

    assert result == "table-task-id"
    interface.session.export.table_to_drive_async.assert_awaited_once_with(
        collection=collection,
        filename_prefix="prefix",
        file_format="CSV",
        folder="my-folder",
        description="my-table",
        selectors=["a", "b"],
        max_vertices=100,
        priority=7,
    )


def test_export_image_to_drive_forwards_every_argument(interface):
    image = MagicMock()
    region = MagicMock()

    result = interface.export_image_to_drive(
        image=image,
        description="my-image",
        folder="my-folder",
        filename_prefix="prefix",
        region=region,
        scale=30,
        crs="EPSG:4326",
        crs_transform=[1, 0, 0, 0, 1, 0],
        max_pixels=1e9,
        file_format="GeoTIFF",
        priority=7,
    )

    assert result == "image-task-id"
    interface.session.export.image_to_drive_async.assert_awaited_once_with(
        image=image,
        filename_prefix="prefix",
        folder="my-folder",
        file_format="GeoTIFF",
        description="my-image",
        max_pixels=1e9,
        region=region,
        scale=30,
        crs="EPSG:4326",
        crs_transform=[1, 0, 0, 0, 1, 0],
        priority=7,
    )


def test_export_image_to_asset_forwards_every_argument(interface):
    image = MagicMock()
    region = MagicMock()

    result = interface.export_image_to_asset(
        image=image,
        asset_id="projects/p/assets/x",
        description="my-image",
        region=region,
        scale=30,
        crs="EPSG:4326",
        crs_transform=[1, 0, 0, 0, 1, 0],
        max_pixels=1e9,
        priority=7,
    )

    assert result == "asset-task-id"
    interface.session.export.image_to_asset_async.assert_awaited_once_with(
        image=image,
        asset_id="projects/p/assets/x",
        description="my-image",
        max_pixels=1e9,
        grid=None,
        request_id=None,
        workload_tag=None,
        priority=7,
        region=region,
        scale=30,
        crs="EPSG:4326",
        crs_transform=[1, 0, 0, 0, 1, 0],
        pyramiding_policy=None,
        pyramiding_policy_overrides=None,
    )


def test_export_image_to_asset_forwards_the_pyramiding_policy(interface):
    """Issue #1042.

    The server default is ``MEAN``, which averages class codes in every
    overview of a categorical image. A caller asking for ``MODE`` has to reach
    ee-client, not be dropped here.
    """
    interface.export_image_to_asset(
        image=MagicMock(),
        asset_id="projects/p/assets/x",
        pyramiding_policy="mode",
        pyramiding_policy_overrides={"B1": "min"},
    )

    kwargs = interface.session.export.image_to_asset_async.await_args.kwargs
    assert kwargs["pyramiding_policy"] == "mode"
    assert kwargs["pyramiding_policy_overrides"] == {"B1": "min"}


@pytest.mark.parametrize(
    ("method", "removed"),
    [
        ("export_image_to_asset", "pyramid_policy"),
        ("export_image_to_drive", "dimensions"),
        ("export_image_to_drive", "skip_empty_tiles"),
        ("export_image_to_drive", "format_options"),
    ],
)
def test_the_parameters_only_the_deleted_branch_honoured_are_gone(method, removed):
    """Removed rather than left to be silently ignored.

    ee-client's export API accepts none of these, so keeping them would have
    meant a caller passing ``skip_empty_tiles=True`` and getting every empty
    tile anyway, with nothing raised. 4.0 removes them so the call fails loudly.
    """
    import inspect

    assert removed not in inspect.signature(getattr(GEEInterface, method)).parameters
