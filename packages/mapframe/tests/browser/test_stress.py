"""Random fast operations on a live widget: every view converges to Python.

The ipyleaflet map this widget replaces drew a layer in the wrong place after
many fast operations. Here each operation is drawn at once, with no waiting,
and after each burst the owned style of every view's map, and of its compare
map in compare mode, must equal what the state contract derives from the
published state for that side (``expected_snapshot``, written without
translate.ts), with a foreign layer still on top.
"""

import json
import random

import ipywidgets as widgets
import pytest
from IPython.display import display
from playwright.sync_api import Error as PlaywrightError

from mapframe import (
    Basemap,
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    PMTilesSource,
    RasterSource,
    VectorPaint,
)

SEEDS = (11, 23, 37, 41, 59)
OPERATIONS = 48
BURST = 8

# Two GeoJSON layers, a raster and a PMTiles layer. The ids need escaping in
# owned style ids.
KINDS = {"geo:a": "geojson", "geo b": "geojson", "raster": "raster", "pm": "pmtiles"}
COLORS = ("#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00")
OPACITIES = (0.0, 0.25, 0.5, 1.0)
ZOOM_RANGES = ((0, None), (2, None), (0, 20))
RASTER_SETS = ("r1", "r2", "r3")
SIDES = ("left", "right", "both")
# How often each operation is picked when it applies. Order bugs need layers
# that stay in place while others move around them, so adds outweigh
# removals and moves come often.
WEIGHTS = {
    "add": 3,
    "remove": 1,
    "move": 4,
    "visibility": 1,
    "opacity": 1,
    "repaint": 1,
    "payload": 1,
    "token": 1,
    "tiles": 1,
    "theme": 1,
    "basemap": 1,
    "zone": 2,
    "compare_on": 1,
    "compare_off": 1,
    "side": 2,
}

# A foreign layer, as a drawing plugin would add one.
FOREIGN = "td-poly"
ADD_FOREIGN = """el => {
    const ring = [[-5, -5], [5, -5], [5, 5], [-5, 5], [-5, -5]];
    el.mapframeMap.addSource('td-poly', {type: 'geojson', data: {
        type: 'Feature', properties: {},
        geometry: {type: 'Polygon', coordinates: [ring]},
    }});
    el.mapframeMap.addLayer({id: 'td-poly', type: 'fill', source: 'td-poly',
        paint: {'fill-color': '#000000', 'fill-opacity': 0.2}});
}"""


