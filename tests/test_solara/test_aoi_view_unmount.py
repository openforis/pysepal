"""Unmounting AoiView must not erase an AOI the host app still owns."""

import asyncio

import reacton
import solara

from pysepal.solara.components.aoi import AoiResult
from pysepal.solara.components.aoi.aoi_view import AoiView


def test_unmount_keeps_caller_owned_value():
    held = solara.reactive(AoiResult(method="ADMIN0", name="PRY", admin="206"))
    mounted = solara.reactive(True)

    @solara.component
    def _Harness():
        if mounted.value:
            AoiView(value=held, gee=False, methods=["ADMIN0"])

    async def _runner():
        _box, rc = reacton.render(_Harness(), handle_error=False)
        mounted.set(False)
        rc.force_update()
        return rc

    rc = asyncio.run(_runner())
    rc.close()

    assert held.value is not None
    assert held.value.name == "PRY"
