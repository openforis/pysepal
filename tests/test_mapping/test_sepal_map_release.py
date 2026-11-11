"""A closed SepalMap releases itself and the widgets it built (#1058).

A Solara server keys ipywidgets' registry and the comms by kernel, so a widget
that is not closed stays reachable until its connection ends. These tests run
in a real kernel context and check what a closed map leaves behind.
"""

import gc
import weakref
from unittest.mock import MagicMock

import ee
import ipyleaflet as ipl
import ipywidgets.widgets.widget as widget_module
import pytest

from pysepal import mapping as sm
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
    return sm.SepalMap(gee=False, dc=True, vinspector=True, statebar=True, fullscreen_control=True)


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
    m.add_legend(legend_dict={"a": "#ff0000"})
    reference = weakref.ref(m)

    m.close()
    del m
    _collect()

    assert reference() is None


def test_a_closed_map_closes_the_widgets_it_built(kernel) -> None:
    before = _registered()
    comms_before = set(kernel.kernel.comm_manager.comms)

    m = _full_map()
    m.add_legend(legend_dict={"a": "#ff0000"})
    m.dc.hide()  # an owned control that is not in m.controls
    m.close()
    del m
    _collect()

    left = _registered() - before
    assert {type(widget_module._instances[k]).__name__ for k in left} == set()
    assert set(kernel.kernel.comm_manager.comms) - comms_before == set()


def test_a_closed_map_keeps_the_layers_of_its_caller(kernel) -> None:
    m = sm.SepalMap(gee=False, statebar=True)
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
    m = sm.SepalMap(gee=False, statebar=True)
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
        m.v_inspector.menu.v_model = True
        m.v_inspector.read_data(type="click", coordinates=[0, 0])
        m.v_inspector.menu.v_model = False
        m.legend.legend_dict = {"b": "#00ff00"} if "a" in m.legend.legend_dict else {"a": "#f00"}

    m.add_legend(legend_dict={"a": "#ff0000"})
    cycle()
    _collect()
    first = len(widget_module._instances)
    for _ in range(3):
        cycle()
    _collect()

    assert len(widget_module._instances) == first
    m.close()


def test_a_closed_control_releases_its_map(kernel) -> None:
    m = sm.SepalMap(gee=False)
    controls = [
        sm.ZoomControl(m),
        sm.LayersControl(m),
        sm.LayerStateControl(m),
        sm.InspectorControl(m),
        sm.FullScreenControl(m),
        sm.GeomanDrawControl(m),
        sm.MenuControl("fa-solid fa-cog", sm.MapBtn("x"), m=m),
    ]
    for control in controls:
        control.close()
        assert control.m is None
        assert getattr(control, "map_", None) is None
    # the map stays usable
    m.add_layer(ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="after"))
    reference = weakref.ref(m)

    m.close()
    del m
    _collect()

    # the caller still holds the closed controls, not the map
    assert reference() is None


def test_a_closed_menu_keeps_the_content_of_its_caller(kernel) -> None:
    m = sm.SepalMap(gee=False)
    content, title = sm.MapBtn("x"), sm.MapBtn("y")
    control = sm.MenuControl("fa-solid fa-cog", content, card_title=title, m=m)

    control.close()

    assert control.menu.comm is None
    assert content.comm is not None
    assert title.comm is not None
    m.close()


@pytest.mark.parametrize(
    "control_name",
    [
        "ZoomControl",
        "LayersControl",
        "LayerStateControl",
        "InspectorControl",
        "FullScreenControl",
        "GeomanDrawControl",
        "MenuControl",
        "LegendControl",
    ],
)
def test_a_control_that_failed_to_build_can_be_closed(control_name) -> None:
    """Widget.__del__ closes a control even when its __init__ raised."""
    control_class = getattr(sm, control_name)
    control_class.__new__(control_class).close()


def _after_close(control_name: str):
    """Return a control of a closed map."""
    m = _full_map()
    controls = {
        "dc": m.dc,
        "zoom": next(c for c in m.controls if isinstance(c, sm.ZoomControl)),
        "fullscreen": next(c for c in m.controls if isinstance(c, sm.FullScreenControl)),
        "inspector": m.v_inspector,
        "layers": next(c for c in m.controls if isinstance(c, sm.LayersControl)),
    }
    control = controls[control_name]
    m.close()
    return control


@pytest.mark.parametrize(
    "control_name, call",
    [
        ("dc", lambda c: c.show()),
        ("dc", lambda c: c.hide()),
        ("zoom", lambda c: c.zoom(c.plus)),
        ("fullscreen", lambda c: c.toggle_fullscreen()),
        ("inspector", lambda c: c.toggle_cursor()),
        ("inspector", lambda c: c.read_data(type="click", coordinates=[0, 0])),
        ("inspector", lambda c: c._from_eelayer.__wrapped__(c, MagicMock(spec=ee.Image), [0, 0])),
        ("inspector", lambda c: c._from_raster("missing.tif", [0, 0])),
        ("layers", lambda c: c.update_table({})),
    ],
)
def test_a_control_of_a_closed_map_does_nothing(kernel, control_name, call) -> None:
    """A task can finish after its map unmounted and still call a control."""
    call(_after_close(control_name))


def test_a_toggle_row_of_a_closed_map_does_nothing(kernel) -> None:
    m = sm.SepalMap(gee=False)
    control = next(c for c in m.controls if isinstance(c, sm.LayersControl))
    row = sm.layers_control.ToggleRow(ipl.Layer(name="x"), control, 0)
    m.close()

    row._toggle_layer()


def test_the_inspector_keeps_the_style_of_its_caller(kernel) -> None:
    style = ipl.MapStyle(cursor="grab")
    m = sm.SepalMap(gee=False, vinspector=True, default_style=style)

    m.v_inspector.menu.v_model = True
    m.v_inspector.menu.v_model = False
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
            sm.SepalMap.element(gee=False, vinspector=True, statebar=True, theme_state=theme_state)

    _box, rc = solara.render(Harness(), handle_error=False)
    try:
        if use_first:
            m = rc.find(sm.SepalMap).widget
            m.v_inspector.menu.v_model = True  # shows the marker
            m.add_layer(ipl.TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="used"))
        mounted.set(False)
    finally:
        rc.close()


@pytest.mark.parametrize("use_first", [False, True], ids=["fresh", "used"])
def test_unmounting_a_map_element_does_not_raise(kernel, use_first) -> None:
    """Reacton closes the widgets built with the map, like the marker, before the map."""
    _unmount(use_first)
