"""Manual test for the bug that started pysepal-map.

The ipyleaflet map drew a layer in the wrong place after many fast operations.
"Random burst" fires 8 operations back to back, each drawn at once. When the
burst is done, the map must show the layers in the order listed on the right.

Everything is local: GeoJSON payloads, a solid-colour raster tile and solid
basemaps are generated here, so the page works offline.

    solara run packages/pysepal-map/examples/random_ops.py --port 8921
"""

import base64
import json
import random
import struct
import zlib

import solara
from pysepal_map import (
    Basemap,
    GeoJSONSource,
    Layer,
    MapState,
    MapWidget,
    RasterSource,
    VectorPaint,
)

BURST = 8
COLORS = ("#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00")
GEOJSON_IDS = ("A", "B", "C", "D")
IDS = (*GEOJSON_IDS, "tint")


def solid_tile(rgb, size=256):
    """A data URL of a one-colour PNG."""

    def chunk(kind, body):
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


BASEMAPS = (
    None,
    Basemap((solid_tile((225, 225, 225)),), "gray"),
    Basemap((solid_tile((236, 224, 190)),), "sand"),
)
TINT = RasterSource((solid_tile((255, 0, 128)),))


def shapes(index):
    """A polygon, a line and a point around a spot that differs per layer."""
    x, y = -30 + 20 * index, -10 + 6 * index
    ring = [[x, y], [x + 14, y], [x + 14, y + 14], [x, y + 14], [x, y]]
    geometries = [
        {"type": "Polygon", "coordinates": [ring]},
        {"type": "LineString", "coordinates": [[x - 4, y + 2], [x + 18, y + 12]]},
        {"type": "Point", "coordinates": [x + 7, y + 7]},
    ]
    features = [{"type": "Feature", "properties": {}, "geometry": g} for g in geometries]
    return json.dumps({"type": "FeatureCollection", "features": features}).encode()


class Model:
    """What the user wants on the map; ``draw`` publishes it."""

    def __init__(self, widget):
        """Draw the four GeoJSON layers on the gray basemap."""
        self.widget = widget
        self.rng = random.Random()
        self.theme = "light"
        self.basemap = BASEMAPS[1]
        self.digests = {i: widget.add_payload(shapes(n)) for n, i in enumerate(GEOJSON_IDS)}
        self.layers = [self.new(i, COLORS[n]) for n, i in enumerate(GEOJSON_IDS)]  # top-first
        self.draw()

    def new(self, layer_id, color=None):
        """A layer spec, shown at full opacity but for the translucent tint."""
        return {
            "id": layer_id,
            "visible": True,
            "opacity": 0.3 if layer_id == "tint" else 1.0,
            "zone": "overlay" if layer_id == "D" else "data",
            "color": color or self.rng.choice(COLORS),
        }

    def state(self):
        """The ``MapState`` the specs describe."""
        layers = []
        for spec in self.layers:
            if spec["id"] == "tint":
                source, paint = TINT, None
            else:
                source = GeoJSONSource(self.digests[spec["id"]])
                paint = VectorPaint(
                    stroke=spec["color"],
                    fill=spec["color"],
                    fill_opacity=0.35,
                    width=3.0,
                    point_radius=7.0,
                )
            layers.append(
                Layer(
                    spec["id"],
                    source,
                    visible=spec["visible"],
                    opacity=spec["opacity"],
                    zone=spec["zone"],
                    paint=paint,
                )
            )
        return MapState(layers=tuple(layers), basemap=self.basemap, theme=self.theme)

    def draw(self):
        """Publish the wanted state at once."""
        self.widget.publish(self.state())

    def drawn_order(self):
        """The layers top-first as they draw: the overlay zone above the data zone."""
        return [s for z in ("overlay", "data") for s in self.layers if s["zone"] == z]

    def operation(self):
        """Apply one random operation to the wanted state; name it."""
        rng, layers = self.rng, self.layers
        choices = ["theme", "basemap"]
        if len(layers) < len(IDS):
            choices += ["add"] * 2
        if layers:
            choices += ["remove", "visibility", "opacity", "paint"]
        if len(layers) > 1:
            choices += ["move"] * 3
        name = rng.choice(choices)
        if name == "add":
            layer_id = rng.choice([i for i in IDS if i not in {s["id"] for s in layers}])
            layers.insert(rng.randint(0, len(layers)), self.new(layer_id))
        elif name == "theme":
            self.theme = "dark" if self.theme == "light" else "light"
        elif name == "basemap":
            self.basemap = rng.choice([b for b in BASEMAPS if b != self.basemap])
        else:
            spec = rng.choice(layers)
            if name == "remove":
                layers.remove(spec)
            elif name == "move":
                layers.remove(spec)
                layers.insert(rng.randint(0, len(layers)), spec)
            elif name == "visibility":
                spec["visible"] = not spec["visible"]
            elif name == "opacity":
                spec["opacity"] = rng.choice([o for o in (0.25, 0.5, 1.0) if o != spec["opacity"]])
            else:
                spec["color"] = rng.choice([c for c in COLORS if c != spec["color"]])
        return name

    def burst(self):
        """Fire ``BURST`` operations, drawing after each without waiting."""
        done = []
        for _ in range(BURST):
            done.append(self.operation())
            self.draw()
        return done


@solara.component
def Page():
    """The map, the three buttons and Python's view of the layers."""
    widget = solara.use_memo(lambda: MapWidget(center=(0, 5), zoom=2, height="520px"), [])
    model = solara.use_memo(lambda: Model(widget), [])
    _, set_tick = solara.use_state(0)
    view_key, set_view_key = solara.use_state(0)
    last, set_last = solara.use_state("")

    def refresh(*_):
        set_tick(lambda n: n + 1)

    def watch():
        widget.on_status(refresh)
        return lambda: widget.on_status(refresh, remove=True)

    solara.use_effect(watch, [])

    def burst():
        set_last(", ".join(model.burst()))
        refresh()

    def toggle_theme():
        model.theme = "dark" if model.theme == "light" else "light"
        model.draw()
        refresh()

    status = widget.layer_status
    basemap = "none" if model.basemap is None else model.basemap.attribution
    with solara.Row(style={"padding": "12px", "gap": "16px", "align-items": "flex-start"}):
        with solara.Column(style={"flex": "1 1 60%"}):
            with solara.Row():
                solara.Button("Random burst", on_click=burst, classes=["burst"])
                solara.Button("Theme", on_click=toggle_theme, classes=["theme"])
                solara.Button(
                    "Redisplay",
                    on_click=lambda: set_view_key(lambda n: n + 1),
                    classes=["redisplay"],
                )
            with solara.Column().key(f"view-{view_key}"):
                solara.display(widget)
        with solara.Column(style={"flex": "1 1 40%"}):
            solara.Text(f"revision {widget.state['revision']}", classes=["py-revision"])
            solara.Text(f"theme {model.theme}, basemap {basemap}")
            solara.Text(f"last burst: {last or 'none yet'}", classes=["py-last"])
            solara.Text("Layers, top first: id, zone, visibility, opacity, status")
            for spec in model.drawn_order():
                current = status.get(spec["id"])
                text = f"{spec['id']} {spec['zone']} {'shown' if spec['visible'] else 'hidden'}"
                text += f" {spec['opacity']} {current.status if current else 'pending'}"
                solara.Text(text, classes=["py-layer"])
