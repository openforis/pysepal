"""The dict-valued input components honour a value set from outside."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import reacton
import solara

import pysepal.solara.components.inputs.asset_select as asset_select_mod
from pysepal.message import msg
from pysepal.solara.components.inputs.asset_select import AssetSelectComponent
from pysepal.solara.components.inputs.point_selector import PointsSelectorComponent
from pysepal.solara.components.inputs.vector_selector import VectorSelectorComponent

from ._harness import find_by_label, of_type, render_and_drain, wait_until

VECTORS = Path(__file__).resolve().parents[1] / "data" / "aoi_manual" / "manual_polygons.geojson"
pytestmark = pytest.mark.usefixtures("empty_file_browser")


def _render(component):
    async def _runner():
        root, rc = reacton.render(component(), handle_error=False)
        rc.close()
        return root

    return asyncio.run(_runner())


def _fake_gee_interface():
    interface = MagicMock()

    async def _folder():
        return "projects/x/assets"

    async def _assets(_folder_path):
        return [{"id": "projects/x/assets/aoi", "type": "TABLE"}]

    async def _asset(_asset_id):
        return {"type": "TABLE"}

    async def _info(_obj):
        if _obj[0] == "values":
            return ["north", "south"]
        return {"properties": {"region": "north"}}

    interface.get_folder_async = _folder
    interface.get_assets_async = _assets
    interface.get_asset_async = _asset
    interface.get_info_async = _info
    return interface


@pytest.fixture
def _no_live_ee(monkeypatch):
    """Stop the asset picker building real ee objects.

    ``on_asset_change`` and ``on_column_change`` construct
    ``ee.FeatureCollection(asset_id)`` directly, before any call reaches the faked
    interface. Without Earth Engine initialised that raises, the generic handler
    nulls the value, and the test never gets as far as the behaviour it checks.
    """

    def feature_collection(aid):
        collection = MagicMock()
        collection.first.return_value = ("properties", aid)
        collection.distinct.return_value.aggregate_array.side_effect = lambda column: (
            "values",
            aid,
            column,
        )
        return collection

    monkeypatch.setattr(asset_select_mod.ee, "FeatureCollection", feature_collection)


def test_asset_select_seeds_the_combobox_from_an_external_value(_no_live_ee):
    held = solara.reactive(
        {"asset_id": "projects/x/assets/aoi", "type": "TABLE", "column": "ALL", "value": None}
    )

    @solara.component
    def _Harness():
        AssetSelectComponent(value=held, gee_interface=_fake_gee_interface())

    root = _render(_Harness)
    comboboxes = of_type(root, "Combobox")

    assert comboboxes
    assert comboboxes[0].v_model == "projects/x/assets/aoi"


def test_asset_select_keeps_a_restored_column_filter(_no_live_ee):
    # Gate on widget state, never on a publish. Everything this component
    # republishes here deep-equals the dict it was seeded with, and solara skips
    # the callback when the new value compares equal — so a publish-gated drain
    # waits out its whole timeout against a perfectly correct implementation.
    restored = {
        "asset_id": "projects/x/assets/aoi",
        "type": "TABLE",
        "column": "region",
        "value": "north",
    }

    @solara.component
    def _Harness():
        AssetSelectComponent(value=restored, gee_interface=_fake_gee_interface())

    root = render_and_drain(
        _Harness, lambda r: bool(getattr(find_by_label(r, "Value"), "items", None))
    )

    assert find_by_label(root, "Column").v_model == "region"
    assert find_by_label(root, "Value").v_model == "north"


def test_a_changed_filter_on_the_same_asset_reaches_the_widgets(_no_live_ee):
    """The same asset id with a new filter must still move the controls.

    Writing an unchanged id back into the reactive is a store no-op, so the
    asset-change task never re-runs and the widgets would keep the old filter.
    """
    held = solara.reactive(
        {"asset_id": "projects/x/assets/aoi", "type": "TABLE", "column": "ALL", "value": None}
    )

    @solara.component
    def _Harness():
        AssetSelectComponent(value=held, gee_interface=_fake_gee_interface())

    async def _runner():
        root, rc = reacton.render(_Harness(), handle_error=False)
        try:
            await wait_until(lambda: find_by_label(root, "Column") is not None)
            held.set({**held.value, "column": "region", "value": "north"})
            await wait_until(
                lambda: getattr(find_by_label(root, "Value"), "v_model", None) == "north"
            )
            return find_by_label(root, "Column")
        finally:
            rc.close()

    column_select = asyncio.run(_runner())

    assert column_select is not None
    assert column_select.v_model == "region"


def test_vector_selector_seeds_the_file_path_from_an_external_value():
    held = solara.reactive({"pathname": str(VECTORS), "column": "ALL", "value": None})

    @solara.component
    def _Harness():
        VectorSelectorComponent(value=held)

    _render(_Harness)

    assert held.value["pathname"] == str(VECTORS)


def test_vector_selector_keeps_a_restored_column_filter():
    import geopandas as gpd

    region = sorted(gpd.read_file(VECTORS, ignore_geometry=True)["region"].dropna().unique())[0]
    restored = {"pathname": str(VECTORS), "column": "region", "value": region}

    @solara.component
    def _Harness():
        VectorSelectorComponent(value=restored)

    root = render_and_drain(
        _Harness,
        lambda r: bool(getattr(find_by_label(r, msg("widgets.vector.value")), "items", None)),
    )

    assert find_by_label(root, msg("widgets.vector.column")).v_model == "region"
    assert find_by_label(root, msg("widgets.vector.value")).v_model == region


def test_points_selector_seeds_every_column_from_an_external_value(tmp_path):
    table = tmp_path / "plots.csv"
    table.write_text("id,lat,lon\n1,0.0,0.0\n")
    held = solara.reactive(
        {"pathname": str(table), "id_column": "id", "lat_column": "lat", "lng_column": "lon"}
    )

    @solara.component
    def _Harness():
        PointsSelectorComponent(value=held)

    root = _render(_Harness)

    assert find_by_label(root, msg("widgets.table.column.id")).v_model == "id"
    assert find_by_label(root, msg("widgets.table.column.lat")).v_model == "lat"
    assert find_by_label(root, msg("widgets.table.column.lng")).v_model == "lon"


def test_asset_user_column_change_does_not_replay_the_restored_filter(_no_live_ee):
    held = solara.reactive(
        {"asset_id": "projects/x/assets/aoi", "type": "TABLE", "column": "region", "value": "north"}
    )

    @solara.component
    def Harness():
        AssetSelectComponent(value=held, gee_interface=_fake_gee_interface())

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(lambda: bool(getattr(find_by_label(root, "Value"), "items", [])))
            find_by_label(root, "Column").v_model = "ALL"
            await wait_until(lambda: held.value["column"] == "ALL")
            find_by_label(root, "Column").v_model = "region"
            await wait_until(lambda: bool(getattr(find_by_label(root, "Value"), "items", [])))
            assert find_by_label(root, "Value").v_model is None
            assert held.value["value"] is None
        finally:
            rc.close()

    asyncio.run(run())


@pytest.mark.parametrize("kind", ["asset", "vector", "points"])
def test_external_clear_resets_selector_controls(kind, tmp_path, _no_live_ee):
    table = tmp_path / "plots.csv"
    table.write_text("id,lat,lon\n1,0,0\n")
    initial = {
        "asset": {
            "asset_id": "projects/x/assets/aoi",
            "type": "TABLE",
            "column": "ALL",
            "value": None,
        },
        "vector": {"pathname": str(VECTORS), "column": "ALL", "value": None},
        "points": {
            "pathname": str(table),
            "id_column": "id",
            "lat_column": "lat",
            "lng_column": "lon",
        },
    }[kind]
    held = solara.reactive(initial)

    @solara.component
    def Harness():
        if kind == "asset":
            AssetSelectComponent(value=held, gee_interface=_fake_gee_interface())
        elif kind == "vector":
            VectorSelectorComponent(value=held)
        else:
            PointsSelectorComponent(value=held)

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(lambda: bool(of_type(root, "Select")))
            held.set(None)
            if kind == "asset":
                assert of_type(root, "Combobox")[0].v_model in (None, "")
            else:
                assert of_type(root, "FileInput")[0].v_model == ""
                assert not of_type(root, "Select")
            assert held.value is None
        finally:
            rc.close()

    asyncio.run(run())


def test_vector_reselecting_a_file_does_not_restore_its_old_filter():
    held = solara.reactive({"pathname": str(VECTORS), "column": "region", "value": "north"})

    @solara.component
    def Harness():
        VectorSelectorComponent(value=held)

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(
                lambda: bool(getattr(find_by_label(root, msg("widgets.vector.value")), "items", []))
            )
            browser = of_type(root, "FileInput")[0]
            browser.v_model = ""
            await wait_until(lambda: held.value is None)
            browser.v_model = str(VECTORS)
            await wait_until(
                lambda: bool(
                    getattr(find_by_label(root, msg("widgets.vector.column")), "items", [])
                )
            )
            assert find_by_label(root, msg("widgets.vector.column")).v_model == "ALL"
            assert held.value == {"pathname": str(VECTORS), "column": "ALL", "value": None}
        finally:
            rc.close()

    asyncio.run(run())


def test_points_keeps_an_incomplete_draft_after_autodetecting_columns(tmp_path):
    table = tmp_path / "plots.csv"
    table.write_text("id,lat,lon\n1,0,0\n")
    held = solara.reactive(None)

    @solara.component
    def Harness():
        PointsSelectorComponent(value=held)

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            browser = of_type(root, "FileInput")[0]
            browser.v_model = str(table)
            await wait_until(lambda: held.value is not None)
            assert held.value == {
                "pathname": str(table),
                "id_column": "id",
                "lat_column": "lat",
                "lng_column": "lon",
            }
            find_by_label(root, msg("widgets.table.column.id")).v_model = None
            assert held.value is None
            assert browser.v_model == str(table)
            assert find_by_label(root, msg("widgets.table.column.lat")).v_model == "lat"
            find_by_label(root, msg("widgets.table.column.id")).v_model = "id"
            assert held.value["id_column"] == "id"
        finally:
            rc.close()

    asyncio.run(run())


def _recording_notifier(monkeypatch):
    """Capture what the asset picker would toast."""
    errors = []
    monkeypatch.setattr(
        asset_select_mod, "use_notifications", lambda: MagicMock(error=errors.append)
    )
    return errors


def test_a_wrong_asset_type_is_reported_under_the_field_only(monkeypatch, _no_live_ee):
    """Two reports of one fault read as two faults.

    A type the picker does not accept is a fault in what the user typed, so it
    belongs in the field's own error slot, where it sits next to the entry that
    caused it. A toast on top of that says the same sentence twice.
    """
    errors = _recording_notifier(monkeypatch)
    interface = _fake_gee_interface()

    async def _wrong_type(_asset_id):
        return {"type": "IMAGE_COLLECTION"}

    interface.get_asset_async = _wrong_type

    @solara.component
    def _Harness():
        AssetSelectComponent(
            types=["TABLE"],
            value={"asset_id": "projects/x/assets/aoi"},
            gee_interface=interface,
        )

    root = render_and_drain(_Harness, lambda r: bool(of_type(r, "Combobox")[0].error_messages))

    assert errors == []
    assert of_type(root, "Combobox")[0].error_messages == msg(
        "widgets.asset_select.wrong_type", asset_type="IMAGE_COLLECTION", allowed="TABLE"
    )


def test_an_unreadable_asset_is_reported_as_a_toast(monkeypatch, _no_live_ee):
    """The other half: a failure the field cannot explain still has to be seen."""
    errors = _recording_notifier(monkeypatch)
    interface = _fake_gee_interface()

    async def _denied(_asset_id):
        raise RuntimeError("permission denied")

    interface.get_asset_async = _denied

    @solara.component
    def _Harness():
        AssetSelectComponent(
            value={"asset_id": "projects/x/assets/aoi"},
            gee_interface=interface,
        )

    root = render_and_drain(_Harness, lambda _r: bool(errors))

    assert errors == [msg("widgets.asset_select.no_access")]
    assert not of_type(root, "Combobox")[0].error_messages
