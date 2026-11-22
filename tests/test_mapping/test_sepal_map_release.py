"""A closed SepalMap releases itself and the widgets it built (#1058).

A Solara server keys ipywidgets' registry and the comms by kernel, so a widget
that is not closed stays reachable until its connection ends. These tests run
in a real kernel context and check what a closed map leaves behind.
"""

import gc
import weakref

import ipywidgets.widgets.widget as widget_module
import pytest

from pysepal import mapping as sm
from pysepal.layers import LayerSpec, LayerStore
from tests._kernel_contexts import kernel_contexts  # noqa: F401

TILES = "https://example.org/{z}/{x}/{y}.png"


def _collect() -> None:
    for _ in range(3):
        gc.collect()


def _registered() -> set:
    return set(widget_module._instances.keys())


def _full_map() -> sm.SepalMap:
    """A map with every control SepalMap can show."""
    return sm.SepalMap(gee=False, fullscreen_control=True)


@pytest.fixture
def kernel(kernel_contexts):  # noqa: F811
    """Enter one kernel context, after a first map has warmed up lazy imports."""
    context = kernel_contexts()
    with context:
        sm.SepalMap(gee=False).close()
        _collect()
        yield context


def test_a_closed_map_is_collected(kernel) -> None:
    m = _full_map()
    m.layer_store.add(LayerSpec.from_tiles(TILES, name="t", id="t"))
    m.add_basemap("OpenStreetMap")
    reference = weakref.ref(m)

    m.close()
    del m
    _collect()

    assert reference() is None


def test_a_closed_map_closes_the_widgets_it_built(kernel) -> None:
    before = _registered()
    comms_before = set(kernel.kernel.comm_manager.comms)

    m = _full_map()
    m.close()
    del m
    _collect()

    left = _registered() - before
    assert {type(widget_module._instances[k]).__name__ for k in left} == set()
    assert set(kernel.kernel.comm_manager.comms) - comms_before == set()


def test_an_open_map_does_not_accumulate_widgets(kernel) -> None:
    m = _full_map()

    def cycle() -> None:
        m.layer_store.add(LayerSpec.from_tiles(TILES, name="t", id="t"))
        m.add_basemap("OpenStreetMap")
        m.remove_layer("t")
        m.basemap = m.basemaps[0]
        m._apply_theme(m.theme == "light")

    cycle()
    _collect()
    first = len(widget_module._instances)
    for _ in range(3):
        cycle()
    _collect()

    assert len(widget_module._instances) == first
    m.close()


def _store_with_layers(raster_spec, pmtiles_spec) -> LayerStore:
    """A store holding a shown raster and a hidden PMTiles layer."""
    store = LayerStore()
    store.add(raster_spec)
    store.add(pmtiles_spec, visible=False)
    return store


def test_a_closed_map_leaves_no_engine_behind(kernel, raster_spec, pmtiles_spec) -> None:
    store = _store_with_layers(raster_spec, pmtiles_spec)
    m = sm.SepalMap(gee=False, layer_store=store)
    assert [layer["id"] for layer in m.state["layers"]] == store.ids
    reference = weakref.ref(m)

    m.close()

    assert store._subscribers == []
    assert m.layer_engine.accepted(raster_spec.id) is None
    # the caller's store keeps its layers, and no longer holds the map
    assert store.ids == [pmtiles_spec.id, raster_spec.id]
    del m
    _collect()
    assert reference() is None


def test_a_store_write_after_close_does_nothing(kernel, raster_spec, pmtiles_spec) -> None:
    """A task can finish after its map unmounted and still write to the store."""
    store = _store_with_layers(raster_spec, pmtiles_spec)
    m = sm.SepalMap(gee=False, layer_store=store)
    m.close()
    published = m.state

    store.set_visible(pmtiles_spec.id, True)
    store.restyle(raster_spec.id, colormap="magma")
    store.remove(pmtiles_spec.id)

    assert m.state == published
    assert m.layer_engine.accepted(raster_spec.id) is None


def _unmount(use_first: bool) -> None:
    """Render a map behind a reactive bool, then unmount it."""
    import solara

    from pysepal.solara.theme import ThemeState

    mounted = solara.reactive(True)
    theme_state = ThemeState()

    @solara.component
    def Harness():
        if mounted.value:
            sm.SepalMap.element(gee=False, theme_state=theme_state)

    _box, rc = solara.render(Harness(), handle_error=False)
    try:
        if use_first:
            m = rc.find(sm.SepalMap).widget
            m.layer_store.add(LayerSpec.from_tiles(TILES, name="used", id="used"))
        mounted.set(False)
    finally:
        rc.close()


@pytest.mark.parametrize("use_first", [False, True], ids=["fresh", "used"])
def test_unmounting_a_map_element_does_not_raise(kernel, use_first) -> None:
    """Reacton closes the map when its element unmounts."""
    _unmount(use_first)


def test_closing_a_half_built_map_raises_and_logs_nothing(kernel, caplog) -> None:
    """A refused construction leaves close() (and __del__) with nothing to read."""
    with pytest.raises(ValueError):
        sm.SepalMap(gee=False, gee_session=object(), gee_interface=object())
    with pytest.raises(TypeError):
        sm.SepalMap(1, 2, 3)
    _collect()
    assert not caplog.records

    half = object.__new__(sm.SepalMap)
    half.close()
