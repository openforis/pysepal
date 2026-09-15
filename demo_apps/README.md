# pysepal demo apps

Working apps built on pysepal, kept here to be read and run. They are **not**
scaffolding — `module_factory` copies `pysepal/templates/map_app` and
`pysepal/templates/panel_app`, never these. Nothing here ships in the wheel.

| Demo                                       | What it exercises                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [`solara_map_app`](solara_map_app)         | What a real SEPAL module needs: AOI selection, async processing with progress notifications, layer management, a floating legend driven by the layers on the map, and Earth Engine / Drive / SEPAL exports. Authenticates against SEPAL.                                                                                                               |
| [`solara_aoi_app`](solara_aoi_app)         | Persisting an area of interest and getting it back. `AoiView` carries the computed `AoiResult` on `value` and the small JSON `AoiSpec` on `spec`; only the spec is written, and passing it back rebuilds both the picker and the geometry. No Earth Engine and no credentials.                                                                         |
| [`solara_aoi_gee_app`](solara_aoi_gee_app) | The same save and restore with Earth Engine on, against a SEPAL session. Reaches what the local one cannot: an ASSET selection round-trips its `asset_id`, and DRAW builds its `ee` geometry on the session the app authenticated. The file methods are excluded, because a saved pathname does not travel between users. Authenticates against SEPAL. |
| [`solara_raster_app`](solara_raster_app)   | Local raster rendering through `SepalMap.add_raster`: a continuous colormap, exact per-class colors, and a raster big enough that preparing it has to happen off the event loop. No session, no credentials.                                                                                                                                           |
| [`solara_vector_app`](solara_vector_app)   | Local vector tiling with `vectortileserver`: one PMTiles archive styled as a single symbol and by attribute value. Needs `tippecanoe` on PATH and the `demos` extra. No session, no credentials.                                                                                                                                                       |

## Running them

Every demo is laid out the same way, and that shape is enforced by
`tests/test_solara/test_demo_apps.py`:

- `app.py` holds the UI in a plain `@solara.component` plus a `Page` entrypoint.
- `ui.ipynb` is a three-line Voila entrypoint that imports that component and
  displays it.

So each one runs under both runtimes, and the gallery below is just a third way
in — the same components either way.

### The gallery, under Solara

```bash
pysepal$ ./run_solara.sh demo_apps/gallery.py --port 8901
```

`gallery.py` gives every demo its own route and a landing page that links to
them. Demos render full-screen, so use the browser's back button to return.

### The gallery, under Voila

```bash
pysepal$ voila demo_apps/ --port 8902
```

Voila serves the directory as a tree; open a demo's folder and click its
`ui.ipynb`.

### One demo on its own

```bash
pysepal$ ./run_solara.sh demo_apps/solara_raster_app/app.py --port 8901
pysepal$ voila demo_apps/solara_raster_app/ui.ipynb --port 8902
```

### Notes

`solara_map_app` and `solara_aoi_gee_app` read SEPAL credentials from a `.env` at
the repo root — `run_solara.sh` is what loads it. `solara_raster_app` needs none, and generates
small synthetic int16 class rasters unless `PYSEPAL_DEMO_RASTER_DIR` points at a
directory holding `aa_test_congo.tif` and `hansen_bolivia.tif`.

If `import pysepal` fails, the checkout is not installed (`pip install -e .`);
prefix the commands with `PYTHONPATH=$PWD` to run against the source tree.
