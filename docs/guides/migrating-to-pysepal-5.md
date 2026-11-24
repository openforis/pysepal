# Migrating to pysepal 5

pysepal 5 supports only **ipyvuetify 3** (Vuetify 3, Vue 3). It removes the old
widget layer, `pysepal.sepalwidgets`, which worked only on ipyvuetify 1
(Vuetify 2, Vue 2), and everything built on it.

## What was removed

- `pysepal.sepalwidgets`: every `sw.*` widget, including the ipyvuetify
  subclasses (`sw.Btn`, `sw.Card`, `sw.Tile`, ...) and the Vue `MapApp`,
  `ThemeToggle`, `RightPanel` and `LocaleSelect` in `sepalwidgets.vue_app`.
- The widgets built on it:
  - `pysepal.aoi.AoiTile`, `pysepal.aoi.AoiView` and `select_methods`;
  - `pysepal.planetapi.PlanetView`, `InfoView` and `InfoCard`;
  - `pysepal.mapping.AoiControl` (`from pysepal.mapping import *` no longer
    exports it) and `AoiModel.ipygeojson` / `AoiModel.get_ipygeojson`, which
    built an ipyleaflet layer (use `LayerSpec.from_geojson` on
    `model.gdf.__geo_interface__`, or `m.layer_store`);
  - `pysepal.mapping.LayersControl` and the `pysepal.mapping.layers_control`
    module (see [LayersControl → LayerPanel](#layerscontrol--layerpanel));
  - `pysepal.scripts.thread_controller`.
- **ipyleaflet.** It is no longer a dependency, and pysepal no longer installs
  the jupyter-leaflet labextension. An app that imports `ipyleaflet` itself
  must depend on it. `xyzservices` is now a direct dependency.
- The `theme_toggle` argument of `SepalMap`: the `ThemeToggle` it took no
  longer exists. Pass `theme_state=` instead; the Solara `MapApp` binds it for
  you. A map without `theme_state` follows `get_current_theme_state()`, the
  kernel's theme, not `v.theme.dark`: drive it with `ThemeToggle` or
  `get_current_theme_state().set_mode("dark")`.
- The `catch_errors` and `loading_button` decorators in
  `pysepal.scripts.decorator`, and their old aliases in `pysepal.scripts.utils`.
- The `module_factory` command and the `pysepal/templates` scaffolds it copied.
- The `sepal_ipyvuetify` command, which generated the sepalwidgets classes.

An old import now fails with a message that points here:

- `import pysepal.sepalwidgets`, `import pysepal.mapping.layers_control` and
  the modules of the removed map controls (see
  [Map controls](#map-controls)): `aoi_control`, `draw_control`,
  `fullscreen_control`, `geojson_utils`, `inspector_control`, `layer`,
  `layer_state_control`, `layers_control`, `legend_control`, `marker_cluster`, `menu_control` and
  `zoom_control`, raise an `ImportError`;
- `pysepal.aoi.AoiView` and the other removed names raise an `AttributeError`
  that names the replacement.

These stay:

- `pysepal.solara` and its components, including `MapApp`;
- `SepalMap`;
- `AoiModel` and `PlanetModel`;
- the `module_deploy`, `module_venv`, `activate_venv` and `entry_point`
  commands.

## What changed

The select items that pysepal builds use the Vuetify 3 shape. Code
that reads `item["text"]` must read `item["title"]`. This covers:

- `fetch_admin_items` in `pysepal.solara.components.aoi.admin`, which returns
  `{"title", "value"}`;
- `get_source_items` and `get_target_items` in
  `pysepal.solara.components.export_hook`, and `TABLE_FILE_FORMATS` in
  `pysepal.solara.components.export_models`. A disabled item has
  `"props": {"disabled": True}`, a header is
  `{"type": "subheader", "title": ...}` and a divider is
  `{"type": "divider", "title": ""}`.

### LayersControl → LayerPanel

`SepalMap` no longer builds a `LayersControl`. Every map owns a
`SepalMap.layer_store`, a `pysepal.layers.LayerStore` that holds its layers top
first, and draws whatever is in it. The Solara `LayerPanel` lists that store and
edits it: visibility, opacity, order, style and removal. To share the layers with
other components, build the store yourself and pass it with
`SepalMap(layer_store=...)`.

- **The wrappers write to the store.** `add_raster`, `add_raster_async`,
  `add_ee_layer` and `add_ee_layer_async` keep their arguments and return a
  `LayerHandle` (see [SepalMap on MapLibre](#sepalmap-on-maplibre)). The
  layer's id in the store is `key`, or the normalized layer name when `key` is
  empty. `find_layer` and `remove_layer` find a layer by key or name, hidden
  ones included, and `remove_all` removes them all.
- **The same key replaces the layer in place.** Adding a layer whose key is
  already in the store replaces it and keeps its position, visibility and
  opacity. Without a `key`, the key is the normalized name, so two calls with
  the same name replace each other: `add_raster` no longer adds three random
  letters to a name already in use. A call with neither a name nor a key gets a
  new `Layer N` name and its own layer. When an `*_async` call is overtaken by
  a newer action on the same key (another add, a removal, a restyle in the
  panel), the newer one wins. `add_raster_async` then returns `None`.
- **Overlay layers are not listed.** A layer in the overlay zone of the store
  (`LayerSpec(zone="overlay")`, or `add_ee_layer(..., overlay=True)`) is drawn
  above every data layer, and the panel does not list it. The AOI and its
  preview are drawn that way.
- **The store drives visibility and opacity.** Set them on the handle a
  wrapper or `find_layer` returns (`handle.visible = True`,
  `handle.opacity = 0.5`), or call `m.layer_store.set_visible(key, True)` and
  `m.layer_store.set_opacity(key, 0.5)`.
- **The Earth Engine object is rebuilt.** An Earth Engine layer keeps its object
  as a serialized expression, and the object the map draws is rebuilt from it:
  it is equivalent to the object you passed, but not the same Python object.
- **Earth Engine colours are normalised** to `#rrggbb`. The alpha of an
  8-digit `fillColor` becomes the fill opacity, but an `RRGGBBAA` `color` (the
  stroke) or palette entry loses its alpha. Use a 6-digit colour, and
  `fill_opacity` for a see-through fill.
- **No layer or basemap switcher on the map.** Without the old in-map control,
  users switch layers only where the app shows a `LayerPanel`, and the basemap
  only where the app sets `m.basemap`. In a `MapApp`, add the panel as a right
  panel section:

  ```python
  from pysepal.solara.components.layer_panel import LayerPanel

  right_panel_content = [
      {"title": "Layers", "icon": "mdi-layers", "content": LayerPanel(store=m.layer_store, map_=m)},
  ]
  ```

  In a notebook or a Voila app, display it next to the map:

  ```python
  import solara

  from pysepal.solara.components.layer_panel import LayerPanel
  from pysepal.solara.components.map_view import MapView

  solara.display(MapView(m), LayerPanel(store=m.layer_store, map_=m))
  ```

### Map controls

The draw, inspector, zoom, fullscreen, state bar, menu and legend controls only
attach to an ipyleaflet map, so they are removed, and `SepalMap` loses the
arguments and members that built them. The MapLibre map draws its own zoom and
scale controls, and a fullscreen control with `fullscreen_control=True`. Their
modules raise an `ImportError`, their names in `pysepal.mapping` and the removed
`SepalMap` members raise an `AttributeError`. `m.state` no longer means the state
bar: it is the map's declared state.

| Removed                                                                                                                           | Replacement                                                                                                                                                                                                                                                                                               |
| --------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ZoomControl`, `FullScreenControl`                                                                                                | the map draws its own zoom, scale and fullscreen controls                                                                                                                                                                                                                                                 |
| `LayerStateControl`, `SepalMap(statebar=...)`, `m.state`                                                                          | `MapView` shows layer loading                                                                                                                                                                                                                                                                             |
| `LegendControl`, `m.add_legend`, `m.add_colorbar`                                                                                 | the `MapView` legend, built from each layer's legend                                                                                                                                                                                                                                                      |
| `MenuControl`                                                                                                                     | Solara components in `MapView(overlays=...)`                                                                                                                                                                                                                                                              |
| `DrawControl`, `GeomanDrawControl`, `SepalMap(dc=...)`, `m.dc`, `m.show_dc`, `m.hide_dc`, `dc.on_draw`, `dc.data`, `dc.to_json()` | `m.draw.begin(modes)` and the `DrawSession` it returns (`features`, `set`, `clear`, `start`, `stop`, `end`, `on_change`); the map draws the toolbar                                                                                                                                                       |
| `InspectorControl`, `ValueInspector`, `SepalMap(vinspector=...)`, `m.v_inspector`                                                 | `SepalMap(inspector=True)`, shown by `MapView`                                                                                                                                                                                                                                                            |
| `m.on_interaction(handler)` with `type == "click"`                                                                                | `m.on_click(cb)` with a `ClickEvent` (`lng`, `lat`, `features`)                                                                                                                                                                                                                                           |
| mousemove coordinate readouts                                                                                                     | `SepalMap(coordinates=True)`                                                                                                                                                                                                                                                                              |
| `EELayer` (`pysepal.mapping.layer`)                                                                                               | `m.add_ee_layer(...)`, or a `LayerSpec` and the `LayerHandle` it returns                                                                                                                                                                                                                                  |
| `get_ipygeojson` (`pysepal.mapping.geojson_utils`), `AoiModel.ipygeojson`, `AoiModel.get_ipygeojson`                              | `LayerSpec.from_geojson(...)` or `LayerSpec.from_vector(...)` with a `VectorStyle`                                                                                                                                                                                                                        |
| vectortileserver's `create_leaflet_layer`, an ipyleaflet `PMTilesLayer`                                                           | `LayerSpec.from_vector(url, format="PMTiles", layer="<source layer>", style=VectorStyle(...))` with the layer's URL. `format=` overrides the suffix guess, and a root-relative URL (vectortileserver's `/api/sandbox/jupyter/proxy/<port>/pmtiles?filePath=...` behind SEPAL's proxy) stays a browser URL |
| `Marker`, `AwesomeIcon`, `MarkerCluster`, `LayerGroup` of clusters                                                                | `LayerSpec.from_points(...)` with `VectorStyle(marker="pin", cluster=True)`; one layer holds every category with `VectorStyle(color_by=..., class_colors=...)`                                                                                                                                            |
| `Popup` with HTML, `on_hover` labels                                                                                              | `VectorStyle(popup=[...])`, `VectorStyle(tooltip={...})`                                                                                                                                                                                                                                                  |
| `Popup` holding widgets                                                                                                           | `m.on_click(cb)` and a Solara component in `MapView(overlays=...)`                                                                                                                                                                                                                                        |
| `hover_style`, `style_callback`                                                                                                   | `VectorStyle(color_by=..., class_colors=...)`: one layer holds every class, on vectors the browser draws, not Earth Engine ones; no hover style                                                                                                                                                           |
| `SplitMapControl(left_layer=..., right_layer=...)`                                                                                | `m.compare = True` with `side="left"` and `side="right"` on the layer methods (or `handle.side`); other layers stay on both sides                                                                                                                                                                         |
| `traitlets.link((m1, "center"), (m2, "center"))` and the same on `zoom`                                                           | `SepalMap(link_group="name")`, or `m.link_group = "name"`, on each map                                                                                                                                                                                                                                    |

Notes on the interaction replacements:

- **Coordinates are `lng, lat`.** ipyleaflet used `[lat, lon]`; a `ClickEvent`,
  the drawn features and `LayerSpec.from_points` use longitude first.
- **Callback shapes changed.** A session's `on_change(collection)` gets one
  GeoJSON FeatureCollection of everything drawn, not ipyleaflet's
  `(target, action, geo_json)`. `m.on_click(cb)` calls `cb(event)` with one
  `ClickEvent`, not the `**kwargs` of `on_interaction`.
- **Clicks.** `m.on_click(cb)` calls `cb(event)` with the features under the
  point, top first. `event.hits(layer_id)` gives the properties of one layer.
  A click on a cluster zooms into it and sends no event.
- **No hover events or hover style, and colors by class only.** Use a tooltip
  for a hover label. In place of a `style_callback`, one layer holds every class
  through `VectorStyle(color_by="status", class_colors={"open": "#ff0000"})`,
  with `class_labels` for the legend. It applies to vectors the browser draws,
  not to Earth Engine vectors, which refuse it. A feature whose value is in no
  class keeps the layer's own color.
- **Popups and tooltips show a table of properties.** `popup=True` shows every
  property, a list names the ones to show, a dict maps each name to the label
  shown for it (`popup={"alert_dt": "Date"}`). A popup that holds widgets (a
  "Go" button, say) becomes `m.on_click` plus a component in `MapView`.
  They apply to vector layers drawn by the browser, not to Earth Engine vectors
  or tile layers.
- **Clusters hold only points.** A property `cluster` that is true is reserved
  on a clustered layer.
- **Drawing.** `AoiView` offers DRAW on a `SepalMap` again. A polygon with holes
  cannot be drawn or given to `session.set` (it raises), and drawings across the
  antimeridian are not supported.
- **The inspector is opt-in.** `SepalMap(inspector=True)` builds it, and every
  `MapView` of the map shows its toggle and card. It reads Earth Engine images
  at the clicked view's scale.
- **Linked maps.** Give each map the same `link_group`; `None` unlinks. The
  first map shown sets the camera, and a map built later starts where the
  group is. A re-run cell, and a Solara hot reload, which keeps the kernel,
  join the maps they build to the group of the old ones, so close the old
  maps or use a new name. In a Solara app, build each map with
  `pysepal.solara.use_sepal_map`, which closes it on unmount, on a dependency
  change and on a hot reload.

```python
import pandas as pd

from pysepal.layers import LayerSpec, VectorStyle

m = SepalMap(inspector=True, coordinates=True)
sites = pd.DataFrame({"lng": [-74.0, -73.9], "lat": [4.6, 4.7], "name": ["A", "B"]})
spec = LayerSpec.from_points(
    sites,
    name="Sites",
    style=VectorStyle(marker="pin", cluster=True, tooltip=["name"]),
)
m.layer_store.add(spec)
m.on_click(lambda event: print(event.lng, event.lat, event.hits(spec.id)))
```

### SepalMap on MapLibre

`SepalMap` is a MapLibre map (`pysepal_map.MapWidget`), no longer an ipyleaflet
`Map`. Everything it shows persistently (layers, basemap, theme, controls,
insets) is declared in its synced state. The camera belongs to the browser:
`set_center`, `fit_bounds` and `zoom_bounds` ask the views to move, and `m.view`
holds where the camera is once a view reported. A removed member raises an
`AttributeError` that names its replacement.

| Before                                                                                          | Now                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ipyleaflet keyword arguments (`min_zoom`, `scroll_wheel_zoom`, `layout`, ...), `map_id`         | `SepalMap(basemaps, *, gee, theme_state, gee_session, gee_interface, fullscreen, fullscreen_control, layer_store, center, zoom, height, loop, inspector, coordinates, link_group)` |
| positional options, `SepalMap([], False)`                                                       | everything after `basemaps` is keyword-only; `SepalMap([], False)` raises `TypeError`                                                                                              |
| `center=[lat, lng]`                                                                             | `center=(lng, lat)`                                                                                                                                                                |
| `m.center`, `m.zoom`                                                                            | `m.view` to read the camera, `m.set_center(lng, lat, zoom)` to move it                                                                                                             |
| `m.set_center(lon, lat, zoom=-1)`                                                               | `m.set_center(lng, lat, zoom=None)`: the keyword is `lng`, and no zoom keeps the current one                                                                                       |
| Leaflet zoom levels (a 256 px world at zoom 0)                                                  | MapLibre counts a 512 px world at zoom 0: the same number shows the world twice as large. `get_scale()` is 78271.517 m per CSS pixel at zoom 0 on the equator                      |
| `zoom_bounds` on a point zooms to the map maximum                                               | it stops at zoom 18 (`zoom_bounds(bounds, max_zoom=...)`).                                                                                                                         |
| `zoom_out=` on `zoom_bounds`, `zoom_ee_object`, `zoom_raster`, `zoom_layer`, `LayerHandle.zoom` | gone: pass `padding=` in px, by keyword (a positional call raises `TypeError`); a padding the map cannot hold is reduced                                                           |
| `m.centerObject(item)`, once an alias of `zoom_ee_object`                                       | `centerObject(item, zoom)` takes the GEE console's zoom and centers on the object; without a zoom it fits the object                                                               |
| `m.layers`, `m.add_layer(layer)`, ipyleaflet layers                                             | `m.layer_store.add(LayerSpec.from_tiles(...))`, or another `LayerSpec` factory                                                                                                     |
| `m.add_control`, `m.remove_control`, `m.controls`, `WidgetControl`                              | Solara components in `MapView(overlays=...)`                                                                                                                                       |
| `m.viewport_inset_left`, `_right`, `_bottom`                                                    | `m.set_insets(left=..., right=..., top=..., bottom=...)`; `MapApp` sets them                                                                                                       |
| `m.canvas_width_px`, `m.canvas_height_px`                                                       | nothing: the browser fits the camera to the map element itself                                                                                                                     |
| the `base` argument of `find_layer`, `remove_layer` and `remove_all`                            | gone: the basemaps are not layers. `m.basemaps` holds the choices and `m.basemap` the one shown; `remove_layer(key, none_ok=True)` takes `none_ok` by keyword only                 |
| `add_basemap(name)` adds a base layer                                                           | it adds `name` to `m.basemaps` and shows it                                                                                                                                        |
| `find_layer(key)` raises `ValueError`, or takes an index                                        | it returns a `LayerHandle`, or `None`. A string is an id, then a name, overlay layers first; there is no index                                                                     |
| the wrappers return an ipyleaflet layer                                                         | they return a live `LayerHandle` (`visible`, `opacity`, `restyle()`, `zoom()`, `remove()`); an `*_async` one returns `None` when superseded or after `m.close()`                   |
| `zoom_raster(layer)` with an ipyleaflet layer                                                   | `zoom_raster` takes a handle, a layer id or a raster path                                                                                                                          |
| `basemap_tiles`, `xyz_to_leaflet` in `pysepal.mapping.basemaps`                                 | `BASEMAP_NAMES`, `get_basemap(name)` and `basemap_label(name)`; `get_basemap_list()` leaves out the providers MapLibre cannot draw                                                 |
| `create_wms_preview_layer` returns a `WMSLayer`                                                 | it returns a `LayerSpec` in the overlay zone, for `m.layer_store.add`                                                                                                              |
| `remove_wms_preview_layer(map_, name=...)` finds the preview by its name                        | `remove_wms_preview_layer(map_, layer_id=...)` removes it from the store by id (default `"aoi_preview"`)                                                                           |
| `SepalMap(fullscreen=True)` adds a CSS class                                                    | it sets `height="100%"`, so the map fills its container (the `.full-screen-map`, `.aoi_map`, `.results_map` and `.pysepal-map-theme-*` classes are gone with the Leaflet CSS)      |

**Known limitation: local raster tiles.** MapLibre fetches tiles where ipyleaflet
loaded them as images, so a local raster's tile URL on another origin than the
page needs CORS headers, which `localtileserver` does not send. Such tiles reach
the map only through a same-origin route (the prefix SEPAL sets,
`jupyter-server-proxy` in JupyterLab, a route you mount) or through
jupyter-loopback's comm bridge, which pysepal turns on for every local raster.
With the bridge off (`LOCALTILESERVER_DISABLE_JUPYTER_LOOPBACK=1`) and no such
route, the browser blocks them. See [local-tile-servers.md](./local-tile-servers.md).

### The map

A map app now has three parts that share one `LayerStore`: the `SepalMap`, the
`LayerPanel` that edits the store, and a `MapView` that puts Solara components
over the map. `MapApp` puts your map in a `MapView`; add a `LayerPanel` to one
of its sections, as `demo_apps/solara_raster_app/app.py` does.

- **Panel rows are one line.** Each row has a drag handle, a visibility toggle,
  the name, a status, zoom-to-layer, a settings button and a remove button.
  The settings button (the gear) opens a pop-up with the style form, the
  opacity and the download and export buttons. A row has no expansion panel and
  no legend. Zoom-to-layer uses the bounds the layer was prepared with; an
  Earth Engine layer looks them up on the first zoom, and a layer without
  bounds still draws but disables its zoom button.
- **Legends and loading status are in the `MapView`.** One legend card sits
  centred at the bottom of the map, or of each half while the map compares. It
  lists the visible layers of its area that have a legend, built from each
  layer's legend, and shows one at a time: the top one, the one picked in its
  dropdown, or a layer the app has just added. Give a layer its own legend with
  `legend=` on `add_raster` and `add_ee_layer` (and their async twins), or later with
  `handle.legend = Legend(...)`; `None` goes back to the derived one. An explicit
  legend is yours, so `restyle` keeps it. A status badge at the top right shows while
  layers are loading. Overlays you add are placed
  in the corner you name, inside the map's insets.

```python
# before
from ipyleaflet import TileLayer, WidgetControl

m.add_layer(TileLayer(url="https://example.org/{z}/{x}/{y}.png", name="Tiles"))
m.add_control(WidgetControl(widget=chip, position="topleft"))

# after
from pysepal.layers import LayerSpec
from pysepal.solara.components.map_view import MapView

m.layer_store.add(LayerSpec.from_tiles("https://example.org/{z}/{x}/{y}.png", name="Tiles"))
MapView(m, overlays={"top-left": [chip]})
```

`MapView` takes `"top-left"`, `"top-right"`, `"bottom-left"` and `"bottom-right"`
as corner names. Outside `MapApp`, display `MapView(m)` instead of `m`.

## Why

- Vue 2 reached its end of life on 2023-12-31, and Vuetify 2 depends on it.
- Since August 2026, `pip install solara` installs ipyvuetify 3. Solara 2 will
  support Vuetify 3 only (widgetti/solara#1163).
- Supporting both majors doubled the work on every widget. The Solara
  components are where pysepal's UI work goes.

## Who is affected

**Solara apps** (`solara run`, the SEPAL container apps) ship their own
frontend. They can move to pysepal 5 as soon as their code is ready.

**Voila apps in SEPAL's app catalog** bring their own frontend too: SEPAL's
Voila loads the widget extensions from the app's own environment first. Each
app moves to pysepal 5 when its code is ready, with no change on SEPAL's side.

**Notebooks opened in JupyterLab**, and Voila servers that don't load the app's
extensions, use the `jupyter-vuetify` installed with the Jupyter server. The
widgets render only when the server and the kernel have the same ipyvuetify
major, so there the server needs ipyvuetify 3 before pysepal 5 renders.

## What to do

### 1. Pin `pysepal<5` until the app is migrated

Add this to the app's `requirements.txt` (or `pyproject.toml`) now:

```text
pysepal<5
```

Every pysepal 4 release requires `ipyvuetify<3`, so this pin also keeps the app
on ipyvuetify 1.

### 2. Replace the removed widgets

| Removed                                        | Replacement                                                                        |
| ---------------------------------------------- | ---------------------------------------------------------------------------------- |
| `sepalwidgets.vue_app.MapApp.element(...)`     | `pysepal.solara.components.map_app.MapApp(...)` (see below)                        |
| `sepalwidgets.vue_app.ThemeToggle`             | `pysepal.solara.components.map_app.ThemeToggle`                                    |
| `sepalwidgets.vue_app.LocaleSelect`            | `pysepal.solara.components.locale_select.LocaleSelectComponent`                    |
| `sw.FileInput`                                 | `pysepal.solara.components.inputs.FileInputComponent`                              |
| `sw.AssetSelect`                               | `pysepal.solara.components.inputs.AssetSelectComponent`                            |
| `sw.VectorField`                               | `pysepal.solara.components.inputs.VectorSelectorComponent`                         |
| `sw.LoadTableField`                            | `pysepal.solara.components.inputs.PointsSelectorComponent`                         |
| `sw.TaskButton`, `sw.Btn` with a task          | `pysepal.solara.components.task_button.TaskButtonComponent`                        |
| `sw.Alert`, `sw.StateBar`, `sw.Banner`         | `pysepal.solara.notifications` (`NotificationProvider`, `use_notifications`)       |
| `aoi.AoiTile`, `aoi.AoiView`, `AoiControl`     | `pysepal.solara.components.aoi.AoiView`                                            |
| `aoi.select_methods`                           | the `methods` argument of `pysepal.solara.components.aoi.AoiView`                  |
| `planetapi.PlanetView`, `InfoView`, `InfoCard` | `pysepal.planetapi.PlanetModel` with your own Solara form                          |
| `catch_errors`                                 | `try` / `except` in the task, then `notify(...)` from `use_notifications()`        |
| `loading_button`, `thread_controller`          | `TaskButtonComponent` or `solara.lab.use_task`                                     |
| `sw.Tile`, `sw.Card`, other `sw.*` subclasses  | Solara layout (`solara.Card`, `solara.Column`, ...) or plain `solara.v.*` elements |

### 3. Move to the Solara `MapApp`

`MapApp` takes the same keyword arguments as the old `MapApp.element`, except
`model`, `theme_toggle` and `language_selector`. The theme toggle and the
language selector are built in. Instead of `model=`, pass `current_step` with
`on_current_step` and `step_open` with `on_step_open`. Usually the move is just
this change:

```python
# before
from pysepal.sepalwidgets.vue_app import MapApp

MapApp.element(app_title="My app", main_map=[sepal_map], ...)

# after
from pysepal.solara.components.map_app import MapApp

MapApp(app_title="My app", main_map=[sepal_map], ...)
```

[solara-mapapp-component.md](./solara-mapapp-component.md) describes every argument.

### 4. Write the app's own widgets in Vuetify 3

If the app's own code uses `ipyvuetify`, `solara.v` / `rv.*` widgets, or has
its own `.vue` templates, write it for Vuetify 3. The common changes:

| Vuetify 2 (ipyvuetify 1)                                 | Vuetify 3 (ipyvuetify 3)                                                          |
| -------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `dense=True`                                             | `density="compact"`                                                               |
| `small=True`, `x_small=True`, `large=True`               | `size="small"`, `size="x-small"`, `size="large"`                                  |
| button `text=True`, `outlined=True`, `depressed=True`    | `variant="text"`, `variant="outlined"`, `variant="flat"`                          |
| text field with no variant (underlined), `outlined=True` | `variant="underlined"` (the default is now filled), `variant="outlined"`          |
| icon `left=True`, `right=True`                           | `start=True`, `end=True`                                                          |
| `ExpansionPanels(accordion=True)`                        | `ExpansionPanels(variant="accordion")`                                            |
| `ExpansionPanelHeader`, `ExpansionPanelContent`          | `ExpansionPanelTitle`, `ExpansionPanelText`                                       |
| `ListItemContent`, `ListItemIcon`, `ListItemAvatar`      | removed: put the content in `ListItem`, use its `prepend` / `append` slots        |
| `Flex`                                                   | `Col` inside a `Row`                                                              |
| `TabsItems`, `TabItem`                                   | `Window`, `WindowItem`                                                            |
| activator `v_on="x.on"` / `v-on="on"`                    | `v_bind="x.props"` / `v-bind="props"`                                             |
| select items `{"text", "value"}`                         | `{"title", "value"}`; disabled: `{"title", "value", "props": {"disabled": True}}` |
| select `{"header": ...}`, `{"divider": True}`            | `{"type": "subheader", "title": ...}`, `{"type": "divider", "title": ""}`         |
| CSS `.theme--dark`, `.theme--light`                      | `.v-theme--dark`, `.v-theme--light`                                               |
| `beforeDestroy` in a template                            | `beforeUnmount`                                                                   |

A removed class raises `AttributeError` in Python. An unknown prop is dropped
with only a `DeprecationWarning`, and an unknown component in a template shows
up only in the browser console. Check the app in a browser with
`scripts/browser_probe.mjs --console` ([browser-testing.md](./browser-testing.md)). The
rules for `.vue` templates are in [ipyvuetify-widgets.md](./ipyvuetify-widgets.md).

pysepal 5 always runs on ipyvuetify 3, so remove any branch on
`solara.util.IPYVUETIFY_V3` and keep only the Vuetify 3 code.

### 5. Remove the pin

When the app runs on the Solara components and Vuetify 3, require `pysepal>=5`
and remove the `pysepal<5` pin.
