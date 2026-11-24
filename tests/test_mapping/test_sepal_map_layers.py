"""SepalMap draws its layers through a LayerStore and a MapLibreEngine."""

import asyncio

import pytest

import pysepal.mapping.sepal_map as sepal_map_module
from pysepal.frontend.styles import THEMES
from pysepal.layers import (
    LayerPrepareError,
    LayerSpec,
    LayerStore,
    RenderLayer,
    prepare_sync,
)
from pysepal.mapping import LayerHandle
from pysepal.mapping.sepal_map import SepalMap
from pysepal.solara.theme import ThemeState, get_current_theme_state
from tests.test_solara._harness import wait_until


def layer_of(m: SepalMap, layer_id: str):
    return next((x for x in m.state.get("layers", ()) if x["id"] == layer_id), None)


def ids_of(m: SepalMap) -> list:
    return [x["id"] for x in m.state.get("layers", ())]


def test_map_owns_a_store():
    m = SepalMap(gee=False)
    assert isinstance(m.layer_store, LayerStore) and len(m.layer_store) == 0
    assert m.state["layers"] == []


def test_prefilled_store_attaches_with_stored_visibility(raster_spec, raster_spec_b):
    store = LayerStore()
    store.add(raster_spec)
    store.add(raster_spec_b, visible=False)
    m = SepalMap(gee=False, layer_store=store)
    assert m.layer_store is store
    assert ids_of(m) == [raster_spec_b.id, raster_spec.id]
    assert layer_of(m, raster_spec.id)["visible"] is True
    assert layer_of(m, raster_spec_b.id)["visible"] is False


def test_prefilled_store_takes_the_bound_theme(fake_vector):
    # the opposite of the kernel's theme, which the map follows until it binds its own
    dark = not get_current_theme_state().dark
    store = LayerStore()
    store.add(LayerSpec.from_vector(fake_vector, id="v"))
    m = SepalMap(
        gee=False, theme_state=ThemeState(mode="dark" if dark else "light"), layer_store=store
    )
    assert layer_of(m, "v")["paint"]["stroke"] == THEMES[dark]["primary"]


def test_map_layers_keep_the_add_order(byte):
    m = SepalMap(gee=False)
    for key in ("a", "b", "c"):
        m.add_raster(byte, key=key)
    # top first, in the store and in the published state
    assert m.layer_store.ids == ids_of(m) == ["c", "b", "a"]


def test_async_wrapper_stale_completion(byte, monkeypatch):
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        first = asyncio.create_task(m.add_raster_async(byte, key="k", colormap="viridis"))
        second = asyncio.create_task(m.add_raster_async(byte, key="k", colormap="magma"))
        await wait_until(lambda: len(gates) == 2)
        gates[1].set()
        assert await second == LayerHandle(m, "k")
        gates[0].set()
        assert await first is None and m.layer_store.get("k").style.colormap == "magma"

    asyncio.run(run())


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize(
    "newer, expected",
    [
        ("panel_remove", None),
        ("panel_restyle", "gray"),
        ("sync_replace", "cividis"),
        ("remove_all", None),
        ("remove_layer", None),
        ("remove_layer_by_name", None),
    ],
)
def test_newer_action_beats_pending_wrapper(byte, monkeypatch, existing, newer, expected):
    if newer == "panel_restyle" and not existing:
        pytest.skip("nothing to restyle before the first add lands")
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        if existing:
            m.add_raster(byte, key="k", colormap="viridis")  # sync path: not gated
        pending = asyncio.create_task(
            m.add_raster_async(byte, layer_name="Pending", key="k", colormap="magma")
        )
        await wait_until(lambda: len(gates) == 1)
        {
            "panel_remove": lambda: m.layer_store.remove("k", missing_ok=True),
            "panel_restyle": lambda: m.layer_store.restyle("k", colormap="gray"),
            "sync_replace": lambda: m.add_raster(byte, key="k", colormap="cividis"),
            "remove_all": lambda: m.remove_all(),
            "remove_layer": lambda: m.remove_layer("k", none_ok=True),
            "remove_layer_by_name": lambda: m.remove_layer("Pending", none_ok=True),
        }[newer]()
        gates[0].set()
        assert await pending is None
        assert (m.layer_store.get("k").style.colormap if "k" in m.layer_store else None) == expected

    asyncio.run(run())


@pytest.mark.parametrize("outcome", ["error", "cancel", "older_error"])
def test_wrapper_releases_its_reservation(byte, tmp_path, monkeypatch, outcome):
    gates = []

    async def slow_prepare(spec, **kw):
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()
        return prepare_sync(spec, **kw)

    monkeypatch.setattr(sepal_map_module, "prepare", slow_prepare)

    async def run():
        m = SepalMap(gee=False)
        first = asyncio.create_task(
            m.add_raster_async(byte if outcome == "cancel" else tmp_path / "gone.tif", key="k")
        )
        await wait_until(lambda: len(gates) == 1)
        if outcome == "older_error":
            newer = asyncio.create_task(m.add_raster_async(byte, key="k"))
            await wait_until(lambda: len(gates) == 2)
        first.cancel() if outcome == "cancel" else gates[0].set()
        with pytest.raises((LayerPrepareError, asyncio.CancelledError)):
            await first
        assert set(m.layer_store.reserved()) == ({"k"} if outcome == "older_error" else set())
        if outcome == "older_error":
            gates[1].set()
            await newer
            assert "k" in m.layer_store and m.layer_store.reserved() == {}

    asyncio.run(run())


