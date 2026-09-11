"""Tests for the Solara AssetSelectComponent."""

import asyncio

import ipyvuetify as v
import solara

from pysepal.solara.components.inputs import asset_select as asset_select_mod


class _FakeGeeInterface:
    """Records how many times the component asked for the asset list."""

    def __init__(self):
        self.calls = 0

    async def get_folder_async(self):
        return "users/tester"

    async def get_assets_async(self, folder):
        self.calls += 1
        return [{"id": f"{folder}/img{self.calls}", "type": "IMAGE"}]


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


def _drive(scenario):
    """Render the component on a running loop -- use_task needs one."""

    async def main():
        gee = _FakeGeeInterface()
        box, _ = solara.render(
            asset_select_mod.AssetSelectComponent(gee_interface=gee),
            handle_error=False,
        )
        assert await _wait_for(lambda: gee.calls >= 1), "initial asset load never ran"
        combobox = _find_combobox(box)
        assert combobox is not None, "AssetSelectComponent rendered no Combobox"
        return await scenario(combobox, gee)

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
