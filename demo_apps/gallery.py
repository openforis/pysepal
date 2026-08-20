"""Landing page for the pysepal demos: one Solara server, one route per app.

Every demo keeps its entrypoint at ``app.py`` so it stays runnable on its own,
which means a plain ``import app`` would resolve to whichever demo was imported
first. Loading by path under the demo's own name avoids that collision, and
putting the demo's directory on ``sys.path`` is what lets ``from component...``
inside it resolve exactly as it does when Solara runs the demo directly.

To run:

```bash
pysepal$ ./run_solara.sh demo_apps/gallery.py --port 8901
```
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import solara

DEMO_ROOT = Path(__file__).resolve().parent

#: ``(directory, url path, label, blurb)`` -- drives both the routes and the landing page.
DEMOS = [
    (
        "solara_map_app",
        "map-app",
        "Map App",
        "What a real SEPAL module needs: AOI selection, async processing with "
        "progress notifications, layer management, a floating legend driven by the "
        "layers on the map, and Earth Engine / Drive / SEPAL exports. It "
        "authenticates against SEPAL, so it needs credentials in `.env`.",
    ),
    (
        "solara_aoi_app",
        "aoi-app",
        "AOI Save & Restore",
        "Persisting an area of interest and getting it back. `AoiView` carries the "
        "computed `AoiResult` on `value` and the small JSON `AoiSpec` on `spec`; the "
        "demo saves only the spec, and rebuilds the geometry on load. No Earth "
        "Engine and no credentials -- admin boundaries come from FAO's WFS service.",
    ),
    (
        "solara_raster_app",
        "raster-app",
        "Raster App",
        "Local raster rendering: a continuous colormap, exact per-class colors, and "
        "a raster large enough that preparing it has to happen off the event loop. "
        "No session and no credentials -- it draws generated stand-ins unless "
        "`PYSEPAL_DEMO_RASTER_DIR` points at real class maps.",
    ),
    (
        "solara_vector_app",
        "vector-app",
        "Vector App",
        "Local vector tiling with `vectortileserver`: one PMTiles archive drawn "
        "with a single symbol and with a color per attribute value. Needs "
        "tippecanoe on PATH; it tiles a generated grid unless "
        "`PYSEPAL_DEMO_VECTOR_DIR` points at a real `landcover.geojson`.",
    ),
]


def load_demo(name: str) -> ModuleType:
    """Return ``<name>/app.py`` imported under the module name ``<name>``."""
    directory = DEMO_ROOT / name
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

    spec = importlib.util.spec_from_file_location(name, directory / "app.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"no app.py to load in {directory}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@solara.component
def Layout(children=[]):
    """Hand a demo the whole viewport; keep Solara's chrome for the landing page.

    Each demo is a ``MapApp``, a full-screen Vuetify app with its own bar and
    drawer. Nested inside Solara's ``AppLayout`` it renders against the outer
    app's offsets and comes out squeezed, so only the landing page is wrapped.
    """
    # ``use_router().path``, not ``use_route()``: the latter consumes the route
    # level that AppLayout needs to build its navigation.
    if solara.use_router().path == "/":
        solara.AppLayout(children=children, title="pysepal demos")
    else:
        solara.Column(children=children, gap="0px", margin=0, style={"height": "100vh"})


@solara.component
def Home():
    """The gallery itself: what each demo shows and a link into it."""
    with solara.Column(style={"max-width": "50em", "padding": "2em"}):
        solara.Markdown("# pysepal demos")
        solara.Markdown(
            "Apps built on pysepal, each runnable on its own or from here. "
            "The same components serve Voila -- see `demo_apps/README.md`."
        )
        for _, path, label, blurb in DEMOS:
            with solara.Card(title=label):
                solara.Markdown(blurb)
                solara.Button(
                    f"open {label}", href=f"/{path}", text=True, icon_name="mdi-open-in-app"
                )


# The layout has to ride on the "/" route: solara only picks up a module-level
# ``Layout`` when it generates the routes itself, not when the script declares them.
routes = [
    solara.Route(path="/", component=Home, label="Demos", layout=Layout),
    *[
        solara.Route(path=path, component=load_demo(name).Page, label=label)
        for name, path, label, _ in DEMOS
    ],
]