def test_hidden_layer_found_and_removed_by_name(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="Elevation", key="dem")
    m.layer_store.set_visible("dem", False)
    assert m.find_layer("Elevation") == LayerHandle(m, "dem")
    m.remove_layer("Elevation")
    assert "dem" not in m.layer_store


def test_an_id_beats_a_name(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="x", key="managed")
    m.add_raster(byte, layer_name="other", key="x")
    assert m.find_layer("x").id == "x"
    m.remove_layer("x")
    assert m.layer_store.ids == ["managed"]


def test_add_raster_goes_through_store(byte):
    m = SepalMap(gee=False)
    layer = m.add_raster(byte, layer_name="dem", key="dem")
    _, render = m.layer_engine.accepted("dem")
    assert m.layer_store.ids == ["dem"] and layer == LayerHandle(m, "dem")
    assert render.raster == str(byte.resolve())


def test_same_key_replaces_in_place(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, key="a")
    m.add_raster(byte, key="b")
    m.add_raster(byte, key="a", colormap="magma")
    assert m.layer_store.ids == ["b", "a"] and m.layer_store.get("a").revision == 1


def test_remove_mixed_layers(byte, pmtiles_spec):
    m = SepalMap(gee=False)
    m.add_raster(byte, layer_name="managed", key="managed")
    overlay = LayerSpec.from_tiles("https://t/{z}/{x}/{y}", name="raw", id="raw", zone="overlay")
    m.layer_store.add(overlay)
    m.layer_store.add(pmtiles_spec)
    m.layer_store.set_visible(pmtiles_spec.id, False)
    m.remove_layer(pmtiles_spec.id)  # hidden, still removable by key
    m.remove_all(keep_names=["raw"])
    assert m.layer_store.ids == ["raw"] and ids_of(m) == ["raw"]


def test_managed_layers_follow_theme(fake_vector):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v"))
    before = layer_of(m, "v")["paint"]["stroke"]
    theme.set_mode("dark")
    assert layer_of(m, "v")["paint"]["stroke"] != before


@pytest.mark.parametrize("kind", ["geojson", "ee"])
def test_hidden_layer_follows_theme_when_shown(fake_vector, gee_spec, kind):
    theme = ThemeState(mode="light")
    m = SepalMap(gee=False, theme_state=theme)
    if kind == "geojson":
        m.layer_store.add(LayerSpec.from_vector(fake_vector, id="v"))
    else:
        spec = gee_spec.model_copy(update={"id": "v"})
        m.layer_engine.put(
            RenderLayer(
                render_hash=spec.render_hash,
                kind="raster-xyz",
                url="https://light/{z}/{x}/{y}",
                theme_urls={False: "https://light/{z}/{x}/{y}", True: "https://dark/{z}/{x}/{y}"},
            )
        )
        m.layer_store.add(spec)
    m.layer_store.set_visible("v", False)
    theme.set_mode("dark")
    m.layer_store.set_visible("v", True)
    layer = layer_of(m, "v")
    if kind == "geojson":
        assert layer["paint"]["stroke"] == THEMES[True]["primary"]
    else:
        assert layer["source"]["tiles"][0].startswith("https://dark")


def test_unnamed_rasters_get_their_own_layers(byte, int16_classes):
    m = SepalMap(gee=False)
    first = m.add_raster(byte)
    second = m.add_raster(int16_classes)
    assert len(m.layer_store) == 2 and first != second
    assert set(ids_of(m)) == {first.id, second.id}
    assert len({spec.name for spec in m.layer_store.specs()}) == 2


def test_unnamed_rasters_get_their_own_layers_async(byte, int16_classes):
    async def run():
        m = SepalMap(gee=False)
        layers = await asyncio.gather(m.add_raster_async(byte), m.add_raster_async(int16_classes))
        assert len(m.layer_store) == 2 and all(layer.alive for layer in layers)
        assert layers[0] != layers[1]

    asyncio.run(run())


def test_a_hidden_unnamed_raster_is_not_replaced(byte, int16_classes):
    m = SepalMap(gee=False)
    first = m.add_raster(byte)
    m.layer_store.set_visible(first.id, False)
    m.add_raster(int16_classes)
    assert len(m.layer_store) == 2


def test_a_keyed_raster_without_a_name_keeps_its_name(byte):
    m = SepalMap(gee=False)
    m.add_raster(byte, key="k")
    name = m.layer_store.get("k").name
    m.add_raster(byte, key="k", colormap="magma")
    assert m.layer_store.ids == ["k"] and m.layer_store.get("k").name == name


@pytest.mark.parametrize("option", [{"warp_to_3857": True}, {"optimize": False}])
def test_restyle_keeps_the_prepare_options(byte, monkeypatch, option):
    m = SepalMap(gee=False)
    m.add_raster(byte, key="w", **option)
    seen = []

    def spy(spec, **kwargs):
        seen.append(kwargs)
        return prepare_sync(spec, **kwargs)

    monkeypatch.setattr("pysepal.mapping.maplibre_engine.prepare_sync", spy)
    m.layer_store.restyle("w", colormap="magma")
    assert len(seen) == 1 and option.items() <= seen[0].items()


def test_layer_methods_take_side(byte):
    m = SepalMap(gee=False)
    handle = m.add_raster(byte, key="r", side="right")
    assert handle.side == "right"
    assert layer_of(m, "r")["side"] == "right"
    again = m.add_raster(byte, key="r", colormap="viridis")
    assert again.side == "right"
    replaced = m.add_raster(byte, key="r", side="left")
    assert replaced.side == "right"
