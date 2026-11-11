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
  - `pysepal.scripts.thread_controller`.
- The `theme_toggle` argument of `SepalMap`: the `ThemeToggle` it took no
  longer exists. Pass `theme_state=` instead; the Solara `MapApp` binds it for
  you.
- The `catch_errors` and `loading_button` decorators in
  `pysepal.scripts.decorator`, and their old aliases in `pysepal.scripts.utils`.
- The `module_factory` command and the `pysepal/templates` scaffolds it copied.
- The `sepal_ipyvuetify` command, which generated the sepalwidgets classes.

An old import now fails with a message that points here:

- `import pysepal.sepalwidgets` raises an `ImportError`;
- `pysepal.aoi.AoiView` and the other removed names raise an `AttributeError`
  that names the replacement.

These stay:

- `pysepal.solara` and its components, including `MapApp`;
- `SepalMap` and the map controls;
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

## Why

- Vue 2 reached its end of life on 2023-12-31, and Vuetify 2 depends on it.
- Since August 2026, `pip install solara` installs ipyvuetify 3. Solara 2 will
  support Vuetify 3 only (widgetti/solara#1163).
- Supporting both majors doubled the work on every widget. The Solara
  components are where pysepal's UI work goes.

## Who is affected

**Solara apps** (`solara run`, the SEPAL container apps) ship their own
frontend. They can move to pysepal 5 as soon as their code is ready.

**Voila apps on SEPAL** are rendered by SEPAL's Jupyter server. That server has
one `jupyter-vuetify` frontend for every app, and a widget renders only when the
app's kernel has the same ipyvuetify major. Today that frontend is ipyvuetify 1.
So every Voila app on SEPAL must stay on pysepal 4 for now, whether or not it
uses sepalwidgets. The same rule holds for any Jupyter server: its own
ipyvuetify must be 3 before an app on pysepal 5 renders there.

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
and remove the `pysepal<5` pin. A Voila app on SEPAL does this only after the
server switch below.

## The SEPAL server switch

SEPAL's maintainers will move SEPAL's Jupyter server to ipyvuetify 3, and will
ask app owners to upgrade their Voila apps first. After the switch:

- a Voila app on pysepal 5 (or any other ipyvuetify 3 stack) renders;
- a Voila app still on pysepal 4 or ipyvuetify 1 starts, but its widgets do not
  render.

Solara apps are not affected by the switch: they ship their own frontend.
