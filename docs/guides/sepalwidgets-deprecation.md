# sepalwidgets is deprecated (pysepal 4.2)

pysepal 4.2 runs on **ipyvuetify 1** (Vuetify 2, Vue 2) and on **ipyvuetify 3**
(Vuetify 3, Vue 3). The Solara layer, `pysepal.mapping`, and the models work on
both. `pysepal.sepalwidgets`, the ipyvuetify widget layer, works only on
ipyvuetify 1. It is deprecated and will be removed in pysepal 5.0.

## What is deprecated

- `pysepal.sepalwidgets`: every `sw.*` widget, including the ipyvuetify
  subclasses (`sw.Btn`, `sw.Card`, `sw.Tile`, ...).
- The widgets built on it:
  - `MapApp`, `ThemeToggle`, `RightPanel` and `LocaleSelect` in
    `pysepal.sepalwidgets.vue_app`;
  - `pysepal.aoi.AoiTile` and `pysepal.aoi.AoiView`;
  - `pysepal.planetapi.PlanetView`, `InfoView` and `InfoCard`;
  - `pysepal.mapping.AoiControl`;
  - `pysepal.scripts.thread_controller`.
- The `module_factory` templates. They still scaffold a sepalwidgets app.

What it means in practice:

- With ipyvuetify 1, importing `pysepal.sepalwidgets` still works and emits a
  `DeprecationWarning`.
- With ipyvuetify 3, it raises an `ImportError` that says what to do.

These keep working on both majors:

- `pysepal.solara` and its components;
- `SepalMap` and the map controls;
- `AoiModel` and `PlanetModel`.

## Why

- Vue 2 reached its end of life on 2023-12-31, and Vuetify 2 depends on it.
- Since August 2026, `pip install solara` installs ipyvuetify 3. While pysepal
  capped ipyvuetify below 3, no package that needs ipyvuetify 3 could be
  installed next to pysepal.
- Solara 2 will support Vuetify 3 only (widgetti/solara#1163).
- Keeping two versions of every widget would double the work on each one. The
  Solara components are where pysepal's UI work goes.

## What to do now

### Voila apps on SEPAL: pin ipyvuetify 1

SEPAL's Jupyter server provides one `jupyter-vuetify` frontend for every Voila
app, and a widget only renders when its kernel has the same ipyvuetify major.
Until SEPAL moves that server to ipyvuetify 3, a Voila app must stay on
ipyvuetify 1. This is true whether or not the app uses sepalwidgets.

Add this line to the app's `requirements.txt` **now**:

```text
ipyvuetify<3
```

Without it, the next venv rebuild after pysepal 4.2 installs ipyvuetify 3:

- an app that uses sepalwidgets stops at the `ImportError`;
- any other app starts, but its widgets do not render.

### Solara apps: move to the Solara components

A Solara app ships its own frontend, so it can run on either major. To move it:

1. Replace each legacy widget with the Solara component in the table below.
2. Remove the `ipyvuetify<3` pin, or keep it until the app's own code is ready.

| Legacy                                        | Solara replacement                                                                 |
| --------------------------------------------- | ---------------------------------------------------------------------------------- |
| `sepalwidgets.vue_app.MapApp.element(...)`    | `pysepal.solara.components.map_app.MapApp(...)` (see below)                        |
| `sepalwidgets.vue_app.ThemeToggle`            | `pysepal.solara.components.map_app.ThemeToggle`                                    |
| `sepalwidgets.vue_app.LocaleSelect`           | `pysepal.solara.components.locale_select.LocaleSelectComponent`                    |
| `sw.FileInput`                                | `pysepal.solara.components.inputs.FileInputComponent`                              |
| `sw.AssetSelect`                              | `pysepal.solara.components.inputs.AssetSelectComponent`                            |
| `sw.VectorField`                              | `pysepal.solara.components.inputs.VectorSelectorComponent`                         |
| `sw.LoadTableField`                           | `pysepal.solara.components.inputs.PointsSelectorComponent`                         |
| `sw.TaskButton`, `sw.Btn` with a task         | `pysepal.solara.components.task_button.TaskButtonComponent`                        |
| `sw.Alert`, `sw.StateBar`, `sw.Banner`        | `pysepal.solara.notifications` (`NotificationProvider`, `use_notifications`)       |
| `aoi.AoiTile`, `aoi.AoiView`                  | `pysepal.solara.components.aoi.AoiView`                                            |
| `sw.Tile`, `sw.Card`, other `sw.*` subclasses | Solara layout (`solara.Card`, `solara.Column`, ...) or plain `solara.v.*` elements |

`MapApp` takes the same keyword arguments as the legacy `MapApp.element`, except
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

`docs/guides/solara-mapapp-component.md` describes every argument.

If the app's own code uses `ipyvuetify` or `solara.v` widgets, or has its own
`.vue` templates, that code must also work on the major the app installs:

- Vuetify 3 renamed props, for example `dense` → `density`, `outlined` /
  `text` → `variant`, `small` → `size`.
- It removed some components, for example `v-list-item-content`, `v-flex` and
  `v-tabs-items`.
- Activator slots bind `props` instead of `on`.

Solara branches on `solara.util.IPYVUETIFY_V3` and so does pysepal. Keep the
`ipyvuetify<3` pin until that code is ready.

## Timeline

- **4.2.0**: sepalwidgets deprecated. pysepal supports both ipyvuetify majors.
- **5.0.0**: sepalwidgets and the widgets built on it are removed. This happens
  once SEPAL's Voila server runs ipyvuetify 3, or once SEPAL modules no longer
  use Voila.
