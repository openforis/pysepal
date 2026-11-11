"""AoiView's select button, country list and success feedback."""

import asyncio
from unittest.mock import MagicMock

import pytest
import reacton
import solara

import pysepal.solara.components.aoi.admin as admin_mod
import pysepal.solara.components.aoi.aoi_view as aoi_view_mod
from pysepal import mapping as sm
from pysepal.message import msg
from pysepal.solara.components.aoi.aoi_result import AoiResult
from pysepal.solara.components.aoi.aoi_spec import AoiSpec
from pysepal.solara.components.aoi.aoi_view import AoiView

from ._harness import find_by_label, of_type, render_and_drain, wait_until

pytestmark = pytest.mark.usefixtures("empty_file_browser")

_ITEMS = {
    (0, ""): [{"title": "Algeria", "value": "101"}, {"title": "Paraguay", "value": "206"}],
    (1, "101"): [{"title": "Adrar", "value": "1001"}],
}

_SQUARE = {
    "type": "Feature",
    "properties": {},
    "geometry": {
        "type": "Polygon",
        "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
    },
}


@pytest.fixture(autouse=True)
def _fake_admin_items(monkeypatch):
    monkeypatch.setattr(
        admin_mod,
        "fetch_admin_items",
        lambda level, parent_code="": _ITEMS.get((level, parent_code), []),
    )


@pytest.fixture
def notifier(monkeypatch):
    fake = MagicMock()
    monkeypatch.setattr(aoi_view_mod, "use_notifications", lambda **_: fake)
    return fake


@pytest.fixture
def fake_process_admin(monkeypatch):
    async def _process_admin(method, admin_code, gee=True, gee_interface=None, admin_codes=()):
        return AoiResult(
            method=method,
            name="DZA",
            admin=admin_code,
            gee=False,
            spec=AoiSpec(method=method, admin_codes=tuple(admin_codes)),
        )

    monkeypatch.setattr(aoi_view_mod, "process_admin", _process_admin)


def _select_button(root):
    label = msg("aoi_sel.btn")
    return next((btn for btn in of_type(root, "Btn") if label in (btn.children or [])), None)


def _session(component, scenario):
    """Keep the render open on a live loop while ``scenario(root)`` drives it."""

    async def run():
        root, rc = reacton.render(component(), handle_error=False)
        try:
            await scenario(root)
        finally:
            rc.close()

    asyncio.run(run())


def _pick(root, label, value):
    # reacton binds on_v_model as a traitlet observer, so this is a user pick.
    find_by_label(root, label).v_model = value


def test_the_select_button_shows_before_a_method_is_picked():
    @solara.component
    def _Harness():
        AoiView(gee=False)

    async def scenario(root):
        button = _select_button(root)
        assert button is not None
        assert button.disabled

    _session(_Harness, scenario)


def test_the_select_button_waits_for_the_last_admin_level():
    @solara.component
    def _Harness():
        AoiView(gee=False)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "ADMIN1")
        _pick(root, msg("aoi_sel.adm.0"), "101")
        assert _select_button(root).disabled

        _pick(root, msg("aoi_sel.adm.1"), "1001")
        assert not _select_button(root).disabled

    _session(_Harness, scenario)


def test_the_select_button_waits_for_a_drawing():
    sepal_map = sm.SepalMap(gee=False)

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        assert _select_button(root).disabled

        sepal_map.dc.data = [_SQUARE]
        assert not _select_button(root).disabled

    _session(_Harness, scenario)


def test_countries_limits_the_country_list():
    @solara.component
    def _Harness():
        AoiView(gee=False, countries=["206"])

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "ADMIN0")
        country = find_by_label(root, msg("aoi_sel.adm.0"))
        await wait_until(lambda: bool(country.items))
        assert [item["value"] for item in country.items] == ["206"]

    _session(_Harness, scenario)


def test_a_spec_outside_the_countries_is_refused(notifier):
    spec = AoiSpec(method="ADMIN0", admin_codes=("101",))

    @solara.component
    def _Harness():
        AoiView(gee=False, countries=["206"], spec=spec, autoselect=False)

    async def scenario(root):
        assert not find_by_label(root, msg("aoi_sel.method")).v_model
        notifier.warning.assert_called_once()

    _session(_Harness, scenario)


def test_the_success_toast_is_sent_by_default(notifier, fake_process_admin):
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(value=held, spec=AoiSpec(method="ADMIN0", admin_codes=("101",)), gee=False)

    render_and_drain(_Harness, lambda *_: held.value is not None)

    assert held.value is not None
    notifier.success.assert_called_once()


def test_notify_success_false_skips_the_toast(notifier, fake_process_admin):
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(
            value=held,
            spec=AoiSpec(method="ADMIN0", admin_codes=("101",)),
            gee=False,
            notify_success=False,
        )

    render_and_drain(_Harness, lambda *_: held.value is not None)

    assert held.value is not None
    notifier.success.assert_not_called()


def test_notify_success_false_skips_the_inline_message(fake_process_admin):
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(
            value=held,
            spec=AoiSpec(method="ADMIN0", admin_codes=("101",)),
            gee=False,
            notify_success=False,
        )

    root = render_and_drain(_Harness, lambda *_: held.value is not None)

    assert held.value is not None
    assert not of_type(root, "Alert")


def test_the_method_list_reaches_the_widget_with_subheaders():
    @solara.component
    def _Harness():
        AoiView(gee=False)

    async def scenario(root):
        method = find_by_label(root, msg("aoi_sel.method"))
        headers = [item for item in method.items if not item.get("value")]
        choices = [item for item in method.items if item.get("value")]

        assert [item["value"] for item in choices][:3] == ["ADMIN0", "ADMIN1", "ADMIN2"]
        assert {item["type"] for item in headers} == {"subheader"}
        assert all(item["title"] for item in headers + choices)
        assert method.density == "compact"
        assert method.variant == "underlined"

    _session(_Harness, scenario)


def test_no_method_leaves_the_select_empty():
    """A select counts "" as a pick and floats the label over an empty field."""

    @solara.component
    def _Harness():
        AoiView(gee=False)

    async def scenario(root):
        method = find_by_label(root, msg("aoi_sel.method"))
        assert method.v_model is None

        _pick(root, msg("aoi_sel.method"), "ADMIN0")
        assert find_by_label(root, msg("aoi_sel.adm.0")) is not None

    _session(_Harness, scenario)


def test_the_draw_name_field_is_outlined_and_dense():
    sepal_map = sm.SepalMap(gee=False)

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        name = find_by_label(root, msg("aoi_sel.aoi_name"))
        assert (name.variant, name.density) == ("outlined", "compact")

    _session(_Harness, scenario)
