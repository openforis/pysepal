"""Tests for the observable layer store."""

import pytest

from pysepal.layers import LayerStore, StoreEvent


def test_add_orders_top_first(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    assert store.ids == [raster_spec_b.id, raster_spec.id]


def test_duplicate_id_needs_replace(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    with pytest.raises(ValueError):
        store.add(raster_spec)


def test_replace_keeps_slot_and_view(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b)
    store.set_opacity(raster_spec.id, 0.3)
    store.add(raster_spec.model_copy(update={"name": "renamed"}), replace=True)
    assert store.ids == [raster_spec_b.id, raster_spec.id]
    assert store.view(raster_spec.id).opacity == 0.3
    assert store.get(raster_spec.id).revision == 1
    assert len(store.history(raster_spec.id)) == 2


def test_restyle_emits_updated_and_keeps_data_hash(raster_spec):
    store, events = LayerStore(), []
    store.add(raster_spec)
    store.subscribe(events.append)
    new = store.restyle(raster_spec.id, colormap="magma")
    assert events == [StoreEvent("updated", raster_spec.id)]
    assert new.data_hash == raster_spec.data_hash


def test_restyle_palette_and_colormap_are_one_choice(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    style = store.restyle(raster_spec.id, palette=["#000000", "#ffffff"]).style
    assert style.palette == ["#000000", "#ffffff"] and style.colormap is None
    style = store.restyle(raster_spec.id, colormap="magma").style
    assert style.colormap == "magma" and style.palette is None


def test_move_and_noop_move(raster_spec, raster_spec_b):
    store, events = LayerStore(), []
    store.add(raster_spec)
    store.add(raster_spec_b)
    store.subscribe(events.append)
    store.move(raster_spec.id, 0)
    store.move(raster_spec.id, 0)
    assert store.ids == [raster_spec.id, raster_spec_b.id]
    assert events == [StoreEvent("moved", raster_spec.id)]


def test_opacity_clamped(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.set_opacity(raster_spec.id, 2)
    assert store.view(raster_spec.id).opacity == 1.0


def test_nested_mutation_does_not_leak(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    store.restyle(raster_spec.id, palette=["#000000", "#ffffff"])
    before = store.get(raster_spec.id).render_hash
    store.get(raster_spec.id).style.palette.append("#ff0000")
    store.history(raster_spec.id)[-1].style.palette.clear()
    assert store.get(raster_spec.id).render_hash == before
    assert len(store.get(raster_spec.id).style.palette) == 2


def test_generation_guards_stale_writes(raster_spec):
    store = LayerStore()
    k = raster_spec.model_copy(update={"id": "k"})
    gen = store.reserve("k")
    store.remove("k", missing_ok=True)  # a newer action on a not-yet-added id
    assert store.add(k, expect_generation=gen) is None and "k" not in store
    gen = store.reserve("k")
    assert store.add(k, expect_generation=gen) == "k"
    gen = store.reserve("k")
    store.restyle("k", colormap="gray")
    assert store.add(k, replace=True, expect_generation=gen) is None
    assert store.get("k").style.colormap == "gray"


def test_clear_invalidates_reservations(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    gen = store.reserve("pending", name="p")
    assert store.reserved() == {"pending": "p"}
    store.clear()
    assert len(store) == 0
    assert store.generation("pending") != gen
    assert store.reserved() == {}


def test_release_is_token_conditional():
    store = LayerStore()
    old = store.reserve("k", name="k")
    new = store.reserve("k", name="k")
    store.release("k", old)
    assert store.reserved() == {"k": "k"}  # an older call cannot drop a newer reservation
    store.release("k", new)
    assert store.reserved() == {} and store.generation("k") == new


def test_unsubscribe_and_failing_subscriber(raster_spec, caplog):
    store, events = LayerStore(), []
    store.subscribe(lambda e: 1 / 0)
    unsubscribe = store.subscribe(events.append)
    store.add(raster_spec)
    unsubscribe()
    store.remove(raster_spec.id)
    assert events == [StoreEvent("added", raster_spec.id)]
    assert "ZeroDivisionError" in caplog.text


@pytest.mark.parametrize("change", [{"zone": "overlay"}, {"attribution": "(c) someone"}])
def test_zone_or_attribution_change_is_an_update(vector_spec, change):
    store, events = LayerStore(), []
    store.add(vector_spec)
    store.subscribe(events.append)
    store.update(vector_spec.id, vector_spec.model_copy(update=change))
    assert events == [StoreEvent("updated", vector_spec.id)]


def test_drawing_order_puts_overlays_first(vector_spec):
    store = LayerStore()
    for name in ("d2", "o1", "d1"):
        zone = "overlay" if name == "o1" else "data"
        store.add(vector_spec.model_copy(update={"id": name, "zone": zone}))
    assert store.ids == ["d1", "o1", "d2"]
    assert store.drawing_order() == ["o1", "d1", "d2"]


def test_set_side_emits_once(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    assert store.view(raster_spec.id).side == "both"
    events = []
    store.subscribe(events.append)
    store.set_side(raster_spec.id, "left")
    store.set_side(raster_spec.id, "left")
    assert store.view(raster_spec.id).side == "left"
    assert events == [StoreEvent("side", raster_spec.id)]


def test_set_side_rejects_unknown(raster_spec):
    store = LayerStore()
    store.add(raster_spec)
    with pytest.raises(ValueError):
        store.set_side(raster_spec.id, "top")
    with pytest.raises(ValueError):
        store.add(raster_spec.model_copy(update={"id": "other"}), side="top")
    assert store.view(raster_spec.id).side == "both"


def test_replace_keeps_side(raster_spec):
    store = LayerStore()
    store.add(raster_spec, side="right")
    store.add(raster_spec, side="left", replace=True)
    assert store.view(raster_spec.id).side == "right"
