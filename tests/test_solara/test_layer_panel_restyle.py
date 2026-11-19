"""Tests for the restyle form of the LayerPanel."""

import solara

from pysepal.layers import LayerStore
from pysepal.mapping.layer_engine import leaflet_style
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.layer_panel.restyle import RestyleForm
from tests.test_solara._layer_panel_helpers import (
    all_text,
    click_apply,
    expand,
    field_names,
    set_field,
)


def test_apply_sends_only_changes(raster_spec):
    sent = []
    box, _ = solara.render(RestyleForm(spec=raster_spec, on_apply=sent.append), handle_error=False)
    set_field(box, "max", "120")
    click_apply(box)
    assert sent == [{"max": 120.0}]


def test_invalid_palette_shows_error_and_keeps_store(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    set_field(box, "palette", "#zz")
    click_apply(box)
    assert store.get(raster_spec.id).revision == 0 and "palette" in all_text(box).lower()


def test_vector_form_fields(vector_spec):
    box, _ = solara.render(
        RestyleForm(spec=vector_spec, on_apply=lambda c: None), handle_error=False
    )
    assert field_names(box) == ["stroke", "fill", "fill_opacity", "width"]


def test_fill_only_edit_is_visible(vector_spec):
    store = LayerStore()
    store.add(vector_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, vector_spec.id)
    set_field(box, "fill", "#00ff00")
    click_apply(box)
    style = store.get(vector_spec.id).style
    assert leaflet_style(style, 1.0, "#000000")["fillOpacity"] == 1.0


def test_class_colors_raster_has_no_form(raster_spec):
    style = raster_spec.style.model_copy(update={"class_colors": {1: "#ffffff"}})
    box, _ = solara.render(
        RestyleForm(spec=raster_spec.revise(style=style), on_apply=lambda c: None),
        handle_error=False,
    )
    assert field_names(box) == []


def test_a_valid_apply_clears_the_error(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    box, _ = solara.render(LayerPanel(store=store), handle_error=False)
    expand(box, raster_spec.id)
    set_field(box, "palette", "#zz")
    click_apply(box)
    set_field(box, "palette", "#000000,#ffffff")
    click_apply(box)
    assert store.get(raster_spec.id).revision == 1 and "palette" not in all_text(box).lower()
