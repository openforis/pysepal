# mapframe

A MapLibre GL JS map widget for Jupyter, Voila and Solara, built with [anywidget](https://anywidget.dev). Python declares the whole map state, and every view in the browser reconciles its map to that state.

It depends only on `anywidget` and `traitlets`: no Earth Engine, Solara or ipyleaflet. It was built for [pysepal](https://github.com/openforis/pysepal), the toolkit for [SEPAL](https://sepal.io) apps, but it knows nothing about SEPAL and works in any notebook.

## Install

```bash
pip install mapframe
```

It imports as `mapframe` and needs Python 3.10 or later. The wheel carries the built JavaScript, so installing it needs no Node.

## Example

```python
import json

from IPython.display import display
from mapframe import Basemap, GeoJSONSource, Interaction, Layer, MapState, MapWidget, VectorPaint

cities = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Rome"},
            "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
        },
    ],
}
osm = Basemap(("https://tile.openstreetmap.org/{z}/{x}/{y}.png",), "© OpenStreetMap contributors")

widget = MapWidget(center=(12.5, 41.9), zoom=4)  # center is (lng, lat)
digest = widget.add_payload(json.dumps(cities).encode())
layer = Layer(
    "cities",
    GeoJSONSource(digest),
    paint=VectorPaint(marker="pin"),
    interaction=Interaction(popup=()),  # a click shows every property
)
widget.publish(MapState(layers=(layer,), basemap=osm))

clicks = []
widget.on_click(clicks.append)  # each click adds a ClickEvent with the features under it
display(widget)
```

To change the map, publish a whole new `MapState`. Every view then updates its map to match it.

## Why this package

mapframe replaces the ipyleaflet map that pysepal used. We built our own widget for these reasons.

**The browser could drift from Python.** With ipyleaflet, Python drove the browser with a stream of small commands: detach a layer, move it to another pane, attach it again. Nothing ever checked the browser against Python. In manual testing, a layer ended up drawn in the wrong place after many fast operations, and only a page refresh fixed it. A random test of the Python side alone never reproduced it, which pointed at the browser. mapframe works the other way. Python declares the whole map state, and the browser reconciles the live map to it. So any new view of a live widget (a remount, a re-display, a JupyterLab reload with the kernel alive) shows exactly the Python state.

**PMTiles were hard to use.** ipyleaflet's `PMTilesLayer` extends `Layer` rather than `RasterLayer`, so it has no `visible` or `opacity`. Its frontend repaints only when the URL changes. A wrong `source-layer` renders nothing, with no error.

**MapLibre GL JS fits what SEPAL apps show.** It draws with WebGL and handles vector tiles, PMTiles and a style spec, with smooth animated camera moves. It works with [Terra Draw](https://github.com/JamesLMilner/terra-draw) for drawing, and a second map clipped by a divider gives a swipe compare view.

**It had to fit SEPAL.** The map must run under `solara run`, Voila and plain Jupyter. It must load no JavaScript from a CDN at runtime, so everything is bundled in the wheel. On SEPAL, local raster tiles reach the browser through a proxy, so tile URLs stay plain strings that the app sets.

We also looked at other libraries. They are good projects with other goals:

- **anymap-ts** (opengeos) is active and feature-rich. Its sync replays an ever-growing list of method calls in the browser, plus some side state: the command-stream pattern we wanted to leave. Most of its work also rests on one maintainer.
- **py-maplibregl** (`maplibre` on PyPI) sends one-off messages and keeps no map state in Python. It has had no release since December 2025, and its drawing uses MapboxDraw, while we wanted Terra Draw.
- **leafmap** offers one API over several map backends. Its MapLibre map extends py-maplibregl's `MapWidget` and its default map extends ipyleaflet's `Map`, so it shares their sync models.
- **folium** writes a Leaflet map to an HTML page, which a notebook shows as is. It has no channel back to Python, so clicks and drawings never reach the kernel, and by default it loads Leaflet and its other scripts from CDNs.
- **lonboard** binds deck.gl to draw large datasets fast on the GPU, from GeoArrow and GeoParquet. SEPAL apps mostly show raster tiles and a few vector layers, and deck.gl layers were out of scope for us.

## What it owns

- **Python owns the persistent map state**: layers and their order, basemap, theme, controls (zoom, fullscreen, a metric scale, a coordinates readout), the cursor and a highlight marker. `MapWidget.publish(MapState)` publishes a whole snapshot, and every mounted view reconciles its map to it. Python never sends a one-off command that changes the map.
- **Tile URLs** are XYZ templates. A Leaflet-style `{s}` in a `RasterSource` or `Basemap` URL expands to the subdomains a, b and c, and `{r}` is dropped; `tile_urls(template, subdomains)` expands one for a provider with other subdomains. `Basemap.from_xyz(provider)` builds a basemap from an [xyzservices](https://github.com/geopandas/xyzservices) `TileProvider`, and raises `ValueError` for one MapLibre cannot draw: a TMS provider, or a URL with a placeholder left unfilled, such as a missing API key.
- **The browser owns the camera** and reports it back (`on_view`); Python can ask for a move with `set_center` and `fit_bounds`, which takes a `padding` in px and a `max_zoom` cap. Both jump, or fly there with `animate=True`; a view reports a flight when it ends, and jumps when the user's system asks for reduced motion.
- **Clicks** reach Python as `ClickEvent`s (`on_click`) with the features under the point, or within 3 px of it when none is under it, so thin lines and small points can be hit, from current layer instances only. Tooltips, popups and the pointer cursor use the same rule. A click on a cluster zooms into it and sends no event. There are no hover events.
- **Popups and tooltips** come from a layer's `Interaction(popup=..., tooltip=...)`: `()` shows every property, a tuple names the ones to show, a mapping of name to label shows them under those labels, `None` turns it off. A click opens a popup with a table of properties, and the pointer shows a tooltip. Values are inserted as text. Neither works on raster layers.
- **Pins and clusters**: `VectorPaint(marker="pin")` draws points as pins, and a `GeoJSONSource` with `Cluster(radius, max_zoom)` groups its points into count bubbles. A clustered source holds only points. A property `cluster` that is true is reserved on it. `publish` raises `ValueError` otherwise, and `check_clusterable(geojson)` runs the same check on data before it reaches the map. The pins are drawn in the browser and the counts as text with local glyphs, so nothing is fetched.
- **Colours by class**: `VectorPaint(color_by="status", class_colors={"open": "#ff0000", "closed": "#00ff00"})` colours one layer's features, pins included, by the value of a property. Values are all strings or all integers and are compared as they are, so `"1"` is not `1`; any other value, a null or a missing property keeps the paint's own colour.
- **The cursor and a marker**: `widget.cursor` sets the pointer (`""`, `"crosshair"`, `"pointer"` or `"wait"`), and `set_marker(lng, lat)` and `clear_marker()` show one highlight marker. `Controls(coordinates=True)` shows the pointer's coordinates, and `Controls(globe=True)` a button that turns the map into a globe and back. `widget.projection` is the projection every view draws, `"mercator"` or `"globe"`, a view shown later included: `set_projection` sets it, and so does a click on the globe button in any view.
- **Drawing** uses the bundled [Terra Draw](https://github.com/JamesLMilner/terra-draw), through one session at a time. `session = widget.draw.begin(("polygon", "rectangle", "circle"), features=..., on_change=cb)` offers the tools (and `select` to edit them) and asks every view to show `features`. Each `begin` ends the session before it and numbers the new one (`drawing.session`, from 1); `session.end()` clears the drawing and hides the tools. An ended session's `features` is empty and its `set`, `clear`, `start` and `stop` raise. While a session offers tools, each view shows the draw toolbar at the top left, below the zoom and fullscreen controls: a button per tool, with Font Awesome icons, and a button that removes every shape. Its labels are English until `draw.set_labels({"polygon": ..., "clear": ...})` replaces the ones it names; they travel in `drawing.labels`. The browser holds the active tool, as it holds the camera: a click on a tool picks it in that view and a second click leaves it, without asking Python, and the clear button reports an empty drawing as a user's edit, even when nothing was drawn. A new session starts with no tool, and a view keeps its tool when its style is replaced. `session.start(mode)` and `session.stop()` ask for a tool through the read-only `draw_tool` trait (`{"seq", "session", "mode"}`): every view running the session follows, and so does the first view shown after the request, but a view shown later, or shown again, starts with no tool. Like the camera, the drawn features belong to the browser: `session.set(features)` or `session.clear()` asks every view to replace what it shows, `session.features` mirrors the last report Python accepted, and `on_change(collection)` runs on each drawing or edit a user made in the session. Python checks only the shapes (one closed ring per polygon, positions on the globe, JSON properties) and keeps ids, properties and coordinates as given. The browser prepares the features: it rounds them to 9 decimals, drops Terra Draw's reserved property names but `mode`, and replaces a missing, non-UUID or repeated id with one derived from the request, the same in every view. Polygons with holes and drawings across the antimeridian are not supported.
- **Insets** name the parts of the map that other UI covers: after `set_insets(left=300)`, views center and fit inside the rest, report its bounds, and move their controls in by as much, while the map keeps its place on screen. A fullscreen map uses none.
- **The fullscreen root** is what the fullscreen control fills: the closest ancestor marked `data-mapframe-fullscreen-root`, else the view's own element. Each view measures its four control corners each time one changes size, and sets their heights there inline as `--mapframe-controls-top-left`, `--mapframe-controls-top-right`, `--mapframe-controls-bottom-left` and `--mapframe-controls-bottom-right`, with `data-mapframe-controls` set to its id, so overlays a host places over the map can clear the controls, the draw toolbar included. While compare is on, the same element holds `--mapframe-divider-x`, the divider's x in px from its left edge, updated on every move, resize and inset change. A view removes them when it goes, unless a newer view has measured there since. A host must not bind that element's `style`, which would drop them.
- The traits that carry the contract (`state`, `view`, `view_request`, `insets`, `marker`, `drawing`, `draw_request`, `drawn`, `draw_tool`, `projection`) are read-only; only the widget's methods write them.
- **Layer status** (`loading`, `ready`, `error`) flows back per layer (`layer_status`, `on_status`). A PMTiles layer whose `source_layer` the archive does not hold is in error, with the names it holds.
- GeoJSON bytes never travel inside the state: `add_payload` returns a sha256 digest, and the browser pulls the bytes it lacks.
- **Compare**: `MapState(compare=True)` turns on a swipe compare. Each layer's `side` is `left`, `right` or `both` (the default); outside compare sides are ignored. The view's own map draws the `left` and `both` layers, and a second map stacked over it, which follows its camera, draws the `right` and `both` ones, clipped by a divider. The divider starts in the middle of the usable area; drag it, or use the arrow keys (5 % a step), Home and End. The browser keeps its position per view and never sends it to Python. Each map takes the GeoJSON payloads the other one holds instead of pulling them, so turning compare off or moving a layer from the right to the left pulls nothing, but a layer drawn only on the right is pulled again when compare turns on, since the first map released it.
- **Input in compare stays on the main map**: it keeps every input and the camera. Clicks, the pointer cursor, tooltips and cluster clicks use the features of the map shown under the pointer, and a click is still sent by the main map; its `ClickEvent.hidden_features` holds the features of the other map at that point. Popups, the tooltip and the highlight marker stay on the main map. Drawing takes input in both halves; Terra Draw runs on the main map and the right map shows a read-only mirror of the drawing, handles included, so a shape drawn across the divider shows whole. The attribution control lists the attributions of both maps.
- **Linked maps**: maps with the same `link_group` (`MapWidget(link_group="name")`, or `widget.link_group = "name"`) keep one camera, and `None` unlinks. The browser does it: every move that changes one view's camera, by a user or a request, jumps the others in the same call, without a round trip to Python, and they paint it on their next frame. A move that keeps the camera, such as a resize, moves nobody. Each view still reports its own camera, and a follower reports once per move of the map that moved, as that map does: as `user` when a user made the move, else as `link`. A `link` report counts like a user's, so `view` and `on_view` follow it. The first map shown sets the camera, and a map shown later takes it, unless a `set_center` or `fit_bounds` made after it joined moved it on mount, which then moves the others. Python moves only the members that no view shows, so a map in a hidden tab still shows where the group went. A shown map that only applies an older request, such as its first one, does not undo such a map's own later `set_center` or `fit_bounds` (made after it joined), which moves the others once it is shown. A map built into, or joined to, a group that has a camera starts there and ignores its own `center`: a re-run notebook cell or a Solara hot reload, which keeps the kernel, joins its new maps to the group of the old ones while those are open, so close them or use a new name. Under Solara, the component that builds a map closes it in an effect cleanup, which also runs on a hot reload. Linking is per page and per kernel, so two users of one `solara run` server never move each other's maps. The group holds no strong reference to its maps.
- The sources and layers the widget owns have ids starting with `mapframe:`, and the images it generates `mapframe-`; it never touches other layers, such as those of a drawing plugin. The sources and layers of its own Terra Draw start with `mapframe-draw-` and, like any other layer, stay above every `mapframe:` layer.

[`src/mapframe/state.py`](src/mapframe/state.py) declares and validates the state. The module docstring of [`widget.py`](src/mapframe/widget.py) describes the rest of the contract: how `publish` gives out instances, the owned style ids, the messages between Python and the views, the camera request and report rules, and the insets.

## Develop

You need Node 22 or later and npm to build the widget, Python 3.10 or later, and [nox](https://nox.thea.codes) to run the checks.

```bash
npm ci && npm run build        # bundle the widget
pip install -e ".[dev]"        # the package, the test and lint tools
pre-commit install             # run the hooks on each commit, and check commit messages
npm run dev                    # rebuild on change
ANYWIDGET_HMR=1 jupyter lab    # reload the widget without restarting the kernel
```

`npm run build` writes `src/mapframe/static/widget.js` and `widget.css`, which git ignores. `pip install .` and `pip install -e .` run `npm ci` and `npm run build` through `hatch_build.py` when those files are missing. A wheel built from an sdist reuses the files the sdist carries and needs no Node.

MapLibre and its worker, PMTiles, Terra Draw and the seven Font Awesome Free icons of the draw toolbar (polygon `draw-polygon`, rectangle `square`, circle `circle`, line `bezier-curve`, point `location-dot`, select `arrow-pointer`, clear `trash`; `square` and `circle` from the regular set, the others solid) are bundled into the Python package, so no request leaves the machine at runtime. [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) holds their licenses.

### Checks

Each nox session that needs the widget runs `npm ci` and `npm run build` first, so it never tests a stale bundle.

- `nox -s lint` runs the pre-commit hooks on every file: black, ruff, prettier (TypeScript, JavaScript, CSS, Markdown, JSON and YAML) and codespell.
- `nox -s typecheck` runs `tsc` and mypy.
- `nox -s js` runs the Vitest unit tests of `js/test/`.
- `nox -s tests` runs the Python unit tests on Python 3.10, 3.11 and 3.12. `nox -s tests-3.12` picks one version.
- `nox -s browser` runs the Playwright browser tests of `tests/browser/` in Chromium, under the Solara, Voila and JupyterLab runners, with the Jupyter user directories in a temporary folder. Arguments after `--` go to pytest, for example `nox -s browser -- tests/browser/test_view.py`.
- `nox -s release-check` builds the sdist from a copy of the repository, builds a wheel from that sdist on a PATH with no Node, installs the wheel in a clean environment and runs the offline render test against it. It needs network access for PyPI and npm.

`nox` alone runs `lint`, `typecheck`, `js` and `tests`. GitHub Actions runs all six on every pull request and every push to `main` (`.github/workflows/tests.yml`).

### Demo

`examples/random_ops.py` is a Solara page for manual testing of the bug that started this package, a layer drawn in the wrong place after many fast operations. "Random burst" fires 8 operations (add, remove, move, show or hide, opacity, paint, theme, basemap) with no waiting between them; the list beside the map shows the layer order and status Python expects. The page uses generated data only, so it works offline.

```bash
solara run examples/random_ops.py
```

## Release

The version lives in `pyproject.toml`. Commits follow [Conventional Commits](https://www.conventionalcommits.org), and [commitizen](https://commitizen-tools.github.io/commitizen/) bumps the version from them.

1. Bump the version: `cz bump`. It updates `pyproject.toml`, `src/mapframe/__init__.py`, the version test and `CHANGELOG.md`, commits, and tags `vX.Y.Z`. For the first release, 0.3.0, skip this step: set the date in `CHANGELOG.md` and tag `v0.3.0` by hand.
2. Push the commit and the tag: `git push --follow-tags`.
3. Publish a GitHub release for the tag. `.github/workflows/release.yml` then checks that the tag names the package version, runs the release check, builds the sdist and the wheel, and publishes them to PyPI with trusted publishing.

Before the first release, add a trusted publisher on PyPI for this repository, with the workflow `release.yml` and the environment `pypi`, and create that environment in the repository settings.

## License

MIT, see [`LICENSE`](LICENSE). The bundled JavaScript packages keep their own licenses, listed in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
