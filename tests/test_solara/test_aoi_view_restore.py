"""AoiView restores its picker, and the AOI, from a persisted AoiSpec."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import reacton
import solara

import pysepal.solara.components.aoi.admin as admin_mod
import pysepal.solara.components.aoi.aoi_view as aoi_view_mod
from pysepal.message import msg
from pysepal.solara.components.aoi.aoi_spec import AoiSpec
from pysepal.solara.components.aoi.aoi_view import AoiView

from ._harness import find_by_label, of_type, render_and_drain, wait_until

DATA = Path(__file__).resolve().parents[1] / "data" / "aoi_manual" / "manual_polygons.geojson"
pytestmark = pytest.mark.usefixtures("empty_file_browser")

_ITEMS = {
    (0, ""): [{"text": "Algeria", "value": "101"}],
    (1, "101"): [{"text": "Adrar", "value": "1001"}],
}


def _fake_items(level, parent_code=""):
    return _ITEMS.get((level, str(parent_code)), [])


def _render(component):
    async def _runner():
        root, rc = reacton.render(component(), handle_error=False)
        rc.close()
        return root

    return asyncio.run(_runner())


def _method_select(root):
    return find_by_label(root, msg("aoi_sel.method"))


def test_a_spec_seeds_the_method_select(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    spec = AoiSpec(method="ADMIN1", admin_codes=("101", "1001"))

    @solara.component
    def _Harness():
        AoiView(spec=spec, gee=False, autoselect=False)

    root = _render(_Harness)

    assert _method_select(root).v_model == "ADMIN1"
    assert find_by_label(root, msg("aoi_sel.adm.1")).v_model == "1001"


def test_a_shape_spec_reaches_the_result(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    held = solara.reactive(None)
    spec = AoiSpec(method="SHAPE", pathname=str(DATA))

    @solara.component
    def _Harness():
        AoiView(value=held, spec=spec, gee=False)

    render_and_drain(_Harness, lambda *_: held.value is not None)

    assert held.value is not None
    assert held.value.method == "SHAPE"
    assert held.value.spec.pathname == str(DATA)


def test_an_admin_spec_reaches_the_result(monkeypatch):
    """The flagship case: a restored ADMIN spec must run with autoselect on.

    ``_apply_spec`` sets the leaf directly rather than waiting for the selector's
    effect, so this pins that the task sees a populated ``admin_code`` without
    depending on effect ordering.
    """
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)

    async def _fake_process_admin(method, admin_code, gee=True, gee_interface=None, admin_codes=()):
        from pysepal.solara.components.aoi.aoi_result import AoiResult

        assert admin_code == "101"
        return AoiResult(
            method=method,
            name="DZA",
            admin=admin_code,
            gee=False,
            spec=AoiSpec(method=method, admin_codes=tuple(admin_codes)),
        )

    monkeypatch.setattr(aoi_view_mod, "process_admin", _fake_process_admin)
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(value=held, spec=AoiSpec(method="ADMIN0", admin_codes=("101",)), gee=False)

    render_and_drain(_Harness, lambda *_: held.value is not None)

    assert held.value is not None
    assert held.value.spec.admin_codes == ("101",)


def test_autoselect_false_fills_the_form_but_never_starts_the_task(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    started = []

    async def _spy_process_shape(*args, **kwargs):
        started.append(kwargs)
        raise AssertionError("autoselect=False must not process the AOI")

    monkeypatch.setattr(aoi_view_mod, "process_shape", _spy_process_shape)
    held = solara.reactive(None)
    spec = AoiSpec(method="SHAPE", pathname=str(DATA))

    @solara.component
    def _Harness():
        AoiView(value=held, spec=spec, gee=False, autoselect=False)

    root = render_and_drain(_Harness, lambda *_: held.value is not None, timeout=0.5)

    assert held.value is None
    assert started == []
    assert _method_select(root).v_model == "SHAPE"


def test_a_second_spec_replaces_the_first_without_a_remount(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    spec = solara.reactive(AoiSpec(method="ADMIN1", admin_codes=("101", "1001")))

    @solara.component
    def _Harness():
        AoiView(spec=spec, gee=False, autoselect=False)

    async def _runner():
        box, rc = reacton.render(_Harness(), handle_error=False)
        spec.set(AoiSpec(method="SHAPE", pathname=str(DATA)))
        rc.force_update()
        return box, rc

    box, rc = asyncio.run(_runner())
    method_select = _method_select(box)
    rc.close()

    assert method_select.v_model == "SHAPE"


def test_clearing_retracts_the_published_spec(monkeypatch):
    """A clear must publish None, or a persisting app resurrects the cleared AOI."""
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    published = []
    # AoiView only assigns `.current` on this, so any object with that attribute
    # works as the caller's handle.
    clear_ref = SimpleNamespace(current=None)

    @solara.component
    def _Harness():
        AoiView(
            spec=AoiSpec(method="SHAPE", pathname=str(DATA)),
            on_spec=published.append,
            gee=False,
            clear_ref=clear_ref,
        )

    async def run():
        _root, rc = reacton.render(_Harness(), handle_error=False)
        try:
            await wait_until(lambda: bool(published))
            clear_ref.current()
            assert published[-1] is None
        finally:
            rc.close()

    asyncio.run(run())


def test_a_successful_selection_publishes_its_spec(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    published = []

    @solara.component
    def _Harness():
        AoiView(
            spec=AoiSpec(method="SHAPE", pathname=str(DATA)),
            on_spec=published.append,
            gee=False,
        )

    render_and_drain(_Harness, lambda *_: bool(published))

    assert published
    assert published[-1].method == "SHAPE"


def test_autoselect_false_leaves_the_map_untouched(monkeypatch):
    """The demo's toggle turns this off, so nothing may reach the map either."""
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    from pysepal import mapping as sm

    sepal_map = sm.SepalMap(gee=False)

    @solara.component
    def _Harness():
        AoiView(
            spec=AoiSpec(method="SHAPE", pathname=str(DATA)),
            map_=sepal_map,
            gee=False,
            autoselect=False,
        )

    def _has_aoi_layer(*_):
        return any(getattr(layer, "key", None) == "aoi" for layer in sepal_map.layers)

    render_and_drain(_Harness, _has_aoi_layer, timeout=0.5)

    assert not _has_aoi_layer()


