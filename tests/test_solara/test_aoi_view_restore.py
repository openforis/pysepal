"""AoiView restores its picker, and the AOI, from a persisted AoiSpec."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import reacton
import solara

import pysepal.solara.components.aoi.admin as admin_mod
import pysepal.solara.components.aoi.aoi_view as aoi_view_mod
from pysepal.message import ms
from pysepal.solara.components.aoi.aoi_spec import AoiSpec
from pysepal.solara.components.aoi.aoi_view import AoiView

from ._harness import find_by_label, render_and_drain

DATA = Path(__file__).resolve().parents[1] / "data" / "aoi_manual" / "manual_polygons.geojson"

_ITEMS = {
    (0, ""): [{"text": "Algeria", "value": "101"}],
    (1, "101"): [{"text": "Adrar", "value": "1001"}],
}


def _fake_items(level, parent_code=""):
    return _ITEMS.get((level, str(parent_code)), [])


def _render(component):
    async def _runner():
        return component.widget()

    return asyncio.run(_runner())


def _method_select(root):
    return find_by_label(root, ms.aoi_sel.method)


def test_a_spec_seeds_the_method_select(monkeypatch):
    monkeypatch.setattr(admin_mod, "fetch_admin_items", _fake_items)
    spec = AoiSpec(method="ADMIN1", admin_codes=("101", "1001"))

    @solara.component
    def _Harness():
        AoiView(spec=spec, gee=False, autoselect=False)

    root = _render(_Harness)

    assert _method_select(root).v_model == "ADMIN1"
    assert find_by_label(root, ms.aoi_sel.adm[1]).v_model == "1001"


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

    render_and_drain(_Harness, lambda *_: bool(published))
    clear_ref.current()

    assert published[-1] is None


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

    render_and_drain(_Harness, lambda *_: _has_aoi_layer())
    assert _has_aoi_layer(), "the AOI never reached the map"

    clear_ref.current()

    assert not _has_aoi_layer()
