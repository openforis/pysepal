"""Tests for the LayerPanel, its rows and the basemap picker."""

import io
import shutil
import threading
import zipfile
from pathlib import Path

import solara

from pysepal.layers import LayerSpec, LayerStore
from pysepal.mapping import SepalMap
from pysepal.solara.components.layer_panel import LayerPanel, download
from pysepal.solara.components.layer_panel.download import download_payload
from tests.test_solara._layer_panel_helpers import (
    all_text,
    button_icon,
    click,
    expand,
    export_button,
    export_buttons,
    file_downloads,
    find_by_role,
    find_visibility_toggle,
    inline_legends,
    pick_basemap,
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


def test_basemap_picker_is_exclusive():
    m = SepalMap(gee=False, basemaps=["SEPAL_DARK", "OpenStreetMap"])
    box, _ = solara.render(LayerPanel(store=m.layer_store, map_=m), handle_error=False)
    pick_basemap(box, "OpenStreetMap")
    assert [lyr.visible for lyr in m.layers if lyr.base] == [False, True]


def test_row_remove_button_drops_the_row(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    box, rc = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
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


def test_expand_then_collapse(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    assert role_widgets(box, "remove")
    expand(box, raster_spec.id)
    assert not role_widgets(box, "remove")


def test_visibility_toggle_after_expanding(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    click(find_visibility_toggle(box, raster_spec.id))
    assert store.view(raster_spec.id).visible is False
    assert button_icon(find_visibility_toggle(box, raster_spec.id)) == "mdi-eye-off"


def test_opacity_slider_sets_view_opacity(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    find_by_role(box, "opacity", raster_spec.id).v_model = 0.4
    assert store.view(raster_spec.id).opacity == 0.4


def test_no_opacity_slider_for_pmtiles(pmtiles_spec):
    store = LayerStore()
    store.add(pmtiles_spec)
    store.set_status(pmtiles_spec.id, "ready", kind="pmtiles")
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, pmtiles_spec.id)
    assert role_widgets(box, "remove") and not role_widgets(box, "opacity")


def test_expanded_row_shows_inline_legend(byte):
    store = LayerStore()
    spec = LayerSpec.from_raster(byte, vmin=0, vmax=255)
    store.add(spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, spec.id)
    legends = inline_legends(box)
    assert len(legends) == 1 and legends[0].legend_data["gradients"]


def test_download_only_for_file_sources(raster_spec, gee_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.add(gee_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    assert len(file_downloads(box)) == 1
    expand(box, raster_spec.id)
    expand(box, gee_spec.id)
    assert role_widgets(box, "remove") and not file_downloads(box)


def _expanded(spec):
    store = LayerStore()
    store.add(spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, spec.id)
    return box


def test_download_disabled_above_the_size_limit(raster_spec, monkeypatch):
    monkeypatch.setattr(download, "DOWNLOAD_MAX_BYTES", 10)
    box = _expanded(raster_spec)
    assert find_by_role(box, "download", raster_spec.id).disabled is True
    # a click anywhere in a FileDownload, disabled button included, would read the file
    assert not file_downloads(box)
    tip = find_by_role(box, "download-tip", raster_spec.id)
    assert tip.disabled is False and "SEPAL file browser" in all_text(tip)


def test_download_enabled_below_the_size_limit(raster_spec):
    box = _expanded(raster_spec)
    tip = find_by_role(box, "download-tip", raster_spec.id)
    assert tip.disabled is True
    assert len(file_downloads(tip)) == 1 and not role_widgets(box, "download")


def test_missing_file_is_not_downloadable(tmp_path, byte):
    path = tmp_path / "r.tif"
    shutil.copy(byte, path)
    spec = LayerSpec.from_raster(path)
    path.unlink()
    box = _expanded(spec)
    assert role_widgets(box, "remove") and not role_widgets(box, "download-tip")
