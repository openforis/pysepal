"""Browser test fixtures: a Solara page with the pysepal-map probes.

Also local raster tiles and a PMTiles file served through Playwright routes,
and the owned-style snapshots the convergence tests compare: what each view's
map holds, and what the state contract derives from the published state.
"""

import functools
import json
import os
import re
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

import pytest
from solara.test import pytest_plugin as ipywidgets_plugin

# The generic widget has no Vuetify to warm up.
os.environ.setdefault("SOLARA_TEST_VUETIFY_WARMUP", "false")

HARNESS = Path(__file__).parent / ".build" / "harness.js"

#: The points of data/points.pmtiles, in its layer "points": feature id to
#: (lng, lat). Built once, from the package directory, with:
#:
#:   echo '{"type":"FeatureCollection","features":[
#:     {"type":"Feature","id":1,"properties":{"name":"west"},
#:      "geometry":{"type":"Point","coordinates":[-20,-10]}},
#:     {"type":"Feature","id":2,"properties":{"name":"north"},
#:      "geometry":{"type":"Point","coordinates":[0,15]}},
#:     {"type":"Feature","id":3,"properties":{"name":"east"},
#:      "geometry":{"type":"Point","coordinates":[25,-5]}}]}' \
#:   | micromamba run -n pysepal tippecanoe -o tests/browser/data/points.pmtiles \
#:       --force -l points -Z 0 -z 6 -r1
PMTILES_POINTS = {1: (-20.0, -10.0), 2: (0.0, 15.0), 3: (25.0, -5.0)}
PMTILES_FILE = Path(__file__).parent / "data" / "points.pmtiles"

# The roots of the views that are mounted now.
MOUNTED = "[...document.querySelectorAll('.psm-map')].filter((el) => el.psmMap)"

# What encodeURIComponent leaves unescaped besides letters and digits.
URI_COMPONENT_SAFE = "-_.!~*'()"


def load_harness(page):
    """Add the probes of harness.ts to the page now open, as ``psmHarness``."""
    if not HARNESS.exists():
        pytest.fail(f"{HARNESS} is missing: run `npm run build:harness`")
    page.add_script_tag(path=HARNESS)


@pytest.fixture
def harness(solara_test, page_session):
    """The test page with the probes of harness.ts loaded as ``psmHarness``."""
    load_harness(page_session)
    return page_session


def wait_settled(page, revision, expected_views=1):
    """Wait for exactly ``expected_views`` mounted views, each at ``revision``.

    The revision marker covers the owned style and the GeoJSON worker loads,
    not pixels: tests of rendered features or colours wait for those too.
    """
    page.wait_for_function(f"n => {MOUNTED}.length === n", arg=expected_views)
    page.wait_for_function(
        f"""([n, r]) => {{
            const roots = {MOUNTED};
            return roots.length === n
                && roots.every((el) => el.dataset.psmRevision === r);
        }}""",
        arg=[expected_views, str(revision)],
    )


def owned_snapshot(page, side="main"):
    """What one map of each mounted view holds of the owned style, in DOM order.

    Per view: the owned layers bottom-first in live order (id, type, source,
    source layer, visibility, paint, zoom range), the owned sources by id as
    set (tiles and attribution included, GeoJSON data apart), the
    coordinates of each GeoJSON source's features in its worker, and the
    theme. ``side="right"`` reads the compare map, ``None`` for a view
    without one.
    """
    return page.evaluate(
        f"""side => Promise.all({MOUNTED}.map((el) =>
            side === 'right' && !el.psmCompare ? null : psmHarness.ownedSnapshot(el, side)))""",
        side,
    )


def for_side(state, side):
    """The published ``state`` with only the layers one map of a view draws.

    From the contract: outside compare ``main`` draws every layer and ``right``
    none; in compare ``main`` draws the ``left`` and ``both`` layers and
    ``right`` the ``right`` and ``both`` ones.
    """
    if not state["compare"]:
        layers = state["layers"] if side == "main" else []
    else:
        drawn = {"main": ("left", "both"), "right": ("right", "both")}[side]
        layers = [layer for layer in state["layers"] if layer["side"] in drawn]
    return {**state, "layers": layers}


