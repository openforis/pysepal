# pysepal-map

A generic MapLibre GL JS widget for Jupyter, built with anywidget. It depends
only on `anywidget` and `traitlets`: no Earth Engine, Solara or ipyleaflet.

```python
from IPython.display import display
from pysepal_map import GeoJSONSource, Layer, MapState, MapWidget, VectorPaint

widget = MapWidget(center=(0, 0), zoom=2)
digest = widget.add_payload(b'{"type": "FeatureCollection", "features": []}')
widget.draw(MapState(layers=(Layer("pts", GeoJSONSource(digest), paint=VectorPaint()),)))
display(widget)
```

## What it owns

- **Python owns the persistent map state**: layers and their order, basemap,
  theme, controls. `MapWidget.draw(MapState)` publishes a whole snapshot, and
  every mounted view reconciles its map to it. Python never sends a one-off
  command that changes the map.
- **The browser owns the camera** and reports it back (`on_view`); Python can
  ask for a move with `set_center` and `fit_bounds`.
- **Layer status** (`loading`, `ready`, `error`) flows back per layer
  (`layer_status`, `on_status`).
- GeoJSON bytes never travel inside the state: `add_payload` returns a sha256
  digest, and the browser pulls the bytes it lacks.
- Everything the widget adds to the MapLibre style has an id starting with
  `psm:`; it never touches other layers, such as those of a drawing plugin.

The full contract, with its invariants, is documented in
[`src/pysepal_map/state.py`](src/pysepal_map/state.py) and
[`widget.py`](src/pysepal_map/widget.py).

## Build

Node 22 or later is needed to build, not to run. MapLibre and its worker are
bundled into the Python package, so no request leaves the machine at runtime.

```bash
npm ci && npm run build
```

This writes `src/pysepal_map/static/widget.js` and `widget.css` (gitignored).
`pip install .` and `pip install -e .` run the same two commands through
`hatch_build.py` when those files are missing; a wheel built from an sdist
reuses the files the sdist carries and needs no Node.

## Test

From the repository root:

```bash
pipx run nox -s map -- tests
```

It runs the TypeScript checks, Vitest, the Python tests and the Playwright
browser tests under the Solara, Voila and JupyterLab runners, with the Jupyter
user directories in a temporary folder. `nox -s map-release` builds the sdist
and a wheel without Node, installs the wheel in a clean environment and runs
the offline render test against it.

## Develop

```bash
cd packages/pysepal-map
npm run dev           # rebuild on change
ANYWIDGET_HMR=1 jupyter lab   # reload the widget without restarting the kernel
```

## Demo

`examples/random_ops.py` is a Solara page for manual testing of the bug that
started this package, a layer drawn in the wrong place after many fast
operations. "Random burst" fires 8 operations (add, remove, move, show or
hide, opacity, paint, theme, basemap) with no waiting between them; the list
beside the map shows the layer order and status Python expects. The page uses
generated data only, so it works offline.

```bash
solara run packages/pysepal-map/examples/random_ops.py
```

Headless Chrome creates a WebGL context with its default flags (software
rendering), so `scripts/browser_probe.mjs` can drive the page.
