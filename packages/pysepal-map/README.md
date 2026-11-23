# pysepal-map

A generic MapLibre GL JS widget for Jupyter, built with anywidget. It depends only on `anywidget` and `traitlets`: no Earth Engine, Solara or ipyleaflet.

```python
from IPython.display import display
from pysepal_map import GeoJSONSource, Layer, MapState, MapWidget, VectorPaint

widget = MapWidget(center=(0, 0), zoom=2)
digest = widget.add_payload(b'{"type": "FeatureCollection", "features": []}')
widget.publish(MapState(layers=(Layer("pts", GeoJSONSource(digest), paint=VectorPaint()),)))
display(widget)
```

## What it owns

- **Python owns the persistent map state**: layers and their order, basemap, theme, controls (zoom, fullscreen, a metric scale, a coordinates readout), the cursor and a highlight marker. `MapWidget.publish(MapState)` publishes a whole snapshot, and every mounted view reconciles its map to it. Python never sends a one-off command that changes the map.
- **The browser owns the camera** and reports it back (`on_view`); Python can ask for a move with `set_center` and `fit_bounds`, which takes a `padding` in px and a `max_zoom` cap.
- **Clicks** reach Python as `ClickEvent`s (`on_click`) with the features under the point, from current layer instances only. A click on a cluster zooms into it and sends no event. There are no hover events.
- **Popups and tooltips** come from a layer's `Interaction(popup=..., tooltip=...)`: `()` shows every property, a tuple names the ones to show, a mapping of name to label shows them under those labels, `None` turns it off. A click opens a popup with a table of properties, and the pointer shows a tooltip. Values are inserted as text. Neither works on raster layers.
- **Pins and clusters**: `VectorPaint(marker="pin")` draws points as pins, and a `GeoJSONSource` with `Cluster(radius, max_zoom)` groups its points into count bubbles. A clustered source holds only points. A property `cluster` that is true is reserved on it. The pins are drawn in the browser and the counts as text with local glyphs, so nothing is fetched.
- **Colours by class**: `VectorPaint(color_by="status", class_colors={"open": "#ff0000", "closed": "#00ff00"})` colours one layer's features, pins included, by the value of a property. Values are all strings or all integers and are compared as they are, so `"1"` is not `1`; any other value, a null or a missing property keeps the paint's own colour.
- **The cursor and a marker**: `widget.cursor` sets the pointer (`""`, `"crosshair"`, `"pointer"` or `"wait"`), and `set_marker(lng, lat)` and `clear_marker()` show one highlight marker. `Controls(coordinates=True)` shows the pointer's coordinates.
- **Drawing** uses the bundled [Terra Draw](https://github.com/JamesLMilner/terra-draw), through one session at a time. `session = widget.draw.begin(("polygon", "rectangle", "circle"), features=..., on_change=cb)` offers the tools (and `select` to edit them) and asks every view to show `features`. Each `begin` ends the session before it and numbers the new one (`drawing.session`, from 1); `session.end()` clears the drawing and hides the tools. An ended session's `features` is empty and its `set`, `clear`, `start` and `stop` raise. While a session offers tools, each view shows the draw toolbar at the top left, below the zoom and fullscreen controls: a button per tool, with Font Awesome icons, and a button that removes every shape. Its labels are English until `draw.set_labels({"polygon": ..., "clear": ...})` replaces the ones it names; they travel in `drawing.labels`. The browser holds the active tool, as it holds the camera: a click on a tool picks it in that view and a second click leaves it, without asking Python, and the clear button reports an empty drawing as a user's edit, even when nothing was drawn. A new session starts with no tool, and a view keeps its tool when its style is replaced. `session.start(mode)` and `session.stop()` ask for a tool through the read-only `draw_tool` trait (`{"seq", "session", "mode"}`): every view running the session follows, and so does the first view shown after the request, but a view shown later, or shown again, starts with no tool. Like the camera, the drawn features belong to the browser: `session.set(features)` or `session.clear()` asks every view to replace what it shows, `session.features` mirrors the last report Python accepted, and `on_change(collection)` runs on each drawing or edit a user made in the session. Python checks only the shapes (one closed ring per polygon, positions on the globe, JSON properties) and keeps ids, properties and coordinates as given. The browser prepares the features: it rounds them to 9 decimals, drops Terra Draw's reserved property names but `mode`, and replaces a missing, non-UUID or repeated id with one derived from the request, the same in every view. Polygons with holes and drawings across the antimeridian are not supported.
- **Insets** name the parts of the map that other UI covers: after `set_insets(left=300)`, views center and fit inside the rest, report its bounds, and move their controls in by as much. A fullscreen map uses none.
- **The fullscreen root** is what the fullscreen control fills: the closest ancestor marked `data-psm-fullscreen-root`, else the view's own element. Each view measures its four control corners each time one changes size, and sets their heights there inline as `--psm-controls-top-left`, `--psm-controls-top-right`, `--psm-controls-bottom-left` and `--psm-controls-bottom-right`, with `data-psm-controls` set to its id, so overlays a host places over the map can clear the controls, the draw toolbar included. A view removes them when it goes, unless a newer view has measured there since. A host must not bind that element's `style`, which would drop them.
- The traits that carry the contract (`state`, `view`, `view_request`, `insets`, `marker`, `drawing`, `draw_request`, `drawn`, `draw_tool`) are read-only; only the widget's methods write them.
- **Layer status** (`loading`, `ready`, `error`) flows back per layer (`layer_status`, `on_status`).
- GeoJSON bytes never travel inside the state: `add_payload` returns a sha256 digest, and the browser pulls the bytes it lacks.
- **Compare**: `MapState(compare=True)` turns on a swipe compare (on `SepalMap`, `m.compare = True`). Each layer's `side` is `left`, `right` or `both` (the default); outside compare sides are ignored. The view's own map draws the `left` and `both` layers, and a second map stacked over it, which follows its camera, draws the `right` and `both` ones, clipped by a divider. The divider starts in the middle of the usable area; drag it, or use the arrow keys (5 % a step), Home and End. The browser keeps its position per view and never sends it to Python. Each map takes the GeoJSON payloads the other one holds instead of pulling them, so turning compare off or moving a layer from the right to the left pulls nothing, but a layer drawn only on the right is pulled again when compare turns on, since the first map released it.
- **Input in compare stays on the main map**: it keeps every input and the camera. Clicks, the pointer cursor, tooltips and cluster clicks use the features of the map shown under the pointer, and a click is still sent by the main map; its `ClickEvent.hidden_features` holds the features of the other map at that point. Popups, the tooltip and the highlight marker stay on the main map. Drawing takes input in both halves; Terra Draw runs on the main map and the right map shows a read-only mirror of the drawing, handles included, so a shape drawn across the divider shows whole. The attribution control lists the attributions of both maps.
- **Linked maps**: maps with the same `link_group` (`MapWidget(link_group="name")`, or `widget.link_group = "name"`) keep one camera, and `None` unlinks. The browser does it: every move that changes one view's camera, by a user or a request, jumps the others in the same call, without a round trip to Python, and they paint it on their next frame. A move that keeps the camera, such as a resize, moves nobody. Each view still reports its own camera, and a follower reports once per move of the map that moved, as that map does: as `user` when a user made the move, else as `link`. A `link` report counts like a user's, so `view` and `on_view` follow it. The first map shown sets the camera, and a map shown later takes it, unless a `set_center` or `fit_bounds` made after it joined moved it on mount, which then moves the others. Python moves only the members that no view shows, so a map in a hidden tab still shows where the group went. A shown map that only applies an older request, such as its first one, does not undo such a map's own later `set_center` or `fit_bounds` (made after it joined), which moves the others once it is shown. A map built into, or joined to, a group that has a camera starts there and ignores its own `center`: a re-run notebook cell joins its new maps to the group of the old ones while those are open, so close them or use a new name. Linking is per page and per kernel, so two users of one `solara run` server never move each other's maps. The group holds no strong reference to its maps.
- The sources and layers the widget owns have ids starting with `psm:`, and the images it generates `psm-`; it never touches other layers, such as those of a drawing plugin. The sources and layers of its own Terra Draw start with `psm-draw-` and, like any other layer, stay above every `psm:` layer.

[`src/pysepal_map/state.py`](src/pysepal_map/state.py) declares and validates the state. The module docstring of [`widget.py`](src/pysepal_map/widget.py) describes the rest of the contract: how `publish` gives out instances, the owned style ids, the messages between Python and the views, the camera request and report rules, and the insets.

## Build

Node 22 or later is needed to build, not to run. MapLibre and its worker, PMTiles, Terra Draw and the seven Font Awesome Free icons of the draw toolbar are bundled into the Python package, so no request leaves the machine at runtime.

```bash
npm ci && npm run build
```

This writes `src/pysepal_map/static/widget.js` and `widget.css` (gitignored). `pip install .` and `pip install -e .` run the same two commands through `hatch_build.py` when those files are missing; a wheel built from an sdist reuses the files the sdist carries and needs no Node.

## Test

From the repository root:

```bash
pipx run nox -s map -- tests
```

It runs the TypeScript checks, Vitest, the Python tests and the Playwright browser tests under the Solara, Voila and JupyterLab runners, with the Jupyter user directories in a temporary folder. `nox -s map-release` builds the sdist and a wheel without Node, installs the wheel in a clean environment and runs the offline render test against it.

## Develop

```bash
cd packages/pysepal-map
npm run dev           # rebuild on change
ANYWIDGET_HMR=1 jupyter lab   # reload the widget without restarting the kernel
```

## Demo

`examples/random_ops.py` is a Solara page for manual testing of the bug that started this package, a layer drawn in the wrong place after many fast operations. "Random burst" fires 8 operations (add, remove, move, show or hide, opacity, paint, theme, basemap) with no waiting between them; the list beside the map shows the layer order and status Python expects. The page uses generated data only, so it works offline.

```bash
solara run packages/pysepal-map/examples/random_ops.py
```

Checked with headless Chrome driven by `scripts/browser_probe.mjs` with its default launch flags: it created a WebGL context and rendered the map.
