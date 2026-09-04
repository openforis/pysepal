"""AdminLevelSelector keeps one code tuple, and restores from it."""

import asyncio

import solara

import pysepal.solara.components.aoi.admin as admin_mod
from pysepal.message import ms
from pysepal.solara.components.inputs.admin_selector import AdminLevelSelector

from ._harness import find_by_label

_ITEMS = {
    (0, ""): [{"text": "Algeria", "value": "101"}, {"text": "Paraguay", "value": "206"}],
    (1, "101"): [{"text": "Adrar", "value": "1001"}],
    (1, "206"): [{"text": "Amambay", "value": "2184"}],
    (2, "1001"): [{"text": "Aoulef", "value": "100001"}],
}


def _fake_items(level, parent_code=""):
    return _ITEMS.get((level, str(parent_code)), [])


def _render(component):
    async def _runner():
        return component.widget()

    return asyncio.run(_runner())


def test_restores_the_whole_cascade_from_codes(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    codes = solara.reactive(("101", "1001", "100001"))
    picked = solara.reactive(None)

    @solara.component
    def _Harness():
        AdminLevelSelector(method="ADMIN2", gee=False, value=picked, codes=codes)

    _render(_Harness)

    assert picked.value == "100001"


def test_the_dropdowns_show_every_restored_level(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    codes = solara.reactive(("101", "1001", "100001"))

    @solara.component
    def _Harness():
        AdminLevelSelector(method="ADMIN2", gee=False, codes=codes)

    root = _render(_Harness)

    assert find_by_label(root, ms.aoi_sel.adm[0]).v_model == "101"
    assert find_by_label(root, ms.aoi_sel.adm[1]).v_model == "1001"
    assert find_by_label(root, ms.aoi_sel.adm[2]).v_model == "100001"


def test_picking_a_parent_drops_its_children(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    codes = solara.reactive(("101", "1001", "100001"))

    @solara.component
    def _Harness():
        AdminLevelSelector(method="ADMIN2", gee=False, codes=codes)

    root = _render(_Harness)
    # reacton binds on_v_model as a traitlet observer, so assigning v_model is
    # exactly what a user pick does.
    find_by_label(root, ms.aoi_sel.adm[0]).v_model = "206"

    assert codes.value == ("206",)


def test_publishes_none_until_the_target_level_is_picked(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    picked = solara.reactive("stale")

    @solara.component
    def _Harness():
        AdminLevelSelector(method="ADMIN2", gee=False, value=picked, codes=("101",))

    _render(_Harness)

    assert picked.value is None


def test_admin0_publishes_the_country_code(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    picked = solara.reactive(None)

    @solara.component
    def _Harness():
        AdminLevelSelector(method="ADMIN0", gee=False, value=picked, codes=("206",))

    _render(_Harness)

    assert picked.value == "206"
