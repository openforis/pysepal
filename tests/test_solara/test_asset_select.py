"""Tests for the Solara AssetSelectComponent."""

import asyncio

import ipyvuetify as v
import pytest
import solara

from pysepal._vuetify import IPYVUETIFY_V3, select_items
from pysepal.solara.components.inputs import asset_select as asset_select_mod

v3_only = pytest.mark.skipif(not IPYVUETIFY_V3, reason="Vuetify 3 combobox behaviour")
v2_only = pytest.mark.skipif(IPYVUETIFY_V3, reason="Vuetify 2 combobox behaviour")


class _FakeGeeInterface:
    """Records how many times the component listed the assets and looked one up."""

    def __init__(self, assets=None):
        self.calls = 0
        self.lookups = []
        self.assets = assets

    async def get_folder_async(self):
        return "users/tester"

    async def get_assets_async(self, folder):
        self.calls += 1
        if self.assets is not None:
            return self.assets
        return [{"id": f"{folder}/img{self.calls}", "type": "IMAGE"}]

    async def get_asset_async(self, asset_id):
        self.lookups.append(asset_id)
        return {"type": "IMAGE"}


def _find_combobox(widget):
    if isinstance(widget, v.Combobox):
        return widget
    for child in getattr(widget, "children", []):
        found = _find_combobox(child)
        if found is not None:
            return found
    return None


async def _wait_for(predicate, timeout=2.0):
    """Give the component's use_task a chance to run on the live loop."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.01)
    return True


def _drive(scenario, assets=None, value=None):
    """Render the component on a running loop -- use_task needs one."""

    async def main():
        gee = _FakeGeeInterface(assets)
        box, rc = solara.render(
            asset_select_mod.AssetSelectComponent(gee_interface=gee, value=value),
            handle_error=False,
        )
        try:
            assert await _wait_for(lambda: gee.calls >= 1), "initial asset load never ran"
            combobox = _find_combobox(box)
            assert combobox is not None, "AssetSelectComponent rendered no Combobox"
            return await scenario(combobox, gee)
        finally:
            rc.close()

    return asyncio.run(main())


def test_sync_icon_is_rendered_inside_the_field():
    async def scenario(combobox, gee):
        assert combobox.prepend_inner_icon == "mdi-sync"

    _drive(scenario)


def test_sync_icon_has_a_click_listener():
    """Vuetify only binds a click handler to an icon that carries a listener."""

    async def scenario(combobox, gee):
        assert "click:prepend-inner" in combobox._events

    _drive(scenario)


def test_clicking_the_sync_icon_reloads_the_asset_list():
    async def scenario(combobox, gee):
        before = gee.calls
        combobox.fire_event("click:prepend-inner", None)
        assert await _wait_for(lambda: gee.calls > before), "sync icon did not reload assets"

    _drive(scenario)


_LISTED = [
    {"id": "users/tester/zones", "type": "TABLE"},
    {"id": "users/tester/mosaic", "type": "IMAGE"},
]


def test_asset_items_reach_the_widget_in_the_shape_of_the_major():
    written = [
        {"divider": True},
        {"header": "Raster"},
        "users/tester/mosaic",
        {"divider": True},
        {"header": "Table"},
        "users/tester/zones",
    ]

    async def scenario(combobox, gee):
        assert await _wait_for(lambda: len(combobox.items) > 1)
        assert combobox.items == select_items(written)
        if IPYVUETIFY_V3:
            kinds = [item.get("type") for item in combobox.items if isinstance(item, dict)]
            assert kinds == ["divider", "subheader", "divider", "subheader"]

    _drive(scenario, assets=_LISTED)


def test_an_empty_folder_shows_a_disabled_item():
    async def scenario(combobox, gee):
        assert await _wait_for(lambda: bool(combobox.items))
        (item,) = combobox.items
        if IPYVUETIFY_V3:
            assert item["props"] == {"disabled": True}
            assert "title" in item
        else:
            assert item["disabled"] is True
            assert "text" in item

    _drive(scenario, assets=[])


def test_the_placeholder_shows_while_the_field_is_empty():
    """Vuetify 2 shows a placeholder unfocused; Vuetify 3 only when told to."""

    async def scenario(combobox, gee):
        if IPYVUETIFY_V3:
            assert combobox.persistent_placeholder is True
        assert combobox.placeholder

    _drive(scenario)


@v2_only
def test_vuetify_2_looks_up_what_the_combobox_commits():
    """A Vuetify 2 combobox moves v_model only on blur, Enter or a pick."""

    async def scenario(combobox, gee):
        combobox.v_model = "users/tester/typed"
        assert await _wait_for(lambda: gee.lookups == ["users/tester/typed"])

    _drive(scenario, assets=_LISTED)


@v3_only
def test_typing_does_not_look_up_every_keystroke():
    """A Vuetify 3 combobox moves v_model on every keystroke."""

    async def scenario(combobox, gee):
        for text in ("u", "us", "users/x"):
            combobox.v_model = text
        await asyncio.sleep(0.1)
        assert gee.lookups == []

    _drive(scenario, assets=_LISTED)


@v3_only
def test_enter_commits_the_typed_id():
    async def scenario(combobox, gee):
        combobox.v_model = "users/tester/typed"
        combobox.fire_event("keydown.enter", {})
        assert await _wait_for(lambda: gee.lookups == ["users/tester/typed"])

    _drive(scenario, assets=_LISTED)


@v3_only
def test_blur_commits_the_typed_id_once():
    async def scenario(combobox, gee):
        combobox.v_model = "users/tester/typed"
        combobox.fire_event("update:focused", True)
        await asyncio.sleep(0.05)
        assert gee.lookups == []

        combobox.fire_event("update:focused", False)
        assert await _wait_for(lambda: gee.lookups == ["users/tester/typed"])

        # Leaving the field again with the same text is not a new selection.
        combobox.fire_event("update:focused", False)
        combobox.fire_event("keydown.enter", {})
        await asyncio.sleep(0.05)
        assert gee.lookups == ["users/tester/typed"]

    _drive(scenario, assets=_LISTED)


@v3_only
def test_picking_a_listed_asset_commits_at_once():
    async def scenario(combobox, gee):
        combobox.v_model = "users/tester/zones"
        assert await _wait_for(lambda: gee.lookups == ["users/tester/zones"])

    _drive(scenario, assets=_LISTED)


@v3_only
def test_clearing_the_field_clears_the_selection_at_once():
    held = solara.reactive(None)

    async def scenario(combobox, gee):
        combobox.v_model = "users/tester/mosaic"
        assert await _wait_for(lambda: held.value is not None)

        combobox.v_model = None

        assert await _wait_for(lambda: held.value is None)
        assert gee.lookups == ["users/tester/mosaic"]

    _drive(scenario, assets=_LISTED, value=held)