def _owned_id(layer):
    encoded = quote(layer["id"], safe=URI_COMPONENT_SAFE)
    return f"psm:{encoded}:{layer['instance']}"


def _source_spec(layer):
    source = layer["source"]
    if layer["kind"] == "geojson":
        spec = {"type": "geojson", "generateId": True}
    elif layer["kind"] == "pmtiles":
        spec = {"type": "vector", "url": f"pmtiles://{source['url']}"}
    else:
        spec = {"type": "raster", "tiles": source["tiles"]}
        spec["tileSize"] = source["tile_size"]
        if source["bounds"] is not None:
            spec["bounds"] = source["bounds"]
        if source["max_native_zoom"] is not None:
            spec["maxzoom"] = source["max_native_zoom"]
    if layer["attribution"]:
        spec["attribution"] = layer["attribution"]
    return spec


def _by_class(paint, default):
    """A part's colour: a ``match`` on ``color_by`` falling back to ``default``, if set."""
    if paint["color_by"] is None:
        return default
    branches = [item for pair in paint["class_colors"] for item in pair]
    return ["match", ["get", paint["color_by"]], *branches, default]


def _paints(layer):
    """Each part's paint, bottom-first, as the vector paint rule defines it."""
    opacity = layer["opacity"]
    if layer["kind"] == "raster":
        return [("raster", {"raster-opacity": opacity})]
    paint = layer["paint"]
    fill = paint["fill"] if paint["fill"] is not None else paint["stroke"]
    fill_opacity = paint["fill_opacity"] * opacity
    return [
        ("fill", {"fill-color": _by_class(paint, fill), "fill-opacity": fill_opacity}),
        (
            "line",
            {
                "line-color": _by_class(paint, paint["stroke"]),
                "line-width": paint["width"],
                "line-opacity": opacity,
            },
        ),
        (
            "circle",
            {
                "circle-radius": paint["point_radius"],
                "circle-color": _by_class(paint, fill),
                "circle-opacity": fill_opacity,
                "circle-stroke-color": paint["stroke"],
                "circle-stroke-width": paint["width"],
                "circle-stroke-opacity": opacity,
            },
        ),
    ]


def expected_snapshot(state, payloads, side="main"):
    """The ``owned_snapshot`` of one map of a view showing a published ``state``.

    Derived from the state contract in the plan, not from translate.ts.
    ``payloads`` maps each digest to its GeoJSON bytes.
    """
    state = for_side(state, side)
    layers, sources, coordinates = [], {}, {}
    basemap = state["basemap"]
    if basemap is not None:
        spec = {"type": "raster", "tiles": basemap["tiles"], "tileSize": 256}
        if basemap["attribution"]:
            spec["attribution"] = basemap["attribution"]
        if basemap["max_zoom"] is not None:
            spec["maxzoom"] = basemap["max_zoom"]
        sources["psm:basemap"] = spec
        layers.append(
            {
                "id": "psm:basemap",
                "type": "raster",
                "source": "psm:basemap",
                "source_layer": None,
                "visibility": "visible",
                "paint": {},
                "min_zoom": 0,
                "max_zoom": None,
            }
        )
    # Top-first in the state; the overlay zone draws above the data zone.
    bottom_first = state["layers"][::-1]
    ordered = [layer for layer in bottom_first if layer["zone"] == "data"]
    ordered += [layer for layer in bottom_first if layer["zone"] == "overlay"]
    for layer in ordered:
        source_id = _owned_id(layer)
        sources[source_id] = _source_spec(layer)
        if layer["kind"] == "geojson":
            data = json.loads(payloads[layer["source"]["digest"]])
            coordinates[source_id] = [
                feature["geometry"]["coordinates"] for feature in data["features"]
            ]
        source_layer = layer["source"]["source_layer"] if layer["kind"] == "pmtiles" else None
        for part, paint in _paints(layer):
            layers.append(
                {
                    "id": f"{source_id}:{part}",
                    "type": part,
                    "source": source_id,
                    "source_layer": source_layer,
                    "visibility": "visible" if layer["visible"] else "none",
                    "paint": paint,
                    "min_zoom": layer["min_zoom"],
                    "max_zoom": layer["max_zoom"],
                }
            )
    return {
        "layers": layers,
        "sources": sources,
        "coordinates": coordinates,
        "theme": state["theme"],
    }