def test_clearing_removes_the_aoi_layer_from_the_map(monkeypatch):
    """Clear must take the geometry off the map, not just the state.

    Vector AOIs are added with ``key="aoi"`` but keep the file stem as their
    ``name``, so matching cleanup on the name left the polygon behind.
    """
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    from pysepal import mapping as sm

    sepal_map = sm.SepalMap(gee=False)
    clear_ref = SimpleNamespace(current=None)

    @solara.component
    def _Harness():
        AoiView(
            spec=AoiSpec(method="SHAPE", pathname=str(DATA)),
            map_=sepal_map,
            gee=False,
            clear_ref=clear_ref,
        )

    def _has_aoi_layer(*_):
        return any(getattr(layer, "key", None) == "aoi" for layer in sepal_map.layers)

    async def run():
        _root, rc = reacton.render(_Harness(), handle_error=False)
        try:
            await wait_until(_has_aoi_layer)
            clear_ref.current()
            assert not _has_aoi_layer()
        finally:
            rc.close()

    asyncio.run(run())


def test_restoring_another_method_removes_the_draw_control():
    from unittest.mock import Mock

    draw = SimpleNamespace(data=[])
    draw.clear = lambda: setattr(draw, "data", [])
    map_ = SimpleNamespace(gee=False, dc=draw, controls=[], layers=[])
    map_.add_control = map_.controls.append
    map_.remove_control = map_.controls.remove
    map_.remove_layer = Mock()
    spec = solara.reactive(
        AoiSpec(method="DRAW", geo_json={"type": "FeatureCollection", "features": [{"id": "a"}]})
    )

    @solara.component
    def Harness():
        AoiView(spec=spec, gee=False, map_=map_, autoselect=False)

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            assert draw in map_.controls
            assert draw.data == [{"id": "a"}]
            spec.set(AoiSpec(method="SHAPE", pathname=str(DATA)))
            assert _method_select(root).v_model == "SHAPE"
            assert draw not in map_.controls
            assert draw.data == []
        finally:
            rc.close()

    asyncio.run(run())


def test_restoring_without_autoselect_cancels_the_previous_selection(monkeypatch):
    from pysepal.solara.components.aoi import AoiResult

    spec = solara.reactive(AoiSpec(method="SHAPE", pathname=str(DATA)))
    autoselect = solara.reactive(True)
    value = solara.reactive(None)

    @solara.component
    def Harness():
        AoiView(spec=spec, value=value, gee=False, autoselect=autoselect.value)

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()
        finished = asyncio.Event()

        async def process_shape(**kwargs):
            started.set()
            try:
                await release.wait()
                return AoiResult(
                    method="SHAPE",
                    name="old",
                    spec=AoiSpec(method="SHAPE", pathname=kwargs["pathname"]),
                )
            finally:
                finished.set()

        monkeypatch.setattr(aoi_view_mod, "process_shape", process_shape)
        _root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await asyncio.wait_for(started.wait(), 3)
            autoselect.set(False)
            replacement = AoiSpec(
                method="SHAPE", pathname=str(DATA), column="region", value="south"
            )
            spec.set(replacement)
            release.set()
            await wait_until(finished.is_set)
            assert spec.value == replacement
            assert value.value is None
        finally:
            rc.close()

    asyncio.run(run())


