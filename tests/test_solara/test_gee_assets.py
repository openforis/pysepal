"""One asset list per session, shared by every asset field."""

import asyncio

import reacton
import solara

from pysepal.solara.components.inputs import (
    AssetSelectComponent,
    reload_gee_assets,
    use_gee_assets,
)

from ._harness import of_type, wait_until

# Each test builds its own fake: the cache is keyed by interface, so no test
# reads a list another test left behind.


class _FakeGee:
    """Counts listings; the asset names carry the listing number."""

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    async def get_folder_async(self):
        return "users/tester"

    async def get_assets_async(self, folder):
        self.calls += 1
        # Yield once, as a real request does, so concurrent mounts overlap.
        await asyncio.sleep(0)
        if self.fail:
            raise RuntimeError("no access")
        return [{"id": f"{folder}/img{self.calls}", "type": "IMAGE"}]


def _asset_ids(combobox):
    return [item for item in combobox.items if isinstance(item, str)]


def _session(component, scenario):
    async def run():
        root, rc = reacton.render(component(), handle_error=False)
        try:
            await scenario(root)
        finally:
            rc.close()

    asyncio.run(run())


def test_fields_mounted_together_list_the_assets_once():
    gee = _FakeGee()

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee)
        AssetSelectComponent(gee_interface=gee)

    async def scenario(root):
        boxes = of_type(root, "Combobox")
        await wait_until(lambda: all(_asset_ids(box) for box in boxes))
        assert gee.calls == 1

    _session(_Harness, scenario)


def test_a_remounted_field_reuses_the_list():
    gee = _FakeGee()
    mounted = solara.reactive(True)

    @solara.component
    def _Harness():
        if mounted.value:
            AssetSelectComponent(gee_interface=gee)

    async def scenario(root):
        await wait_until(lambda: _asset_ids(of_type(root, "Combobox")[0]))
        mounted.set(False)
        mounted.set(True)
        await wait_until(lambda: _asset_ids(of_type(root, "Combobox")[0]))
        assert gee.calls == 1
        assert _asset_ids(of_type(root, "Combobox")[0]) == ["users/tester/img1"]

    _session(_Harness, scenario)


def test_the_sync_icon_reloads_every_field():
    gee = _FakeGee()

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee)
        AssetSelectComponent(gee_interface=gee)

    async def scenario(root):
        first, second = of_type(root, "Combobox")
        await wait_until(lambda: _asset_ids(first) and _asset_ids(second))

        first.fire_event("click:prepend-inner", None)
        await wait_until(lambda: _asset_ids(second) == ["users/tester/img2"])
        assert _asset_ids(first) == ["users/tester/img2"]
        assert gee.calls == 2

    _session(_Harness, scenario)


def test_a_failed_listing_is_tried_again_on_the_next_mount():
    gee = _FakeGee(fail=True)
    mounted = solara.reactive(True)

    @solara.component
    def _Harness():
        if mounted.value:
            AssetSelectComponent(gee_interface=gee)

    async def scenario(root):
        await wait_until(lambda: gee.calls == 1 and not of_type(root, "Combobox")[0].loading)
        gee.fail = False
        mounted.set(False)
        mounted.set(True)
        await wait_until(lambda: _asset_ids(of_type(root, "Combobox")[0]))
        assert gee.calls == 2

    _session(_Harness, scenario)


def test_each_folder_has_its_own_list():
    gee = _FakeGee()

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee, folder="users/tester/a")
        AssetSelectComponent(gee_interface=gee, folder="users/tester/b")

    async def scenario(root):
        first, second = of_type(root, "Combobox")
        await wait_until(lambda: _asset_ids(first) and _asset_ids(second))
        assert _asset_ids(first)[0].startswith("users/tester/a/")
        assert _asset_ids(second)[0].startswith("users/tester/b/")
        assert gee.calls == 2

    _session(_Harness, scenario)


def test_an_app_field_shares_the_list_through_the_hook():
    gee = _FakeGee()
    seen = []

    @solara.component
    def _AppField():
        listing = use_gee_assets(gee_interface=gee)
        seen.append(listing)

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee)
        _AppField()

    async def scenario(root):
        await wait_until(lambda: seen and seen[-1].assets)
        assert seen[-1].folder == "users/tester"
        assert [asset["id"] for asset in seen[-1].assets] == ["users/tester/img1"]
        assert not seen[-1].loading
        assert gee.calls == 1

    _session(_Harness, scenario)


def test_the_hook_reports_a_failed_listing():
    gee = _FakeGee(fail=True)
    seen = []

    @solara.component
    def _AppField():
        seen.append(use_gee_assets(gee_interface=gee))

    async def scenario(root):
        await wait_until(lambda: seen and seen[-1].error is not None)
        assert "no access" in str(seen[-1].error)
        assert seen[-1].assets == ()
        assert not seen[-1].loading

    _session(_AppField, scenario)


def test_the_hook_reload_lists_again():
    gee = _FakeGee()
    seen = []

    @solara.component
    def _AppField():
        seen.append(use_gee_assets(gee_interface=gee))

    async def scenario(root):
        await wait_until(lambda: seen and seen[-1].assets)
        seen[-1].reload()
        await wait_until(lambda: seen[-1].assets[0]["id"] == "users/tester/img2")
        assert gee.calls == 2

    _session(_AppField, scenario)


def test_the_sync_icon_reloads_every_folder():
    gee = _FakeGee()

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee, folder="users/tester/a")
        AssetSelectComponent(gee_interface=gee, folder="users/tester/b")

    async def scenario(root):
        first, second = of_type(root, "Combobox")
        await wait_until(lambda: _asset_ids(first) and _asset_ids(second))
        before = _asset_ids(second)

        first.fire_event("click:prepend-inner", None)
        await wait_until(lambda: _asset_ids(second) != before)
        assert gee.calls == 4

    _session(_Harness, scenario)


def test_reload_gee_assets_refreshes_every_field():
    gee = _FakeGee()

    @solara.component
    def _Harness():
        AssetSelectComponent(gee_interface=gee)
        AssetSelectComponent(gee_interface=gee)

    async def scenario(root):
        first, second = of_type(root, "Combobox")
        await wait_until(lambda: _asset_ids(first) and _asset_ids(second))

        reload_gee_assets()
        await wait_until(lambda: _asset_ids(first) == _asset_ids(second) == ["users/tester/img2"])
        assert gee.calls == 2

    _session(_Harness, scenario)
