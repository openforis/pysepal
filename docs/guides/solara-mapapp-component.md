# MapApp — the Solara map application shell

`pysepal.solara.components.map_app.MapApp` is the shell of a SEPAL map
application:

- a full-screen map;
- a drawer on the left with the steps, the links, the theme toggle and the
  language selector;
- a panel on the right with sections of tools;
- a dialog for dialog steps.

Below 960px of window width the drawer becomes a 60px rail and the panel docks
at the bottom of the window.

It is a plain `@solara.component` built from Solara and Vuetify elements, so it
renders on ipyvuetify 1 (Vuetify 2) and ipyvuetify 3 (Vuetify 3). It replaces
the legacy `pysepal.sepalwidgets.vue_app.MapApp`, a Vue 2 template that is
deprecated with the rest of sepalwidgets (see `sepalwidgets-deprecation.md`).

## Quick start

```python
import solara

from pysepal.solara import get_current_theme_state
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.notifications import NotificationProvider


@solara.component
def Page():
    NotificationProvider()
    theme_state = get_current_theme_state()
    sepal_map = use_sepal_map(theme_state)  # your own hook; see the demo apps

    MapApp(
        app_title="My App",
        app_icon="mdi-earth",
        main_map=[sepal_map],
        theme_state=theme_state,
        locales=messages.available_locales(),
        right_panel_config={"title": "Tools", "icon": "mdi-tools", "width": 400},
        right_panel_content=[
            {"title": "Area of interest", "icon": "mdi-map-marker", "content": AoiStep()},
            {"title": "Layers", "icon": "mdi-layers", "content": [LayerControls()]},
        ],
        right_panel_open=True,
        repo_url="https://github.com/sepal-contrib/my-app",
    )
```

`demo_apps/solara_map_app/app.py` is a complete app built this way.

## Arguments

| Argument                | Purpose                                                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------------------------------- |
| `app_title`, `app_icon` | Title and MDI icon at the top of the drawer.                                                                    |
| `main_map`              | The map widget, or a one-item list holding it (see "The map" below).                                            |
| `steps_data`            | The drawer steps (see "Steps").                                                                                 |
| `right_panel_config`    | `title`, `icon`, `width` (px), `description` and `toggle_icon` of the right panel.                              |
| `right_panel_content`   | The panel sections: `title`, `icon`, `description`, `content`, `divider`. No section, no panel.                 |
| `right_panel_footer`    | Elements or widgets pinned below the sections, e.g. an action bar.                                              |
| `right_panel_open`      | Whether the panel starts open. A later change opens or closes it.                                               |
| `on_right_panel_open`   | Called with the new state when the user opens or closes the panel.                                              |
| `initial_step`          | The step to open on mount, if it can show (it has content and its `display` is `"step"` or `"dialog"`).         |
| `current_step`          | The active step. A later change activates that step; `None` shows the map.                                      |
| `on_current_step`       | Called with the step the user activates (`None` when they go back to the map).                                  |
| `step_open`             | A later change to `False` closes the step dialog, to `True` reopens it.                                         |
| `on_step_open`          | Called when a step opens or closes.                                                                             |
| `is_pinned`             | Whether the drawer starts pinned open. An unpinned drawer starts as a rail and collapses on a click on the map. |
| `theme_state`           | The `ThemeState` the toggle and the map follow; defaults to the current scope's.                                |
| `locales`               | The locale codes the language selector offers, normally `messages.available_locales()`.                         |
| `repo_url`              | Target of the Source Code and Report Bug links; empty hides both.                                               |
| `docs_url`              | Target of the Documentation link; empty hides it.                                                               |
| `dialog_width`          | Default width of dialog steps, in px or `"NN%"` of the window.                                                  |
| `dialog_fullscreen`     | Show dialog steps full screen.                                                                                  |

A `content` is an element (`AoiView(...)`), a widget, or a list of them.

The shell owns its state. A parent that passes `current_step`,
`right_panel_open` or `step_open` on every render does not reset what the user
did. Only a change of the value is an instruction. To follow the user, pass the
matching `on_*` callback and keep the value in a reactive.

## Steps

Each entry of `steps_data` is a dict:

| Key                  | Meaning                                                                                                                                                        |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                 | Unique id, reported through `on_current_step`.                                                                                                                 |
| `name`, `icon`       | Label and MDI icon in the drawer.                                                                                                                              |
| `display`            | `"step"` replaces the map with the content. `"dialog"` opens the content in a dialog. Any other value shows nothing, but a click still reports `current_step`. |
| `content`            | What the step shows. A step without content only runs its `right_panel_action`.                                                                                |
| `content_enabled`    | `False` keeps the step from being highlighted or opened on mount.                                                                                              |
| `right_panel_action` | `"open"`, `"close"` or `"toggle"` the right panel when the step is clicked.                                                                                    |
| `actions`            | Dialog footer buttons: `label`, `cancel` (outlined style), `close` (closes the dialog), `next` (moves to that step id).                                        |
| `width`, `height`    | Size of a dialog step, in px or `"NN%"` of the window.                                                                                                         |

All step and section contents stay mounted. The shell only hides the ones that
are not shown, so a form keeps what the user typed when they leave the step and
come back. On mount, the shell opens the step named by `current_step` or
`initial_step`. If there is no map and no such step, it opens the first step
that can show.

## The map

The map fills the window behind the drawer and the panel. When the map widget
has these attributes, the shell keeps them up to date:

- `viewport_inset_left`, `viewport_inset_right`, `viewport_inset_bottom`: the
  width of the drawer and of the open panel, and the height of the docked
  panel. `SepalMap` uses them so that `zoom_bounds` fits the visible part of the
  map.
- `canvas_width_px`, `canvas_height_px`: the window size.
- `bind_theme_state(theme_state)`: the map's basemap and its controls follow the
  theme.

`SepalMap` has all of these. The Leaflet controls move out from under the
drawer and the panel.

## Theme and language

The drawer footer holds a `ThemeToggle` and a `LocaleSelectComponent`, both
built in. The toggle cycles dark → light → auto:

- It writes the mode to `theme_state.mode`, and the result to
  `theme_state.dark` and to Solara's theme.
- `auto` follows the browser's colour-scheme preference.
- The browser remembers the mode for the next visit.

`ThemeToggle` can also be used on its own:
`from pysepal.solara.components.map_app import ThemeToggle`.

## Floating components

The shell publishes its geometry as CSS variables on the page root:

- `--sepal-drawer-width`
- `--sepal-right-panel-width`
- `--sepal-right-panel-open`
- `--sepal-notification-right-offset`
- `--sepal-bottom-reserved`

While a step dialog is open, the shell also puts the class `sepal-modal-open` on
`body`.

The legend and the notifications use these to stay clear of the panels, so mount
`NotificationProvider()` and the legend next to the shell and they follow it.

## Moving from the legacy MapApp

| Legacy                                                 | Native                                                              |
| ------------------------------------------------------ | ------------------------------------------------------------------- |
| `from pysepal.sepalwidgets.vue_app import MapApp`      | `from pysepal.solara.components.map_app import MapApp`              |
| `MapApp.element(...)`                                  | `MapApp(...)`, same keyword arguments                               |
| `model=HasTraits()`                                    | `current_step` / `on_current_step` and `step_open` / `on_step_open` |
| `theme_toggle=`, `language_selector=`                  | built in; pass `theme_state=` and `locales=`                        |
| content built as widgets to keep their click handlers  | elements work too, e.g. `solara.Button(..., on_click=...)`          |
| observing the widget's `right_panel_open`, `step_open` | `on_right_panel_open`, `on_step_open`                               |
