"""A closed SepalMap releases itself and the widgets it built (#1058).

A Solara server keys ipywidgets' registry and the comms by kernel, so a widget
that is not closed stays reachable until its connection ends. These tests run
in a real kernel context and check what a closed map leaves behind.
"""

import gc
import weakref

import ipyleaflet as ipl
import ipywidgets.widgets.widget as widget_module
import pytest

from pysepal import mapping as sm
from pysepal.layers import LayerStore
from tests._kernel_contexts import kernel_contexts  # noqa: F401


def _collect() -> None:
    for _ in range(3):
        gc.collect()


def _registered() -> set:
    return set(widget_module._instances.keys())


def _handlers(widget) -> list:
    """Every observer registered on the traits of a widget."""
    return [
        h for by_type in widget._trait_notifiers.values() for hs in by_type.values() for h in hs
    ]


def _full_map() -> sm.SepalMap:
    """A map with every control SepalMap can build."""
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
    m.add_layer(ipl.GeoJSON(data={"type": "FeatureCollection", "features": []}, name="v"))
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


def test_a_closed_map_keeps_the_layers_of_its_caller(kernel) -> None:
    m = sm.SepalMap(gee=False)
    layer = ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="caller")
    own_handlers = _handlers(layer)
    m.add_layer(layer)
    reference = weakref.ref(m)

    m.close()
    del m
    _collect()

    assert reference() is None
    assert layer.comm is not None
    # neither a control nor a link of the layer table still observes it
    assert _handlers(layer) == own_handlers


def test_a_removed_layer_is_no_longer_observed(kernel) -> None:
    m = sm.SepalMap(gee=False)
    layer = ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="caller")
    own_handlers = _handlers(layer)
    m.add_layer(layer)
    m.remove_layer(layer)

    assert _handlers(layer) == own_handlers
    m.close()


def test_an_open_map_does_not_accumulate_widgets(kernel) -> None:
    m = _full_map()
    layer = ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="caller")
    vector = ipl.GeoJSON(data={"type": "FeatureCollection", "features": []}, name="v")

    def cycle() -> None:
        m.add_layer(layer)
        m.add_layer(vector)
        m.remove_layer(vector)
        m.remove_layer(layer)
        m._on_theme_change({"new": not m._is_dark()})

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
    drawn = [m.layer_engine.leaflet_layer(layer_id) for layer_id in store.ids]
    assert all(layer is not None for layer in drawn)
    reference = weakref.ref(m)

    m.close()

    assert store._subscribers == []
    assert all(layer.comm is None for layer in drawn)
    assert not any(getattr(layer, "layer_id", None) for layer in m.layers)
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

    store.set_visible(pmtiles_spec.id, True)
    store.restyle(raster_spec.id, colormap="magma")
    store.remove(pmtiles_spec.id)

    assert m.layer_engine.leaflet_layer(raster_spec.id) is None
    assert not any(getattr(layer, "layer_id", None) for layer in m.layers)


def test_a_map_keeps_the_style_of_its_caller(kernel) -> None:
    style = ipl.MapStyle(cursor="grab")
    m = sm.SepalMap(gee=False, default_style=style)
    assert style.comm is not None

    m.close()
    assert style.comm is not None


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
            m.add_layer(ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="used"))
        mounted.set(False)
    finally:
        rc.close()


@pytest.mark.parametrize("use_first", [False, True], ids=["fresh", "used"])
def test_unmounting_a_map_element_does_not_raise(kernel, use_first) -> None:
    """Reacton closes the widgets built with the map, like the marker, before the map."""
    _unmount(use_first)
