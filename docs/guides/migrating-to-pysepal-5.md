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
    exports it);
  - `pysepal.mapping.LayersControl` and the `pysepal.mapping.layers_control`
    module (see [LayersControl → LayerPanel](#layerscontrol--layerpanel));
  - `pysepal.scripts.thread_controller`.
- The `theme_toggle` argument of `SepalMap`: the `ThemeToggle` it took no
  longer exists. Pass `theme_state=` instead; the Solara `MapApp` binds it for
  you.
- The `catch_errors` and `loading_button` decorators in
  `pysepal.scripts.decorator`, and their old aliases in `pysepal.scripts.utils`.
- The `module_factory` command and the `pysepal/templates` scaffolds it copied.
- The `sepal_ipyvuetify` command, which generated the sepalwidgets classes.

An old import now fails with a message that points here:

- `import pysepal.sepalwidgets`, `import pysepal.mapping.layers_control` and
  the modules of the removed map controls (see
  [Map controls](#map-controls)) raise an `ImportError`;
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
  `add_ee_layer` and `add_ee_layer_async` keep their arguments and return
  values. The layer's id in the store is `key`, or the normalized layer name
  when `key` is empty. A hidden layer of the store is off `m.layers`, but
  `find_layer` and `remove_layer` still find it by key or name, and
  `remove_all` removes it.
- **The same key replaces the layer in place.** Adding a layer whose key is
  already in the store replaces it and keeps its position, visibility and
  opacity. Without a `key`, the key is the normalized name, so two calls with
  the same name replace each other: `add_raster` no longer adds three random
  letters to a name already in use. A call with neither a name nor a key gets a
  new `Layer N` name and its own layer. When an `*_async` call is overtaken by
  a newer action on the same key (another add, a removal, a restyle in the
  panel), the newer one wins. `add_raster_async` then returns `None`.
- **`add_layer` stays unmanaged.** A layer added with `add_layer` is drawn as
  before, but it is not in the store, so the panel does not list it. A tile
  layer added without a `pane` is drawn in the overlay pane, above every layer of
  the store. `add_ee_layer(..., overlay=True)` does the same for an Earth Engine
  layer: the AOI is drawn that way.
- **The store drives visibility and opacity.** Setting `.visible` or
  `.opacity` on a layer that `find_layer` returns no longer drives a layer of
  the store. A layer added with `shown=False` is off the map, so
  `layer.visible = True` shows nothing. Call
  `m.layer_store.set_visible(key, True)` and
  `m.layer_store.set_opacity(key, 0.5)` instead.
- **`layer.ee_object` is rebuilt.** An Earth Engine layer keeps its object as a
  serialized expression, and `ee_object` is rebuilt from it: it is equivalent
  to the object you passed, but not the same Python object.
- **Earth Engine colours are normalised** to `#rrggbb`. The alpha of an
  8-digit `fillColor` becomes the fill opacity, but an `RRGGBBAA` `color` (the
  stroke) or palette entry loses its alpha. Use a 6-digit colour, and
  `fill_opacity` for a see-through fill.
- **No layer or basemap switcher on the map.** Without the old in-map control,
  users switch layers and basemaps only where the app shows a `LayerPanel`. In
  a `MapApp`, add it as a right panel section:

  ```python
  from pysepal.solara.components.layer_panel import LayerPanel

  right_panel_content = [
      {"title": "Layers", "icon": "mdi-layers", "content": LayerPanel(store=m.layer_store, map_=m)},
  ]
  ```

  In a notebook or a Voila app, display it next to the map:

  ```python
  from pysepal.solara.components.layer_panel import LayerPanel

  solara.display(m, LayerPanel(store=m.layer_store, map_=m))
  ```

### Map controls

The draw, inspector, zoom, fullscreen, state bar, menu and legend controls only
attach to an ipyleaflet map, so they are removed, and `SepalMap` loses the
arguments and members that built them. `SepalMap` keeps ipyleaflet's own zoom
(and fullscreen, with `fullscreen_control=True`) controls for now. Their modules
raise an `ImportError`, their names in `pysepal.mapping` and the removed
`SepalMap` members raise an `AttributeError`. `m.state` no longer means the state
bar.

| Removed                                                                                  | Replacement                                               |
| ---------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `ZoomControl`, `FullScreenControl`                                                       | the map draws its own zoom, scale and fullscreen controls |
| `LayerStateControl`, `SepalMap(statebar=...)`, `m.state`                                 | `MapView` shows layer loading                             |
| `LegendControl`, `m.add_legend`, `m.add_colorbar`                                        | the `MapView` legend, built from each layer's legend      |
| `MenuControl`                                                                            | Solara components in `MapView(overlays=...)`              |
| `DrawControl`, `GeomanDrawControl`, `SepalMap(dc=...)`, `m.dc`, `m.show_dc`, `m.hide_dc` | being rebuilt on the MapLibre map                         |
| `InspectorControl`, `ValueInspector`, `SepalMap(vinspector=...)`, `m.v_inspector`        | being rebuilt on the MapLibre map                         |

Until drawing is back, `AoiView` offers DRAW only for a map that has a draw
control, so a `SepalMap` has no DRAW method.

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
