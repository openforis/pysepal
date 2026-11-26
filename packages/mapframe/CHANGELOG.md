## v0.3.0 (unreleased)

First release from its own repository. Until now it lived in the pysepal repository, under `packages/pysepal-map`, and was not published. It installs and imports as `mapframe`.

### Feat

- `MapWidget` and `MapState`: Python declares the whole map state (layers, basemap, theme, controls, cursor, marker) and every view reconciles its MapLibre GL JS map to it.
- Raster tile, GeoJSON and PMTiles sources, with per-layer status (`loading`, `ready`, `error`) reported back to Python; a PMTiles layer name the archive lacks is an error.
- Camera reports and requests: `set_center` and `fit_bounds`, which can fly there with `animate=True`.
- Click events, popups and tooltips (a feature within 3 px of the pointer counts when none is under it), pins, clusters and colours by class.
- Drawing with Terra Draw, one session at a time.
- A swipe compare view and linked maps (`link_group`).
- `Controls(globe=True)`: a button that turns the map into a globe and back. `projection` and `set_projection` read and set it from Python, and a view shown later starts in it.
- A Leaflet-style `{s}` in a tile URL expands to the subdomains a, b and c, and `{r}` is dropped; `tile_urls` expands one for other subdomains.
- `Basemap.from_xyz` builds a basemap from an xyzservices `TileProvider`, and raises `ValueError` for one MapLibre cannot draw.
- `check_clusterable`: `publish` raises `ValueError` when a clustered source holds anything but points, or a feature with `cluster: true`.
- MapLibre, its worker, PMTiles, Terra Draw and the toolbar icons are bundled, so nothing is loaded from a CDN at runtime.