@pytest.fixture(name="wait_settled")
def wait_settled_fixture():
    """``wait_settled(page, revision, expected_views=1)``."""
    return wait_settled


@pytest.fixture(name="owned_snapshot")
def owned_snapshot_fixture():
    """``owned_snapshot(page, side="main") -> list[dict | None]``."""
    return owned_snapshot


@pytest.fixture(name="expected_snapshot")
def expected_snapshot_fixture():
    """``expected_snapshot(state, payloads, side="main") -> dict``."""
    return expected_snapshot


@pytest.fixture(name="load_harness")
def load_harness_fixture():
    """``load_harness(page)``, for pages a runner opened."""
    return load_harness


def _jupyter_lab_runner(jupyter_server, notebook_path, page):
    """pytest-ipywidgets' JupyterLab runner, for the toolbar of JupyterLab 4.6.

    pytest-ipywidgets 1.66 waits for a ``runmenu:run`` toolbar button, which
    JupyterLab 4.6 names ``notebook:run-cell-and-select-next``.
    """
    count = 0

    def run(f, locals=None):
        nonlocal count
        cwd = str(Path(f.__code__.co_filename).parent)
        setup = f"import os\nos.chdir({cwd!r})\n"
        for name, value in (locals or {}).items():
            setup += f"{name} = {value!r}\n"
        ipywidgets_plugin.write_notebook(
            [setup, ipywidgets_plugin.code_from_function(f)], notebook_path
        )
        page.goto(
            f"{jupyter_server.base_url}/lab/workspaces/solara-test/tree/notebook.ipynb"
            f"?reset&v={count}"
        )
        button = page.locator('[data-command="notebook:run-cell-and-select-next"]')
        button.wait_for()
        page.locator('button:has-text("No Kernel")').wait_for(state="detached")
        page.locator('[data-status="idle"]').wait_for()
        # The setup cell, then the function's.
        button.click()
        button.click()
        count += 1

    return run


@pytest.fixture(params=ipywidgets_plugin.runners)
def ipywidgets_runner(
    solara_server,
    solara_app,
    voila_server,
    jupyter_server,
    notebook_path,
    page_session,
    request,
    pytestconfig,
):
    """pytest-ipywidgets' ``ipywidgets_runner``, with a JupyterLab 4.6 runner.

    A test that names its runner skips when SOLARA_TEST_RUNNERS leaves it out,
    since its server is then never started.
    """
    # pytest-ipywidgets 1.66.3 runs cells with a JupyterLab command that 4.6
    # renamed to `notebook:run-cell-and-select-next`. Drop this override once
    # upstream supports it.
    runner = request.param
    if runner not in ipywidgets_plugin.runners:
        pytest.skip(f"SOLARA_TEST_RUNNERS does not include {runner}")
    warmup = pytestconfig.getoption("solara_vuetify_warmup")
    if runner == "solara":
        with ipywidgets_plugin.create_runner_solara(
            solara_server, solara_app, page_session, warmup
        ) as run:
            yield run
    elif runner == "voila":
        yield ipywidgets_plugin.create_runner_voila(
            voila_server, notebook_path, page_session, warmup
        )
    elif runner == "jupyter_lab":
        yield _jupyter_lab_runner(jupyter_server, notebook_path, page_session)
    elif runner == "jupyter_notebook":
        yield ipywidgets_plugin.create_runner_jupyter_notebook(
            jupyter_server, notebook_path, page_session, warmup
        )
    else:
        raise RuntimeError(f"Unknown runner {runner}")


@pytest.fixture
def browser_errors(page_session):
    """The errors the page logs or throws during the test."""
    errors = []

    def on_console(message):
        if message.type == "error":
            errors.append(message.text)

    def on_error(error):
        errors.append(str(error))

    page_session.on("console", on_console)
    page_session.on("pageerror", on_error)
    yield errors
    page_session.remove_listener("console", on_console)
    page_session.remove_listener("pageerror", on_error)


