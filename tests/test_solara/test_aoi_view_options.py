"""AoiView's select button, country list and success feedback."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
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
from tests.test_solara.test_notifications.test_notification_ui_template import (
    needs_node,
    run_vue_script,
)

from ._draw_helpers import drawn_feature, mount, report
from ._harness import find_by_label, of_type, render_and_drain, wait_until, walk

pytestmark = pytest.mark.usefixtures("empty_file_browser")

_ITEMS = {
    (0, ""): [{"title": "Algeria", "value": "101"}, {"title": "Paraguay", "value": "206"}],
    (1, "101"): [{"title": "Adrar", "value": "1001"}],
}


def _draw_map() -> sm.SepalMap:
    sepal_map = sm.SepalMap(gee=False)
    mount(sepal_map)
    return sepal_map


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


def test_a_map_without_drawing_tools_offers_no_draw():
    offered = aoi_view_mod.resolve_methods("ALL", gee=False, map_=SimpleNamespace(draw=None))
    assert "DRAW" not in offered
    assert "DRAW" not in aoi_view_mod.resolve_methods("ALL", gee=False, map_=None)


def test_a_sepal_map_offers_draw():
    offered = aoi_view_mod.resolve_methods("ALL", gee=False, map_=_draw_map())
    assert "DRAW" in offered


def test_the_select_button_waits_for_a_drawing():
    sepal_map = _draw_map()

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        assert _select_button(root).disabled

        report(sepal_map)
        assert not _select_button(root).disabled

    _session(_Harness, scenario)


def test_selecting_draw_clears_and_enables_the_tools_and_leaving_disables_them():
    sepal_map = _draw_map()
    sepal_map.draw.set([drawn_feature()])

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        assert sepal_map.draw.modes == ("polygon", "rectangle", "circle", "select")
        assert sepal_map.draw.features["features"] == []

        _pick(root, msg("aoi_sel.method"), "ADMIN0")
        assert sepal_map.draw.modes == ()

    _session(_Harness, scenario)


def test_clearing_with_draw_selected_keeps_the_tools_for_a_new_drawing():
    sepal_map = _draw_map()
    clear_ref = SimpleNamespace(current=None)

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map, clear_ref=clear_ref)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        report(sepal_map)
        assert not _select_button(root).disabled

        clear_ref.current()
        assert sepal_map.draw.modes == ("polygon", "rectangle", "circle", "select")
        assert sepal_map.draw.features["features"] == []
        assert _select_button(root).disabled

        report(sepal_map)
        assert not _select_button(root).disabled

    _session(_Harness, scenario)


def test_a_drawing_submits_without_the_properties_terra_draw_adds():
    sepal_map = _draw_map()
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map, value=held)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        report(sepal_map)
        _press_enter(root)
        await wait_until(lambda: held.value is not None)

        features = held.value.spec.geo_json["features"]
        assert [f["properties"] for f in features] == [{"name": "kept"}]
        assert list(held.value.gdf.columns) == ["geometry", "name"]

    _session(_Harness, scenario)


def test_unmounting_an_admin_only_view_leaves_the_apps_own_drawing():
    sepal_map = _draw_map()
    sepal_map.draw.set([drawn_feature()])
    sepal_map.draw.enable(("point",))

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map, methods="ADMIN")

    async def run():
        root, rc = reacton.render(_Harness(), handle_error=False)
        _pick(root, msg("aoi_sel.method"), "ADMIN0")
        rc.close()

    asyncio.run(run())

    assert sepal_map.draw.modes == ("point", "select")
    assert len(sepal_map.draw.features["features"]) == 1


def test_swapping_the_map_moves_the_tools_and_the_external_clear():
    map_a, map_b = _draw_map(), _draw_map()
    current = solara.reactive(map_a)
    clear_ref = SimpleNamespace(current=None)

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=current.value, clear_ref=clear_ref)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        assert map_a.draw.modes and not map_b.draw.modes

        current.set(map_b)
        assert map_b.draw.modes == ("polygon", "rectangle", "circle", "select")
        assert map_a.draw.modes == ()

        report(map_b)
        assert map_b.draw.features["features"]
        clear_ref.current()
        assert map_b.draw.features["features"] == []
        assert map_b.draw.modes

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
    sepal_map = _draw_map()

    @solara.component
    def _Harness():
        AoiView(gee=False, map_=sepal_map)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "DRAW")
        name = find_by_label(root, msg("aoi_sel.aoi_name"))
        assert (name.variant, name.density) == ("outlined", "compact")

    _session(_Harness, scenario)


def _enter_bridge(root):
    return next(widget for widget in walk(root) if hasattr(widget, "vue_submit"))


def _press_enter(root):
    """Call the handler the page calls when the user presses Enter in a field."""
    _enter_bridge(root).vue_submit(None)


def test_the_enter_bridge_sits_in_the_form_it_watches():
    @solara.component
    def _Harness():
        AoiView(gee=False)

    async def scenario(root):
        bridge = _enter_bridge(root)
        form = next(w for w in walk(root) if bridge in (getattr(w, "children", None) or ()))
        assert bridge.scope in form.class_.split()

    _session(_Harness, scenario)


def test_enter_selects_a_complete_form(fake_process_admin):
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(value=held, gee=False)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "ADMIN0")
        _pick(root, msg("aoi_sel.adm.0"), "101")

        _press_enter(root)

        await wait_until(lambda: held.value is not None)
        assert held.value.admin == "101"

    _session(_Harness, scenario)


def test_enter_waits_for_a_complete_form(fake_process_admin):
    held = solara.reactive(None)

    @solara.component
    def _Harness():
        AoiView(value=held, gee=False)

    async def scenario(root):
        _pick(root, msg("aoi_sel.method"), "ADMIN1")
        _pick(root, msg("aoi_sel.adm.0"), "101")

        _press_enter(root)
        await asyncio.sleep(0.2)

        assert held.value is None

    _session(_Harness, scenario)


_ENTER_TEMPLATE = Path(aoi_view_mod.__file__).with_name("SubmitOnEnter.vue")


@needs_node
@pytest.mark.parametrize(
    ("classes", "submits", "blocks"),
    [
        (["v-text-field"], True, False),
        (["v-autocomplete"], True, True),
        (["v-combobox"], True, False),
        (["v-select", "v-select--active-menu"], False, False),
        (["v-autocomplete", "v-autocomplete--active-menu"], False, False),
        (["v-combobox", "v-combobox--active-menu"], False, False),
    ],
)
def test_enter_in_a_field_follows_its_vuetify_3_menu(classes, submits, blocks):
    """An open list keeps Enter to pick an item; a closed autocomplete must not reopen."""
    outcome = run_vue_script(
        _ENTER_TEMPLATE,
        f"""
        global.HTMLInputElement = class {{}};
        global.setTimeout = (fn) => fn();
        const classes = new Set({json.dumps(["v-input", *classes])});
        const field = {{ classList: {{ contains: (name) => classes.has(name) }} }};
        const form = {{ contains: () => true }};
        const input = Object.assign(new HTMLInputElement(), {{
          type: "text",
          readOnly: false,
          closest: (selector) => (selector === ".v-input" ? field : form),
        }});
        let submits = false;
        let blocks = false;
        const vm = makeVm({{ scope: "sepal-aoi-view", $el: {{}}, submit: () => (submits = true) }});
        vm.handleKeydown({{
          key: "Enter",
          target: input,
          preventDefault: () => (blocks = true),
          stopPropagation: () => {{}},
        }});
        return {{ submits, blocks }};
        """,
    )
    assert outcome == {"submits": submits, "blocks": blocks}
