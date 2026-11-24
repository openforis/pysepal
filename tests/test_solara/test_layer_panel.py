"""Tests for the LayerPanel, its rows and the basemap picker."""

import asyncio
import io
import shutil
import threading
import zipfile
from pathlib import Path

import pytest
import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.mapping import SepalMap
from pysepal.solara.components.layer_panel import LayerPanel, download, panel, row
from pysepal.solara.components.layer_panel.download import download_payload
from tests.test_solara._harness import wait_until, walk
from tests.test_solara._layer_panel_helpers import (
    HEADER_ROLES,
    all_text,
    all_widgets,
    button_icon,
    click,
    export_button,
    export_buttons,
    file_downloads,
    find_by_role,
    find_visibility_toggle,
    header_roles,
    of_kind,
    open_settings,
    role_widgets,
    row_ids,
    shown_rows,
    spinner_count,
)


def test_rows_follow_store_order(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert row_ids(box) == [raster_spec_b.id, raster_spec.id]


def test_toggle_hides_layer(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    find_visibility_toggle(box, raster_spec.id).fire_event("click", {})
    assert store.view(raster_spec.id).visible is False


def test_row_follows_changes_made_outside_it(raster_spec):
    """The engine sets the status, other components the visibility: the row shows both."""
    store = LayerStore()
    store.add(raster_spec)
    store.set_status(raster_spec.id, "pending")
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert spinner_count(box) == 1

    store.set_status(raster_spec.id, "ready")
    store.set_visible(raster_spec.id, False)

    assert spinner_count(box) == 0
    assert button_icon(find_visibility_toggle(box, raster_spec.id)) == "mdi-eye-off"


def test_row_shows_a_change_made_before_it_subscribed(raster_spec):
    """A layer can finish preparing between the panel's render and its subscription."""
    store = LayerStore()
    store.add(raster_spec)
    store.set_status(raster_spec.id, "pending")

    @solara.component
    def Ready():
        solara.use_effect(lambda: store.set_status(raster_spec.id, "ready"), [])
        return solara.Text("")

    @solara.component
    def Page():
        # Effects run in tree order, so Ready's write lands before the panel subscribes.
        return solara.Column(children=[Ready(), LayerPanel(store=store)])

    box, _ = solara.render(Page(), handle_error=False)

    assert spinner_count(box) == 0


def test_error_row_shows_message(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.set_status(raster_spec.id, "error", error="boom")
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert "boom" in all_text(box)


def test_empty_store_shows_empty_text():
    box, _ = solara.render(LayerPanel(store=LayerStore()), handle_error=False)
    assert "No layers" in all_text(box)


def test_export_only_for_gee_with_callback(raster_spec, gee_spec):
    exported, store = [], LayerStore()
    store.add(raster_spec)
    store.add(gee_spec)
    box, _ = solara.render(LayerPanel(store=store, on_export=exported.append), handle_error=False)
    assert export_buttons(box) == [gee_spec.id]
    click(export_button(box, gee_spec.id))
    assert exported == [store.get(gee_spec.id)]


def test_shapefile_download_zips_only_sidecars(fake_vector, tmp_path):
    for f in fake_vector.parent.glob(f"{fake_vector.stem}.*"):
        shutil.copy(f, tmp_path)
    (tmp_path / f"{fake_vector.stem}.csv").write_text("unrelated")
    data, name = download_payload(LayerSpec.from_vector(tmp_path / fake_vector.name))
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert name.endswith(".zip") and {".shp", ".shx", ".dbf"} <= {Path(n).suffix for n in names}
    assert not any(n.endswith(".csv") for n in names)


def test_vuetify_3_sizes(raster_spec):
    m = SepalMap(gee=False)
    m.layer_store.add(raster_spec)
    m.layer_store.set_status(raster_spec.id, "error", error="boom")
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    icons = of_kind(box, "Icon")
    assert len(icons) == 5 and {icon.size for icon in icons} == {row.ICON_SIZE}
    buttons = [w for role in HEADER_ROLES for w in role_widgets(box, role)]
    assert buttons and {(b.size, b.density) for b in buttons} == {("small", "comfortable")}


def _slots(row_widget):
    return [w.attributes["data-slot"] for w in row_widget.children]


def _rows(box):
    return [w for w in walk(box) if "pysepal-layer-row__header" in (getattr(w, "class_", "") or "")]


def test_every_row_has_the_same_fixed_slots(raster_spec, raster_spec_b):
    m, box = _compare_panel(raster_spec, raster_spec_b)
    m.compare = True
    rows = _rows(box)
    assert len(rows) == 2
    for widget in rows:
        assert _slots(widget) == ["visibility", "name", "zoom", "side", "settings", "remove"]
        # one fixed column per action, the name takes the rest
        template = f"{row.SLOT_WIDTH} minmax(0, 1fr) repeat(4, {row.SLOT_WIDTH})"
        assert f"grid-template-columns:{template};" in widget.style_

    m.compare = False
    assert all("repeat(3," in widget.style_ for widget in _rows(box))


def test_an_empty_slot_keeps_its_column():
    box, _ = solara.render(row._slot("zoom"), handle_error=False)
    slot = next(w for w in walk(box) if "__slot--zoom" in (getattr(w, "class_", "") or ""))
    assert slot.children == [] and slot.attributes == {"data-slot": "zoom"}


def test_every_row_button_has_an_accessible_name(raster_spec, raster_spec_b):
    m, box = _compare_panel(raster_spec, raster_spec_b)
    m.compare = True
    for role in HEADER_ROLES:
        for widget in role_widgets(box, role):
            assert widget.attributes.get("aria-label"), role


def test_visibility_button_says_what_a_click_does(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert find_visibility_toggle(box, raster_spec.id).attributes["aria-label"] == "Hide layer"
    click(find_visibility_toggle(box, raster_spec.id))
    assert find_visibility_toggle(box, raster_spec.id).attributes["aria-label"] == "Show layer"


def test_the_handles_are_labelled(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    sortable = next(w for w in walk(box) if hasattr(w, "vue_move"))
    assert "Alt+Up" in sortable.handle_label


def test_the_panel_lists_only_layers_whatever_the_basemaps(raster_spec):
    m = SepalMap(["SEPAL_LIGHT", "OpenStreetMap"], gee=False)
    m.layer_store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    assert of_kind(box, "Select") == []


def move(box, layer_id: str, to: int) -> None:
    """Drop a row at index ``to``, as the sortable list reports it."""
    next(w for w in walk(box) if hasattr(w, "vue_move")).vue_move({"id": layer_id, "to": to})


def _tiles(layer_id: str, zone: str = "data") -> LayerSpec:
    url = f"https://t.test/{layer_id}/{{z}}/{{x}}/{{y}}.png"
    return LayerSpec.from_tiles(url, name=layer_id, id=layer_id, zone=zone)


def test_overlay_layers_are_not_listed():
    store = LayerStore()
    store.add(_tiles("a"))
    store.add(_tiles("o", zone="overlay"))
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert row_ids(box) == ["a"]


def test_a_move_skips_the_overlay_ids():
    store = LayerStore()
    for layer_id, zone in [("b", "data"), ("a", "data"), ("o", "overlay")]:
        store.add(_tiles(layer_id, zone))
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert row_ids(box) == ["a", "b"] and store.ids == ["o", "a", "b"]

    move(box, "b", 0)
    assert store.ids == ["o", "b", "a"] and row_ids(box) == ["b", "a"]

    move(box, "b", 1)
    assert store.ids == ["o", "a", "b"] and row_ids(box) == ["a", "b"]


def test_row_remove_button_drops_the_row(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    box, rc = solara.render(LayerPanel(store=store), handle_error=False)
    click(find_by_role(box, "remove", raster_spec.id))
    assert store.ids == [raster_spec_b.id]
    assert shown_rows(box) == [raster_spec_b.id]
    rc.close()


def test_remove_all_from_a_sibling_button_keeps_the_app(raster_spec, raster_spec_b):
    m = SepalMap(gee=False)
    m.layer_store.add(raster_spec)
    m.layer_store.add(raster_spec_b)

    @solara.component
    def App():
        return solara.Column(
            children=[
                solara.Button("all", on_click=m.remove_all, attributes={"data-role": "all"}),
                LayerPanel(store=m.layer_store, map_=m),
            ]
        )

    box, rc = solara.render(App(), handle_error=False)
    click(role_widgets(box, "all")[0])
    assert m.layer_store.ids == []
    assert shown_rows(box) == [] and "No layers" in all_text(box)
    assert role_widgets(box, "all")  # the rest of the app is still rendered
    rc.close()


def test_removal_from_another_thread(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    box, rc = solara.render(LayerPanel(store=store), handle_error=False)
    thread = threading.Thread(target=lambda: store.remove(raster_spec.id))
    thread.start()
    thread.join()
    assert shown_rows(box) == [raster_spec_b.id]
    rc.close()


def test_a_layer_added_from_a_pool_worker_gets_its_row_in_the_kernel(
    kernel_contexts, kernel_comms, raster_spec, raster_spec_b
):
    """A pool worker has no kernel context: a row built there would never reach the browser."""
    context = kernel_contexts()
    store = LayerStore()
    store.add(raster_spec)
    store.set_status(raster_spec.id, "ready")

    async def page():
        box, rc = solara.render(LayerPanel(store=store), handle_error=False)
        await asyncio.to_thread(store.add, raster_spec_b)  # pending: its row shows a spinner
        await wait_until(lambda: raster_spec_b.id in shown_rows(box))
        assert find_visibility_toggle(box, raster_spec_b.id).comm.kernel is context.kernel
        assert spinner_count(box) == 1
        orphans = [
            w for w in all_widgets(box) if w.comm is None or w.comm.kernel is not context.kernel
        ]
        assert orphans == []
        rc.close()

    with context:
        asyncio.run(page())


def test_remove_is_always_on_the_row(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert role_widgets(box, "remove")
    open_settings(box, raster_spec.id)
    open_settings(box, raster_spec.id)
    assert role_widgets(box, "remove")


def test_visibility_toggle_with_settings_open(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, raster_spec.id)
    click(find_visibility_toggle(box, raster_spec.id))
    assert store.view(raster_spec.id).visible is False
    assert button_icon(find_visibility_toggle(box, raster_spec.id)) == "mdi-eye-off"


def test_opacity_slider_sets_view_opacity(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, raster_spec.id)
    find_by_role(box, "opacity", raster_spec.id).v_model = 0.4
    assert store.view(raster_spec.id).opacity == 0.4


def test_pmtiles_row_has_opacity(pmtiles_spec):
    store = LayerStore()
    store.add(pmtiles_spec)
    store.set_status(pmtiles_spec.id, "ready", kind="pmtiles")
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, pmtiles_spec.id)
    find_by_role(box, "opacity", pmtiles_spec.id).v_model = 0.3
    assert store.view(pmtiles_spec.id).opacity == 0.3


def test_row_has_no_legend(byte):
    store = LayerStore()
    spec = LayerSpec.from_raster(byte, vmin=0, vmax=255)
    store.add(spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, spec.id)
    assert not [w for w in of_kind(box, "LegendComponent")]
    assert "Legend" not in all_text(box)


def test_download_only_for_file_sources(raster_spec, gee_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.add(gee_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, raster_spec.id)
    assert len(file_downloads(box)) == 1
    find_by_role(box, "settings-menu", raster_spec.id).v_model = False
    open_settings(box, gee_spec.id)
    assert role_widgets(box, "remove") and not file_downloads(box)


def _opened(spec):
    store = LayerStore()
    store.add(spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, spec.id)
    return box


def test_download_disabled_above_the_size_limit(raster_spec, monkeypatch):
    monkeypatch.setattr(download, "DOWNLOAD_MAX_BYTES", 10)
    box = _opened(raster_spec)
    assert find_by_role(box, "download", raster_spec.id).disabled is True
    # a click anywhere in a FileDownload, disabled button included, would read the file
    assert not file_downloads(box)
    tip = find_by_role(box, "download-tip", raster_spec.id)
    assert tip.disabled is False and "SEPAL file browser" in all_text(tip)


def test_download_enabled_below_the_size_limit(raster_spec):
    box = _opened(raster_spec)
    tip = find_by_role(box, "download-tip", raster_spec.id)
    assert tip.disabled is True
    assert len(file_downloads(tip)) == 1 and not role_widgets(box, "download")


def test_missing_file_is_not_downloadable(tmp_path, byte):
    path = tmp_path / "r.tif"
    shutil.copy(byte, path)
    spec = LayerSpec.from_raster(path)
    path.unlink()
    box = _opened(spec)
    assert role_widgets(box, "remove") and not role_widgets(box, "download-tip")


def test_row_is_one_line_in_order(raster_spec):
    m = SepalMap(gee=False)
    m.layer_store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    assert header_roles(box) == ["visibility", "zoom", "settings", "remove"]


def test_no_zoom_button_without_a_map(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert header_roles(box) == ["visibility", "settings", "remove"]


def _compare_panel(raster_spec, raster_spec_b):
    m = SepalMap(gee=False)
    m.layer_store.add(raster_spec)
    m.layer_store.add(raster_spec_b)
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    return m, box


def test_no_side_button_while_compare_is_off(raster_spec):
    m = SepalMap(gee=False)
    m.layer_store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    assert role_widgets(box, "side") == []


def test_side_buttons_follow_compare(raster_spec, raster_spec_b):
    m, box = _compare_panel(raster_spec, raster_spec_b)

    m.compare = True
    assert len(role_widgets(box, "side")) == 2
    assert header_roles(box)[:5] == ["visibility", "zoom", "side", "settings", "remove"]

    m.compare = False
    assert role_widgets(box, "side") == []


def test_a_publish_that_keeps_compare_does_not_render_the_panel(
    raster_spec, raster_spec_b, monkeypatch
):
    renders = []
    data_ids = panel._data_ids
    monkeypatch.setattr(panel, "_data_ids", lambda store: renders.append(1) or data_ids(store))
    m, box = _compare_panel(raster_spec, raster_spec_b)
    m.compare = True
    count = len(renders)
    m.layer_engine.flush()
    m.layer_engine.flush()
    assert len(renders) == count
    m.compare = False
    assert len(renders) > count
    assert role_widgets(box, "side") == []


def test_side_button_cycles_the_layer_side(raster_spec, raster_spec_b):
    m, box = _compare_panel(raster_spec, raster_spec_b)
    m.compare = True
    layer_id = raster_spec.id

    seen = []
    for _ in range(3):
        button = find_by_role(box, "side", layer_id)
        assert button.attributes["data-side"] == m.layer_store.view(layer_id).side
        click(button)
        seen.append(m.layer_store.view(layer_id).side)
    assert seen == ["right", "left", "both"]
    assert m.layer_store.view(raster_spec_b.id).side == "both"


def test_side_button_shows_the_current_side(raster_spec, raster_spec_b):
    m, box = _compare_panel(raster_spec, raster_spec_b)
    m.compare = True
    m.layer_store.set_side(raster_spec.id, "left")

    button = find_by_role(box, "side", raster_spec.id)
    assert button.attributes["data-side"] == "left"
    assert button.attributes["title"] == "Left side only"
    assert button_icon(button) == "mdi-format-horizontal-align-left"


def test_settings_menu_holds_opacity_restyle_download(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    assert not role_widgets(box, "opacity")
    open_settings(box, raster_spec.id)
    assert role_widgets(box, "opacity") and role_widgets(box, "field")
    assert len(file_downloads(box)) == 1


def test_settings_menu_stays_open_and_follows_the_store(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    menu = find_by_role(box, "settings-menu", raster_spec.id)
    assert menu.close_on_content_click is False
    open_settings(box, raster_spec.id)

    store.set_opacity(raster_spec.id, 0.2)

    assert find_by_role(box, "settings-menu", raster_spec.id).v_model is True
    assert find_by_role(box, "opacity", raster_spec.id).v_model == 0.2


def test_tile_source_row_has_no_restyle_form():
    store = LayerStore()
    spec = _tiles("t")
    store.add(spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    open_settings(box, "t")
    assert role_widgets(box, "opacity") and not role_widgets(box, "field")
    assert not role_widgets(box, "apply")


class _FakeZoom:
    """Scripted zoom results and the instance the map says it published."""

    def __init__(self, results, instance=1):
        self.results = list(results)
        self.calls = 0
        self.instance = instance

    async def zoom_layer_async(self, layer_id, *, padding=20):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _zoom_panel(fake, monkeypatch):
    m = SepalMap(gee=False)
    m.zoom_layer_async = fake.zoom_layer_async
    monkeypatch.setattr(row, "_published_instance", lambda map_, layer_id: fake.instance)
    m.layer_store.add(_tiles("a"))
    m.layer_store.set_status("a", "ready")
    box, rc = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    return m.layer_store, box, rc


def _zoom(box):
    return find_by_role(box, "zoom", "a")


@pytest.mark.asyncio
async def test_zoom_runs_only_on_click(monkeypatch):
    fake = _FakeZoom(["moved"])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    store.set_visible("a", False)
    store.set_visible("a", True)
    await wait_until(lambda: True)
    assert fake.calls == 0

    click(_zoom(box))
    await wait_until(lambda: fake.calls == 1)
    assert fake.calls == 1
    rc.close()


@pytest.mark.asyncio
async def test_zoom_disabled_while_pending(monkeypatch):
    fake = _FakeZoom([])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    store.set_status("a", "pending")
    assert _zoom(box).disabled is True
    store.set_status("a", "ready")
    assert not _zoom(box).disabled
    rc.close()


@pytest.mark.asyncio
async def test_failed_zoom_stays_enabled(monkeypatch):
    fake = _FakeZoom(["failed", RuntimeError("boom")])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    click(_zoom(box))
    await wait_until(lambda: "Could not zoom" in all_text(box))
    assert not _zoom(box).disabled

    click(_zoom(box))
    await wait_until(lambda: fake.calls == 2)
    assert not _zoom(box).disabled
    rc.close()


@pytest.mark.asyncio
async def test_unbounded_layer_zoom_disables_the_button(monkeypatch):
    fake = _FakeZoom(["no_bounds"])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    click(_zoom(box))
    await wait_until(lambda: _zoom(box).disabled is True)
    assert "no bounds" in all_text(box)
    rc.close()


@pytest.mark.asyncio
async def test_no_bounds_clears_when_the_data_changes(monkeypatch):
    fake = _FakeZoom(["no_bounds"])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    click(_zoom(box))
    await wait_until(lambda: _zoom(box).disabled is True)

    # the same layer rendered again keeps it
    store.set_visible("a", False)
    assert _zoom(box).disabled is True

    # data written over the same path publishes a new instance
    fake.instance = 2
    store.set_visible("a", True)
    assert not _zoom(box).disabled
    rc.close()


@pytest.mark.asyncio
async def test_superseded_zoom_leaves_the_button_enabled(monkeypatch):
    fake = _FakeZoom(["superseded", "missing"])
    store, box, rc = _zoom_panel(fake, monkeypatch)
    for expected in (1, 2):
        click(_zoom(box))
        await wait_until(lambda: fake.calls == expected)
        await wait_until(lambda: True)
        assert not _zoom(box).disabled
    assert "Could not zoom" not in all_text(box) and "no bounds" not in all_text(box)
    rc.close()
