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
- **The browser owns the camera** and reports it back (`on_view`); Python can ask for a move with `set_center` and `fit_bounds`, which takes a `max_zoom` cap and a `zoom_out` step.
- **Clicks** reach Python as `ClickEvent`s (`on_click`) with the features under the point, from current layer instances only. A click on a cluster zooms into it and sends no event. There are no hover events.
- **Popups and tooltips** come from a layer's `Interaction(popup=..., tooltip=...)`: `()` shows every property, a tuple names the ones to show, `None` turns it off. A click opens a popup with a table of properties, and the pointer shows a tooltip. Values are inserted as text. Neither works on raster layers.
- **Pins and clusters**: `VectorPaint(marker="pin")` draws points as pins, and a `GeoJSONSource` with `Cluster(radius, max_zoom)` groups its points into count bubbles. A clustered source holds only points. The pins and bubbles are drawn in the browser, so nothing is fetched.
- **The cursor and a marker**: `widget.cursor` sets the pointer (`""`, `"crosshair"`, `"pointer"` or `"wait"`), and `set_marker(lng, lat)` and `clear_marker()` show one highlight marker. `Controls(coordinates=True)` shows the pointer's coordinates.
- **Drawing** uses the bundled [Terra Draw](https://github.com/JamesLMilner/terra-draw). `widget.draw.enable(("polygon", "rectangle", "circle"))` offers the tools (and `select` to edit them), `draw.start(mode)` picks one, and `draw.set(features)` or `draw.clear()` asks every view to replace what it shows. Like the camera, the drawn features belong to the browser: `draw.features` mirrors the last report Python accepted, and `on_draw` runs on each drawing or edit a user made. Polygons with holes and drawings across the antimeridian are not supported.
- **Insets** name the parts of the map that other UI covers: after `set_insets(left=300)`, views center and fit inside the rest, report its bounds, and move their controls in by as much. A fullscreen map uses none.
- The traits that carry the contract (`state`, `view`, `view_request`, `insets`, `marker`, `drawing`, `draw_request`, `drawn`) are read-only; only the widget's methods write them.
- **Layer status** (`loading`, `ready`, `error`) flows back per layer (`layer_status`, `on_status`).
- GeoJSON bytes never travel inside the state: `add_payload` returns a sha256 digest, and the browser pulls the bytes it lacks.
- The sources and layers the widget owns have ids starting with `psm:`, and the images it generates `psm-`; it never touches other layers, such as those of a drawing plugin. The sources and layers of its own Terra Draw start with `psm-draw-` and, like any other layer, stay above every `psm:` layer.

[`src/pysepal_map/state.py`](src/pysepal_map/state.py) declares and validates the state. The module docstring of [`widget.py`](src/pysepal_map/widget.py) describes the rest of the contract: how `publish` gives out instances, the owned style ids, the messages between Python and the views, the camera request and report rules, and the insets.

## Build

Node 22 or later is needed to build, not to run. MapLibre and its worker, PMTiles and Terra Draw are bundled into the Python package, so no request leaves the machine at runtime.

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
