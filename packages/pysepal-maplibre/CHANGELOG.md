## v0.3.0 (unreleased)

First release from its own repository. Until now it lived in the pysepal repository, under `packages/pysepal-map`, and was not published. It installs as `pysepal-maplibre` and imports as `pysepal_map`.

### Feat

- `MapWidget` and `MapState`: Python declares the whole map state (layers, basemap, theme, controls, cursor, marker) and every view reconciles its MapLibre GL JS map to it.
- Raster tile, GeoJSON and PMTiles sources, with per-layer status (`loading`, `ready`, `error`) reported back to Python.
- Camera reports and requests: `set_center` and `fit_bounds`, which can fly there with `animate=True`.
- Click events, popups and tooltips, pins, clusters and colours by class.
- Drawing with Terra Draw, one session at a time.
- A swipe compare view and linked maps (`link_group`).
- `Controls(globe=True)`: a button that turns each view's map into a globe and back.
- MapLibre, its worker, PMTiles, Terra Draw and the toolbar icons are bundled, so nothing is loaded from a CDN at runtime.
