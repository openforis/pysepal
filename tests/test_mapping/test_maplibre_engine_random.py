"""Random sequences of store operations against the MapLibre engine.

Each sequence runs on one loop, with prepares that settle at once or after a few
turns of the loop, so draws, prepares and later writes interleave. Every burst of
operations is followed by ``wait_idle``; the published state must then follow the
store: the drawing order, each layer's visibility and opacity, and every payload a
view would pull.
"""

import asyncio
import random

import pytest
from pysepal_map import MapWidget

import pysepal.mapping.maplibre_engine as maplibre_engine
from pysepal.layers import LayerSpec, LayerStore, RenderLayer

OPS_PER_SEED = 48
BURST = 8
SEEDS = range(40)
IDS = ("a", "b", "c", "d", "e")


def make_spec(layer_id: str, kind: str, variant: int) -> LayerSpec:
    """A raster or GeoJSON spec of ``layer_id``; ``variant`` picks its data."""
    if kind == "raster":
        url = f"https://tiles.test/{layer_id}/{variant}/{{z}}/{{x}}/{{y}}.png"
        return LayerSpec.from_tiles(url, name=layer_id, id=layer_id)
    uri = f"https://data.test/{layer_id}/{variant}.geojson"
    return LayerSpec.from_vector(uri, name=layer_id, id=layer_id)


def made_up(spec: LayerSpec) -> RenderLayer:
    if spec.source.type == "tile":
        url = f"{spec.source.url}?style={spec.render_hash[:8]}"
        return RenderLayer(render_hash=spec.render_hash, kind="raster-xyz", url=url)
    x = int(spec.source.uri.rsplit("/", 1)[1].split(".")[0])
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [x, 0]},
    }
    data = {"type": "FeatureCollection", "features": [feature]}
    return RenderLayer(
        render_hash=spec.render_hash, kind="geojson", data=data, vector_style=spec.style
    )


class Prepare:
    """Settles each prepare at once, or after the loop turns its spec id was given."""

    def __init__(self) -> None:
        """Settle every prepare at once until told otherwise."""
        self.turns: dict[str, int] = {}

    async def __call__(self, spec: LayerSpec, **kw) -> RenderLayer:
        for _ in range(self.turns.get(spec.id, 0)):
            await asyncio.sleep(0)
        return made_up(spec)


def random_op(rng: random.Random, store: LayerStore, engine, prepare: Prepare, theme: list) -> str:
    """Apply one random operation and describe it."""
    present = store.ids
    absent = [layer_id for layer_id in IDS if layer_id not in store]
    kinds = ["theme"]
    if absent:
        kinds += ["add"] * 3
    if present:
        kinds += ["replace", "remove", "move", "move", "visible", "opacity", "restyle"]
    kind = rng.choice(kinds)

    if kind == "theme":
        theme[0] = "light" if theme[0] == "dark" else "dark"
        engine.configure(theme=theme[0])
        return f"theme {theme[0]}"
    if kind in ("add", "replace"):
        layer_id = rng.choice(absent if kind == "add" else present)
        spec = make_spec(layer_id, rng.choice(["raster", "geojson"]), rng.randint(0, 2))
        prepare.turns[layer_id] = rng.choice([0, 0, 1, 3])
        timing = "sync" if prepare.turns[layer_id] == 0 else "async"
        if kind == "replace":
            store.add(spec, replace=True)
            return f"replace {layer_id} with {spec.source.type} ({timing})"
        index, visible = rng.randint(0, len(present)), rng.random() < 0.8
        store.add(spec, index=index, visible=visible, opacity=rng.choice([1.0, 0.5]))
        return f"add {spec.source.type} {layer_id} at {index} visible={visible} ({timing})"

    layer_id = rng.choice(present)
    if kind == "remove":
        store.remove(layer_id)
    elif kind == "move":
        to = rng.randint(0, len(present) - 1)
        store.move(layer_id, to)
        return f"move {layer_id} to {to}"
    elif kind == "visible":
        visible = not store.view(layer_id).visible
        store.set_visible(layer_id, visible)
        return f"visible {layer_id} {visible}"
    elif kind == "opacity":
        opacity = rng.choice([0.2, 0.6, 1.0])
        store.set_opacity(layer_id, opacity)
        return f"opacity {layer_id} {opacity}"
    elif kind == "restyle":
        if store.get(layer_id).source.type == "tile":
            change = {"colormap": rng.choice(["viridis", "magma"])}
        else:
            change = {"stroke": rng.choice(["#ff0000", "#00aa00", None])}
        prepare.turns[layer_id] = rng.choice([0, 1])
        store.restyle(layer_id, **change)
        return f"restyle {layer_id} {change}"
    return f"{kind} {layer_id}"


def served(widget: MapWidget, digest: str) -> bool:
    sent = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(widget, "send", lambda content, buffers=None: sent.append(content))
        widget._handle_custom_msg({"type": "pull", "digests": [digest]}, [])
    return bool(sent) and not sent[0].get("missing")


def check(widget: MapWidget, store: LayerStore, engine, theme: str) -> list[str]:
    """Return every way the published state differs from the store."""
    problems = []
    layers = widget.state["layers"]
    expected = [i for i in store.drawing_order() if engine.accepted(i) is not None]
    if [x["id"] for x in layers] != expected:
        problems.append(f"order {[x['id'] for x in layers]}, store wants {expected}")
    for layer_id in store.ids:
        pair = engine.accepted(layer_id)
        if pair is None or pair[0].render_hash != store.get(layer_id).render_hash:
            problems.append(f"{layer_id}: the engine draws an older spec")
        if store.view(layer_id).status != "ready":
            problems.append(f"{layer_id}: status {store.view(layer_id).status}")
    for x in layers:
        view = store.view(x["id"])
        if (x["visible"], x["opacity"]) != (view.visible, view.opacity):
            problems.append(f"{x['id']}: drawn {x['visible']}/{x['opacity']}, store {view}")
        if x["kind"] == "geojson" and not served(widget, x["source"]["digest"]):
            problems.append(f"{x['id']}: its payload is not served")
    if widget.state["theme"] != theme:
        problems.append(f"theme {widget.state['theme']}, configured {theme}")
    return problems


def report(seed: int, log: list[str], problems: list[str]) -> str:
    return f"seed {seed}\nops:\n  " + "\n  ".join(log) + "\nproblems:\n  " + "\n  ".join(problems)


@pytest.mark.asyncio
@pytest.mark.parametrize("seed", SEEDS)
async def test_random_ops(seed, monkeypatch):
    prepare = Prepare()
    monkeypatch.setattr(maplibre_engine, "prepare", prepare)
    rng, loop = random.Random(seed), asyncio.get_running_loop()
    widget, store = MapWidget(loop=loop), LayerStore()
    engine = maplibre_engine.MapLibreEngine(widget, store, loop=loop)
    theme, log, problems = ["light"], [], []
    try:
        for step in range(1, OPS_PER_SEED + 1):
            log.append(random_op(rng, store, engine, prepare, theme))
            if rng.random() < 0.3:
                await asyncio.sleep(0)
            if step % BURST:
                continue
            await engine.wait_idle()
            problems += [f"after op {step}: {p}" for p in check(widget, store, engine, theme[0])]
    finally:
        engine.close()
    assert not problems, report(seed, log, problems)