def test_success_callback_can_unmount_the_picker(monkeypatch):
    from pysepal.solara.components.aoi import AoiResult

    mounted = solara.reactive(True)
    specs = []
    values = []
    spec = AoiSpec(method="SHAPE", pathname=str(DATA))
    result_spec = AoiSpec(method="SHAPE", pathname=str(DATA), column="ALL")

    async def process_shape(**kwargs):
        return AoiResult(method="SHAPE", name="selected", spec=result_spec)

    monkeypatch.setattr(aoi_view_mod, "process_shape", process_shape)

    def on_value(result):
        values.append(result)
        if result is not None:
            mounted.set(False)

    @solara.component
    def Harness():
        if mounted.value:
            AoiView(spec=spec, on_value=on_value, on_spec=specs.append, gee=False)

    async def run():
        _root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(lambda: not mounted.value)
            assert values[-1].name == "selected"
            assert specs == [result_spec]
        finally:
            rc.close()

    asyncio.run(run())


def test_explicit_clear_resets_an_incomplete_points_form(tmp_path):
    table = tmp_path / "plots.csv"
    table.write_text("id,lat,lon\n1,0,0\n")
    clear_ref = SimpleNamespace(current=None)
    spec = AoiSpec(
        method="POINTS", pathname=str(table), id_column="id", lat_column="lat", lng_column="lon"
    )

    @solara.component
    def Harness():
        AoiView(spec=spec, clear_ref=clear_ref, gee=False, autoselect=False)

    async def run():
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await wait_until(
                lambda: bool(
                    getattr(find_by_label(root, msg("widgets.table.column.id")), "items", [])
                )
            )
            find_by_label(root, msg("widgets.table.column.id")).v_model = None
            clear_ref.current()
            await wait_until(lambda: of_type(root, "FileInput")[0].v_model == "")
            assert _method_select(root).v_model == "POINTS"
            assert of_type(root, "FileInput")[0].v_model == ""
        finally:
            rc.close()

    asyncio.run(run())


def test_clearing_while_processing_cancels_the_run(monkeypatch):
    """A clear must stop a running selection, not let it land on an emptied picker."""
    from pysepal.solara.components.aoi import AoiResult

    clear_ref = SimpleNamespace(current=None)
    spec = AoiSpec(method="SHAPE", pathname=str(DATA))
    value = solara.reactive(None)

    @solara.component
    def Harness():
        AoiView(spec=spec, value=value, clear_ref=clear_ref, gee=False)

    async def run():
        started = asyncio.Event()
        release = asyncio.Event()

        async def process_shape(**kwargs):
            started.set()
            await release.wait()
            return AoiResult(method="SHAPE", name="late", spec=spec)

        monkeypatch.setattr(aoi_view_mod, "process_shape", process_shape)
        root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await asyncio.wait_for(started.wait(), 3)
            clear_ref.current()
            await wait_until(lambda: of_type(root, "FileInput")[0].v_model == "")

            # Releasing a run that was not cancelled would publish "late" here.
            # Nothing arriving is the assertion, so this waits by time on purpose.
            release.set()
            await asyncio.sleep(0.1)

            assert value.value is None
            assert _method_select(root).v_model == "SHAPE"
        finally:
            rc.close()

    asyncio.run(run())


def test_a_restore_from_inside_a_run_does_not_break_that_run(monkeypatch):
    """A run renders while it is still running, so a restore can land on its stack.

    Writing a reactive from the task body renders synchronously, thus an effect
    that restores or clears executes inside the coroutine. ``task.cancel()`` raises
    there, which is why the cancel asks ``is_current()`` first.
    """
    from pysepal.solara.components.aoi import AoiResult

    spec = solara.reactive(AoiSpec(method="SHAPE", pathname=str(DATA)))
    replacement = AoiSpec(method="SHAPE", pathname=str(DATA), column="region", value="south")
    running = solara.reactive(False)
    value = solara.reactive(None)

    @solara.component
    def Harness():
        def restore_once():
            if running.value:
                spec.set(replacement)

        solara.use_effect(restore_once, [running.value])
        AoiView(spec=spec, value=value, gee=False)

    async def run():
        started = asyncio.Event()
        returned = asyncio.Event()

        async def process_shape(**kwargs):
            started.set()
            # Renders inside this coroutine, which is what puts the restore here.
            running.set(True)
            try:
                return AoiResult(method="SHAPE", name="ok", spec=spec.value)
            finally:
                returned.set()

        monkeypatch.setattr(aoi_view_mod, "process_shape", process_shape)
        _root, rc = reacton.render(Harness(), handle_error=False)
        try:
            await asyncio.wait_for(started.wait(), 3)
            await wait_until(returned.is_set)
            assert spec.value == replacement
        finally:
            rc.close()

    asyncio.run(run())
