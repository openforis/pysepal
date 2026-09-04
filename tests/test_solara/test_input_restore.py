"""The dict-valued input components honour a value set from outside."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import solara

import pysepal.solara.components.inputs.asset_select as asset_select_mod
from pysepal.message import ms
from pysepal.solara.components.inputs.asset_select import AssetSelectComponent
from pysepal.solara.components.inputs.point_selector import PointsSelectorComponent
from pysepal.solara.components.inputs.vector_selector import VectorSelectorComponent

from ._harness import find_by_label, of_type, render_and_drain

VECTORS = Path(__file__).resolve().parents[1] / "data" / "aoi_manual" / "manual_polygons.geojson"


def _render(component):
    async def _runner():
        return component.widget()

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
    monkeypatch.setattr(asset_select_mod.ee, "FeatureCollection", lambda _aid: MagicMock())


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
        root = _Harness.widget()
        # Wait for the Column select to exist — it renders only once column_items
        # has filled, i.e. once the first cascade finished. The change and the
        # wait both have to happen while the loop is still alive, so this drives
        # the whole sequence inside one asyncio.run.
        for _ in range(300):
            await asyncio.sleep(0.01)
            if find_by_label(root, "Column") is not None:
                break
        held.set({**held.value, "column": "region", "value": "north"})
        for _ in range(300):
            await asyncio.sleep(0.01)
            if getattr(find_by_label(root, "Column"), "v_model", None) == "region":
                break
        return find_by_label(root, "Column")

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
        lambda r: bool(getattr(find_by_label(r, ms.widgets.vector.value), "items", None)),
    )

    assert find_by_label(root, ms.widgets.vector.column).v_model == "region"
    assert find_by_label(root, ms.widgets.vector.value).v_model == region


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

    assert find_by_label(root, ms.widgets.table.column.id).v_model == "id"
    assert find_by_label(root, ms.widgets.table.column.lat).v_model == "lat"
    assert find_by_label(root, ms.widgets.table.column.lng).v_model == "lon"