@functools.cache
def png(rgb, size=256):
    """A one-colour PNG."""

    def chunk(kind, body):
        crc = zlib.crc32(kind + body)
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    rows = b"".join(b"\x00" + bytes(rgb) * size for _ in range(size))
    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


GREEN = (0, 160, 0)


@dataclass
class Tiles:
    """Raster tile sets on the page's own origin, answered by a Playwright route.

    Every tile is a green PNG, or of the colour ``color`` gives its set. In a
    set marked with ``fail_one``, the first tile it is asked for answers 500,
    and so does every retry of it; in one marked with ``fail_all``, every tile.
    ``failed`` holds the first failed tile of each set.
    """

    PREFIX: ClassVar[str] = "/psm-test-tiles/"

    origin: str
    colors: dict = field(default_factory=dict)
    failing: set = field(default_factory=set)
    failing_all: set = field(default_factory=set)
    failed: dict = field(default_factory=dict)
    served: list = field(default_factory=list)

    def url(self, name):
        return f"{self.origin}{self.PREFIX}{name}/{{z}}/{{x}}/{{y}}.png"

    def color(self, name, rgb):
        self.colors[name] = tuple(rgb)

    def fail_one(self, name):
        self.failing.add(name)

    def fail_all(self, name):
        self.failing_all.add(name)

    def zooms(self, name):
        """The zoom of each tile of a set served so far."""
        prefix = f"{self.origin}{self.PREFIX}{name}/"
        return [
            int(url[len(prefix) :].split("/", 1)[0])
            for url in self.served
            if url.startswith(prefix)
        ]

    def handle(self, route):
        url = route.request.url
        name = url.split(self.PREFIX, 1)[1].split("/", 1)[0]
        one = name in self.failing and self.failed.setdefault(name, url) == url
        if one or name in self.failing_all:
            self.failed.setdefault(name, url)
            route.fulfill(status=500, body="deliberate failure")
        else:
            self.served.append(url)
            body = png(self.colors.get(name, GREEN))
            route.fulfill(status=200, content_type="image/png", body=body)


@pytest.fixture
def tiles(harness, page_session):
    """Local raster tiles for the test page; see ``Tiles``."""
    server = Tiles(page_session.evaluate("location.origin"))
    pattern = f"{server.origin}{Tiles.PREFIX}**"
    page_session.route(pattern, server.handle)
    yield server
    page_session.unroute(pattern, server.handle)


@dataclass
class PMTiles:
    """data/points.pmtiles on the page's own origin, served by byte range.

    ``points`` maps each feature id to its coordinates; ``ranges`` records
    each range asked for, as ``(start, end)`` inclusive.
    """

    PATH: ClassVar[str] = "/psm-test-data/points.pmtiles"
    points: ClassVar[dict] = PMTILES_POINTS

    origin: str
    ranges: list = field(default_factory=list)

    @property
    def url(self):
        return f"{self.origin}{self.PATH}"

    @property
    def bounds(self):
        lngs = [lng for lng, _ in self.points.values()]
        lats = [lat for _, lat in self.points.values()]
        return (min(lngs), min(lats), max(lngs), max(lats))

    def handle(self, route):
        data = PMTILES_FILE.read_bytes()
        size = len(data)
        asked = route.request.headers.get("range")
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", asked or "")
        if match is None:
            route.fulfill(status=200, body=data, content_type="application/octet-stream")
            return
        start = int(match[1])
        end = min(int(match[2]) if match[2] else size - 1, size - 1)
        if start >= size:
            route.fulfill(status=416, headers={"Content-Range": f"bytes */{size}"})
            return
        self.ranges.append((start, end))
        route.fulfill(
            status=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
            },
            content_type="application/octet-stream",
            body=data[start : end + 1],
        )


@pytest.fixture
def pmtiles(harness, page_session):
    """data/points.pmtiles for the test page; see ``PMTiles``."""
    server = PMTiles(page_session.evaluate("location.origin"))
    page_session.route(server.url, server.handle)
    yield server
    page_session.unroute(server.url, server.handle)