class Scenario:
    """A user's layers under random operations; each step makes one change."""

    def __init__(self, seed, widget, tiles, pmtiles):
        """Start with no layer, no basemap and the light theme."""
        self.rng = random.Random(seed)
        self.widget = widget
        self.tiles = tiles
        self.pmtiles = pmtiles
        self.layers = []  # top-first, one dict per layer
        self.tokens = dict.fromkeys(KINDS, 0)
        self.theme = "light"
        self.basemaps = (
            None,
            Basemap((tiles.url("base-a"),), "© Base A"),
            # Same attribution as A, so a swap from A only changes the tiles.
            Basemap((tiles.url("base-b"),), "© Base A"),
            Basemap((tiles.url("base-c"),), "© Base C", max_zoom=17),
        )
        self.basemap = None
        self.compare = False
        self.payloads = {}  # digest -> bytes of every payload published
        self.count = 0

    def step(self):
        """Apply one random operation that applies now; describe it."""
        names = [name for name, ok in self._applicable().items() if ok]
        [name] = self.rng.choices(names, [WEIGHTS[name] for name in names])
        return getattr(self, f"_{name}")()

    def state(self):
        layers = []
        for spec in self.layers:
            if spec["kind"] == "geojson":
                digest = self.widget.add_payload(spec["payload"])
                self.payloads[digest] = spec["payload"]
                source = GeoJSONSource(digest)
            elif spec["kind"] == "raster":
                source = RasterSource(
                    (self.tiles.url(spec["tiles"]),),
                    max_native_zoom=spec["max_native_zoom"],
                    bounds=spec["bounds"],
                )
            else:
                source = PMTilesSource(self.pmtiles.url, "points")
            layers.append(
                Layer(
                    spec["id"],
                    source,
                    token=self.tokens[spec["id"]],
                    zone=spec["zone"],
                    side=spec["side"],
                    visible=spec["visible"],
                    opacity=spec["opacity"],
                    min_zoom=spec["min_zoom"],
                    max_zoom=spec["max_zoom"],
                    paint=spec["paint"],
                    attribution=spec["attribution"],
                )
            )
        return MapState(
            layers=tuple(layers), basemap=self.basemap, theme=self.theme, compare=self.compare
        )

    def _applicable(self):
        kinds = {spec["kind"] for spec in self.layers}
        return {
            "add": len(self.layers) < len(KINDS),
            "remove": bool(self.layers),
            "move": len(self.layers) > 1,
            "visibility": bool(self.layers),
            "opacity": bool(self.layers),
            "repaint": bool(kinds - {"raster"}),
            "payload": "geojson" in kinds,
            "token": bool(self.layers),
            "tiles": "raster" in kinds,
            "theme": True,
            "basemap": True,
            "zone": bool(self.layers),
            "compare_on": not self.compare,
            "compare_off": self.compare,
            "side": bool(self.layers),
        }

    def _pick(self, kinds=None):
        return self.rng.choice([s for s in self.layers if kinds is None or s["kind"] in kinds])

    def _payload_bytes(self):
        """A point, a line and a polygon at a random place, never repeated."""
        self.count += 1
        x = round(self.rng.uniform(-60, 55), 3)
        y = round(self.rng.uniform(-40, 35), 3)
        geometries = [
            {"type": "Point", "coordinates": [x, y]},
            {"type": "LineString", "coordinates": [[x, y], [x + 5, y + 3]]},
            {
                "type": "Polygon",
                "coordinates": [[[x, y], [x + 4, y], [x + 4, y + 4], [x, y + 4], [x, y]]],
            },
        ]
        features = [
            {"type": "Feature", "properties": {"n": self.count}, "geometry": g} for g in geometries
        ]
        return json.dumps({"type": "FeatureCollection", "features": features}).encode()

    def _random_paint(self):
        return VectorPaint(
            stroke=self.rng.choice(COLORS),
            fill=self.rng.choice((None, *COLORS)),
            fill_opacity=self.rng.choice(OPACITIES),
            width=self.rng.choice((1.0, 2.0, 3.5)),
            point_radius=self.rng.choice((3.0, 5.0, 8.0)),
        )

    def _add(self):
        present = {spec["id"] for spec in self.layers}
        layer_id = self.rng.choice(sorted(set(KINDS) - present))
        kind = KINDS[layer_id]
        min_zoom, max_zoom = self.rng.choice(ZOOM_RANGES)
        spec = {
            "id": layer_id,
            "kind": kind,
            "zone": self.rng.choice(("data", "overlay")),
            "side": self.rng.choice(SIDES),
            "visible": self.rng.random() < 0.8,
            "opacity": self.rng.choice((1.0, 0.5)),
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "attribution": self.rng.choice(("", f"© {layer_id}")),
            "paint": None if kind == "raster" else self._random_paint(),
        }
        if kind == "geojson":
            spec["payload"] = self._payload_bytes()
        elif kind == "raster":
            spec["tiles"] = self.rng.choice(RASTER_SETS)
            spec["max_native_zoom"] = self.rng.choice((None, 18))
            spec["bounds"] = self.rng.choice((None, (-60.0, -40.0, 60.0, 40.0)))
        index = self.rng.randint(0, len(self.layers))
        self.layers.insert(index, spec)
        return f"add {layer_id!r} at {index}"

    def _remove(self):
        spec = self._pick()
        self.layers.remove(spec)
        return f"remove {spec['id']!r}"

    def _move(self):
        spec = self._pick()
        start = self.layers.index(spec)
        self.layers.remove(spec)
        index = self.rng.choice([i for i in range(len(self.layers) + 1) if i != start])
        self.layers.insert(index, spec)
        return f"move {spec['id']!r} from {start} to {index}"

    def _visibility(self):
        spec = self._pick()
        spec["visible"] = not spec["visible"]
        return f"{'show' if spec['visible'] else 'hide'} {spec['id']!r}"

    def _opacity(self):
        spec = self._pick()
        spec["opacity"] = self.rng.choice([o for o in OPACITIES if o != spec["opacity"]])
        return f"opacity of {spec['id']!r} to {spec['opacity']}"

    def _repaint(self):
        spec = self._pick(("geojson", "pmtiles"))
        spec["paint"] = self._random_paint()
        return f"paint {spec['id']!r} {spec['paint']}"

    def _payload(self):
        spec = self._pick(("geojson",))
        spec["payload"] = self._payload_bytes()
        return f"new payload for {spec['id']!r} under token {self.tokens[spec['id']]}"

    def _token(self):
        spec = self._pick()
        self.tokens[spec["id"]] += 1
        return f"token of {spec['id']!r} to {self.tokens[spec['id']]}"

    def _tiles(self):
        spec = self._pick(("raster",))
        spec["tiles"] = self.rng.choice([t for t in RASTER_SETS if t != spec["tiles"]])
        return f"raster tiles to {spec['tiles']!r}"

    def _theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        return f"theme {self.theme}"

    def _basemap(self):
        self.basemap = self.rng.choice([b for b in self.basemaps if b != self.basemap])
        return f"basemap {None if self.basemap is None else self.basemap.tiles[0]}"

    def _zone(self):
        spec = self._pick()
        spec["zone"] = "overlay" if spec["zone"] == "data" else "data"
        return f"zone of {spec['id']!r} to {spec['zone']}"

    def _compare_on(self):
        self.compare = True
        return "compare on"

    def _compare_off(self):
        self.compare = False
        return "compare off"

    def _side(self):
        spec = self._pick()
        spec["side"] = self.rng.choice([s for s in SIDES if s != spec["side"]])
        return f"side of {spec['id']!r} to {spec['side']}"


