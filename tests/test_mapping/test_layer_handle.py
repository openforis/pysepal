"""Tests for live layer handles."""

import pytest

from pysepal.layers import LayerStore, Legend, LegendItem
from pysepal.mapping import LayerGoneError, LayerHandle


class FakeMap:
    def __init__(self):
        """Create the fake."""
        self.layer_store = LayerStore()
        self.zoom_calls = []
        self.answer = "moved"

    def zoom_layer(self, layer_id, *, padding=20):
        self.zoom_calls.append((layer_id, padding))
        return self.answer

    async def zoom_layer_async(self, layer_id, *, padding=20):
        self.zoom_calls.append((layer_id, padding))
        return self.answer


@pytest.fixture
def fake_map():
    return FakeMap()


def test_handle_reads_and_writes_the_store(fake_map, vector_spec):
    store = fake_map.layer_store
    store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    assert h.id == vector_spec.id
    assert h.store is store
    assert h.alive
    assert h.name == vector_spec.name
    assert h.visible is True
    h.visible = False
    assert store.view(h.id).visible is False
    h.opacity = 0.4
    assert store.view(h.id).opacity == 0.4
    assert h.opacity == 0.4
    store.set_status(h.id, "error", error="boom")
    assert h.status == "error"
    assert h.error == "boom"
    h.remove()
    assert vector_spec.id not in store
    assert not h.alive


def test_handle_holds_no_copy(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    fake_map.layer_store.restyle(vector_spec.id, width=5.0)
    assert h.spec.style.width == 5.0
    assert h.restyle(width=7.0).style.width == 7.0
    assert h.spec.style.width == 7.0


def test_gone_layer_raises(fake_map, vector_spec):
    h = LayerHandle(fake_map, vector_spec.id)
    assert not h.alive
    for attr in ("spec", "name", "visible", "opacity", "side", "status", "error"):
        with pytest.raises(LayerGoneError, match="is no longer on the map"):
            getattr(h, attr)
    with pytest.raises(LayerGoneError):
        h.visible = False
    with pytest.raises(LayerGoneError):
        h.opacity = 0.5
    with pytest.raises(LayerGoneError):
        h.restyle(width=1.0)
    with pytest.raises(LayerGoneError):
        h.zoom()
    with pytest.raises(LayerGoneError):
        h.remove()
    assert fake_map.zoom_calls == []
    assert issubclass(LayerGoneError, KeyError)

    fake_map.layer_store.add(vector_spec)
    assert h.alive
    assert h.name == vector_spec.name


@pytest.mark.asyncio
async def test_zoom_async_gone_raises(fake_map, vector_spec):
    with pytest.raises(LayerGoneError):
        await LayerHandle(fake_map, vector_spec.id).zoom_async()


def test_zoom_delegates_and_reports(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    fake_map.answer = "no_bounds"
    assert LayerHandle(fake_map, vector_spec.id).zoom() == "no_bounds"
    assert fake_map.zoom_calls == [(vector_spec.id, 20)]


@pytest.mark.asyncio
async def test_zoom_async_delegates(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    fake_map.answer = "preparing"
    assert await LayerHandle(fake_map, vector_spec.id).zoom_async(padding=3) == "preparing"
    assert fake_map.zoom_calls == [(vector_spec.id, 3)]


def test_equal_by_store_and_id(fake_map):
    other = FakeMap()
    other.layer_store = fake_map.layer_store
    a, b = LayerHandle(fake_map, "x"), LayerHandle(other, "x")
    assert a == b
    assert hash(a) == hash(b)
    assert a != LayerHandle(fake_map, "y")
    assert a != LayerHandle(FakeMap(), "x")
    assert a != "x"
    assert repr(a) == "LayerHandle('x')"


def test_handle_side(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    assert h.side == "both"
    h.side = "right"
    assert fake_map.layer_store.view(h.id).side == "right"
    h.remove()
    with pytest.raises(LayerGoneError):
        h.side
    with pytest.raises(LayerGoneError):
        h.side = "left"


def test_zoom_takes_padding_by_keyword(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    handle = LayerHandle(fake_map, vector_spec.id)
    with pytest.raises(TypeError):
        handle.zoom(2)
    handle.zoom(padding=2)
    assert fake_map.zoom_calls == [(vector_spec.id, 2)]


def test_legend_setter_writes_the_spec_and_none_clears_it(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    own = Legend(title="own", items=[LegendItem(label="a", color="#ff0000")])
    assert h.legend is None

    h.legend = own
    assert h.legend == own
    assert fake_map.layer_store.get(h.id).legend == own

    h.legend = None
    assert h.legend is None


def test_legend_on_a_removed_layer_raises(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    h.remove()
    with pytest.raises(LayerGoneError):
        h.legend = Legend()
    with pytest.raises(LayerGoneError):
        h.legend


def test_a_restyle_keeps_an_explicit_legend(fake_map, vector_spec):
    fake_map.layer_store.add(vector_spec)
    h = LayerHandle(fake_map, vector_spec.id)
    own = Legend(title="own", items=[LegendItem(label="a", color="#ff0000")])
    h.legend = own

    h.restyle(stroke="#00ff00")

    assert h.legend == own
    assert h.spec.style.stroke == "#00ff00"