def difference(view, expected):
    """What a view's snapshot has that the expected one does not, by key."""
    out = {}
    for key, want in expected.items():
        have = view[key]
        if have == want:
            continue
        if key == "layers" and [a["id"] for a in have] != [b["id"] for b in want]:
            out[key] = {
                "live ids": [a["id"] for a in have],
                "expected ids": [b["id"] for b in want],
            }
        elif key == "layers":
            out[key] = {
                "live": [a for a in have if a not in want],
                "expected": [b for b in want if b not in have],
            }
        else:
            out[key] = {"live": have, "expected": want}
    return out


@pytest.mark.parametrize("seed", SEEDS)
def test_random_operations_converge(
    seed,
    tiles,
    pmtiles,
    page_session,
    wait_settled,
    owned_snapshot,
    expected_snapshot,
    browser_errors,
):
    widget = MapWidget(center=(0, 0), zoom=2)
    widget.publish(MapState())
    # Boxes, so a second view can mount without remounting the first.
    first_box = widgets.VBox([widget])
    column = widgets.VBox([first_box])
    display(column)
    wait_settled(page_session, 1)
    first = page_session.locator(".mapframe-map").first.element_handle()
    first.evaluate(ADD_FOREIGN)
    first_id = first.evaluate("el => mapframeHarness.viewId(el)")
    scenario = Scenario(seed, widget, tiles, pmtiles)

    def fail(burst, why, live=None):
        """Report a burst that did not converge; ``live`` maps each side to its snapshots."""
        live = live or {}
        expected = {side: expected_snapshot(widget.state, scenario.payloads, side) for side in live}
        differs = {
            side: [difference(view, expected[side]) for view in views if view is not None]
            for side, views in live.items()
        }
        report = {
            "seed": seed,
            "burst": burst,
            "why": why,
            "differs": differs,
            "desired state": widget.state,
            "expected snapshot": expected,
            "live snapshot": live,
            "browser errors": browser_errors,
        }
        try:
            report["views"] = page_session.evaluate(
                "() => [...document.querySelectorAll('.mapframe-map')].map((el) => ({"
                " revision: el.dataset.mapframeRevision ?? null,"
                " order: el.mapframeMap?.getLayersOrder(),"
                " held: el.mapframeInspect?.(),"
                " right: el.mapframeCompare ? {"
                "  order: el.mapframeCompare.map.getLayersOrder(),"
                "  held: el.mapframeCompare.sync.inspect() } : null }))"
            )
        except PlaywrightError as error:
            report["views"] = str(error)
        pytest.fail(json.dumps(report, indent=1, default=str), pytrace=False)

    def check(burst, views=1):
        try:
            wait_settled(page_session, widget.state["revision"], views)
            live = {side: owned_snapshot(page_session, side) for side in ("main", "right")}
        except PlaywrightError as error:
            fail(burst, f"never settled: {error.message}")
        if len(live["main"]) != views:
            fail(burst, f"{len(live['main'])} live snapshots for {views} views", live)
        # Each map holds its side's layers in store order; no right map outside compare.
        for side, snapshots in live.items():
            if side == "right" and not widget.state["compare"]:
                expected = None
            else:
                expected = expected_snapshot(widget.state, scenario.payloads, side)
            if any(view != expected for view in snapshots):
                fail(burst, f"a {side} map differs from the desired state", live)
        order = first.evaluate("el => el.mapframeMap.getLayersOrder()")
        if not order or order[-1] != FOREIGN:
            fail(burst, f"{FOREIGN} is not on top: {order}", live)

    for _ in range(OPERATIONS // BURST):
        burst = []
        for _ in range(BURST):
            burst.append(scenario.step())
            widget.publish(scenario.state())
        check(burst)

    # A second view of the same widget shows the same state, without the
    # foreign layer the plugin added to the first view's map only.
    opened = []
    widget.on_msg(
        lambda _, content, __: (
            opened.append(content["view_id"]) if content.get("type") == "view_open" else None
        )
    )
    column.children = (first_box, widgets.VBox([widget]))
    check(["display a second view"], views=2)
    kept, second = page_session.locator(".mapframe-map").element_handles()
    assert kept.evaluate("el => mapframeHarness.viewId(el)") == first_id
    second_id = second.evaluate("el => mapframeHarness.viewId(el)")
    assert second_id != first_id
    assert second_id in opened
    assert FOREIGN not in second.evaluate("el => el.mapframeMap.getLayersOrder()")
    assert browser_errors == []
