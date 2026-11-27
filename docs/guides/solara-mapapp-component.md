# MapApp — the Solara map application shell

`pysepal.solara.components.map_app.MapApp` is the shell of a SEPAL map
application:

- a full-screen map;
- a drawer on the left with the steps, the links, the theme toggle and the
  language selector;
- a panel on the right with sections of tools;
- a dialog for dialog steps.

Below 960px of window width the drawer becomes a bar across the top: the app
title, the map, steps and links as icons, and the theme and language buttons at
the right end. The entries that do not fit go into a menu at the end of the row.
The panel docks at the bottom of the window, opened by its tab, and the task
pill and its logger hide.

It is a plain `@solara.component` built from Solara and Vuetify 3 elements. It
replaces the Vue 2 `pysepal.sepalwidgets.vue_app.MapApp`, removed in pysepal 5
with the rest of sepalwidgets (see `migrating-to-pysepal-5.md`).

## Quick start

```python
import solara

from pysepal.mapping import SepalMap
from pysepal.solara import get_current_theme_state, use_sepal_map
from pysepal.solara.components.aoi import AoiView
from pysepal.solara.components.layer_panel import LayerPanel
from pysepal.solara.components.map_app import MapApp
from pysepal.solara.notifications import NotificationProvider

from component.message import messages  # the app's own catalog


@solara.component
def Page():
    NotificationProvider()
    theme_state = get_current_theme_state()
    sepal_map = use_sepal_map(lambda: SepalMap(gee=False, theme_state=theme_state), [])
    aoi = solara.use_reactive(None)

    MapApp(
        app_title="My App",
        app_icon="mdi-earth",
        main_map=[sepal_map],
        theme_state=theme_state,
        locales=messages.available_locales(),
        right_panel_config={"title": "Tools", "icon": "mdi-tools", "width": 400},
        right_panel_content=[
            {
                "title": "Area of interest",
                "icon": "mdi-map-marker",
                "content": AoiView(value=aoi, map_=sepal_map, gee=False),
            },
            {
                "title": "Layers",
                "icon": "mdi-layers",
                "content": LayerPanel(sepal_map.layer_store, map_=sepal_map),
            },
        ],
        right_panel_open=True,
        repo_url="https://github.com/sepal-contrib/my-app",
    )
```

[A whole app](./solara-map-apps.md#a-whole-app) adds Earth Engine work with
progress to this shell, and `demo_apps/solara_map_app/app.py` is a complete app
built this way.

## Arguments

| Argument                | Purpose                                                                                                                                                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `app_title`, `app_icon` | Title and MDI icon at the top of the drawer.                                                                                                                                                                         |
| `main_map`              | The map widget, or a one-item list holding it (see "The map" below).                                                                                                                                                 |
| `steps_data`            | The drawer steps (see "Steps").                                                                                                                                                                                      |
| `right_panel_config`    | `title`, `icon`, `width` (px as a number, `"300"` or `"300px"`), `description` and `toggle_icon` of the right panel.                                                                                                 |
| `right_panel_content`   | The panel sections: `title`, `icon`, `description`, `content`, `divider`. No section, no panel.                                                                                                                      |
| `right_panel_footer`    | Elements or widgets pinned below the sections, e.g. an action bar.                                                                                                                                                   |
| `right_panel_open`      | Whether the panel starts open. A later change opens or closes it.                                                                                                                                                    |
| `on_right_panel_open`   | Called with the new state when the user opens or closes the panel.                                                                                                                                                   |
| `initial_step`          | The `id` of the step to open on mount, if it can show (it has content and its `display` is `"step"` or `"dialog"`).                                                                                                  |
| `current_step`          | The `id` of the active step. A later change activates that step, unless it has no content; `None` shows the map.                                                                                                     |
| `on_current_step`       | Called with the `id` of the step the user activates, `None` when they go back to the map or close the dialog.                                                                                                        |
| `step_open`             | Dialog steps only: a later change to `False` closes the step dialog, to `True` reopens it. To leave a `"step"` step, set `current_step=None`.                                                                        |
| `on_step_open`          | Called with `True` when the user opens any step with content, and `False` when they go back to the map or close the dialog.                                                                                          |
| `is_pinned`             | Whether the drawer starts pinned open. An unpinned drawer starts as a rail and collapses on a click on the map.                                                                                                      |
| `theme_state`           | The `ThemeState` the toggle and the map follow; defaults to the current scope's.                                                                                                                                     |
| `locales`               | The locale codes the language selector offers, normally `messages.available_locales()`. `None` offers English only.                                                                                                  |
| `repo_url`              | Target of the Source Code and Report Bug links; empty hides both.                                                                                                                                                    |
| `docs_url`              | Target of the Documentation link; empty hides it.                                                                                                                                                                    |
| `dialog_width`          | Default width of dialog steps, in the forms of a step's `width`. 800 when it does not read as a size.                                                                                                                |
| `dialog_fullscreen`     | Show dialog steps full screen.                                                                                                                                                                                       |
| `map_overlays`          | Elements or widgets to stack over the map by corner (`"top-left"`, `"top-right"`, `"bottom-left"`, `"bottom-right"`), as `MapView(overlays=)` takes them. Used when the map has a `layer_store`, as `SepalMap` does. |

A `content` is an element (`AoiView(...)`), a widget, or a list of them.

The shell owns its state. A parent that passes `current_step`,
`right_panel_open` or `step_open` on every render does not reset what the user
did. Only a change of the value is an instruction. To follow the user, pass the
matching `on_*` callback and keep the value in a reactive.

## Steps

Each entry of `steps_data` is a dict:

| Key                  | Meaning                                                                                                                                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                 | Unique id, reported through `on_current_step`. Steps that share an id or have none still work, but report an id the parent cannot tell apart.                                                                    |
| `name`, `icon`       | Label and MDI icon in the drawer.                                                                                                                                                                                |
| `display`            | `"step"` replaces the map with the content. `"dialog"` opens the content in a dialog. Any other value shows nothing, but a click on a step with content still reports `current_step`.                            |
| `content`            | What the step shows. A step without content only runs its `right_panel_action`.                                                                                                                                  |
| `content_enabled`    | `False` keeps the step from being highlighted and from opening as `initial_step`. A click or `current_step` still opens it.                                                                                      |
| `right_panel_action` | `"open"`, `"close"` or `"toggle"` the right panel when the step is clicked.                                                                                                                                      |
| `actions`            | Dialog footer buttons: `label`, `cancel` (outlined style), `close` (closes the dialog), `next` (moves to that step id; a step without content closes the dialog instead).                                        |
| `width`, `height`    | Size of a dialog step: px as a number, `"600"` or `"600px"`, or `"NN%"` of the window. A `width` that does not read falls back to `dialog_width`; a `height` that does not read lets the dialog fit its content. |

All step and section contents stay mounted. The shell only hides the ones that
are not shown, so a form keeps what the user typed when they leave the step and
come back. On mount, the shell opens the step named by `current_step` if it
has content, else `initial_step`. If there is no map and no such step, it opens
the first step that can show.

## The map

The map fills the window behind the drawer and the panel. In a narrow window it
stops above the band kept for the docked panel, 45 % of the window, even while
the panel is closed. When the map widget has these methods, the shell calls
them:

- `set_insets(left=..., right=...)`: in a wide window, the width of the drawer
  and of the open panel, which overlap the map. In a narrow window all insets
  are 0: the map already sits below the top bar and above the docked panel.
  `SepalMap` fits and centers inside what the insets leave, and moves its
  controls out from under the drawer and the panel. The map itself stays where
  it is when the drawer or the panel opens or closes.
- `bind_theme_state(theme_state)`: the map's basemap and its controls follow the
  theme.

`SepalMap` has both. A replaced map gets the current insets at once.

Build the map with `pysepal.solara.use_sepal_map(factory, dependencies)` in the
component that renders `MapApp`, as in the quick start. It builds the map once
(again when a dependency changes) and closes it on unmount, on a dependency
change and on a hot reload. Solara closes only the widgets it built from
elements, so a map built in `solara.use_memo` alone stays alive until the
kernel closes. The component that builds a map closes it; `MapApp`, `MapView`
and the other components it is passed to never do. The other rules for map
code are in [Best practices for map apps](./solara-map-apps.md).

`MapView`, which `MapApp` builds around the map, stacks the overlays of each
corner (`map_overlays`) inside the insets and 10 px past the map's controls in
that corner. The browser measures the controls, so a stack moves when the draw
toolbar or the coordinates readout comes or goes. The stacks stay hidden until
the map has measured them.

`MapView` also shows a legend card centred at the bottom of the map, between
the bottom controls, or above them in a compare (`MapView(legend=False)` turns
it off):

- It lists the visible layers that have a legend, top first, and shows one: the
  top one until the user picks one in its dropdown. A layer added after the
  view mounted is shown at once, as if picked. While the picked layer is hidden,
  the card shows the top one, and it shows the pick again when the layer comes
  back.
- The card follows the map's insets, so it stays centred between the drawer
  and the panel, and in fullscreen it centres on the whole screen. Its bar sits
  on the same line as the attribution; an open card on a narrow map can cover
  the scale and the attribution until it is closed. In a compare, the cards sit
  above the bottom controls.
- A long legend scrolls inside the card, which takes at most 40 % of the map's
  height. In an area narrower than 140 px only the card's bar shows, with the
  layer's name, and in one narrower than 60 px nothing.

### The inspector, and the draw toolbar the map draws

Two tools sit at the top left of the map:

- **The draw toolbar** is the map's own: the browser draws it below the zoom,
  fullscreen and globe controls while a drawing session offers tools
  (`m.draw.begin(...)`), with one button per tool and a button that removes
  every shape. `AoiView` begins a session for its DRAW method. The browser
  holds the active tool, so each view of the map has its own, and a click
  never waits for Python. `session.start(mode)` and `session.stop()` ask every
  view that shows the session for a tool. The labels follow the app's
  language: `SepalMap` sets them from pysepal's messages, and `MapView` sets
  them again when the language changes.
- **The inspector** has a toggle and, after a click, a card with the values of
  every visible layer at that point. It exists only for `SepalMap(inspector=True)`.
  A layer that changed between the click and the read shows "this layer
  changed, click again". `MapView`, which `MapApp` builds around the map,
  shows it below the draw toolbar and follows the map, so every `MapView` of
  one map shows the same state.

### Compare mode

`m.compare = True` turns the map into a swipe compare: a divider splits it, the
left half draws the `left` and `both` layers and the right half the `right` and
`both` ones. Outside compare every layer is drawn, whatever its side.

- **Sides.** The layer methods take `side=` (`"left"`, `"right"` or `"both"`,
  the default): `m.add_ee_layer(image, side="left")`, and the same on
  `add_raster` and their async forms. `handle.side = "right"` moves a layer
  that is already on the map.
- **The panel button.** While the map compares, each row of the `LayerPanel`
  (built with `map_=m`) shows a side button. It follows the map's state, so it
  appears by itself, and a click cycles left, both, right and back to left.
- **The switch is the app's.** The panel has no compare switch: an app that
  wants one adds its own, such as a `solara.Switch` whose `on_value` sets
  `m.compare`.
- **A legend per half.** While the map compares, `MapView` shows two legend
  cards, each centred on its half and following the divider as it moves. The
  left card lists the `left` and `both` layers, the right card the `right` and
  `both` ones. Each half keeps its own pick and collapse, and the left half
  continues the whole map's card when compare turns on, and back.

## Theme and language

The drawer footer holds a `ThemeToggle` and a `LocaleSelectComponent`, both
built in. The toggle cycles dark → light → auto:

- It writes the mode to `theme_state.mode`, and the result to
  `theme_state.dark` and to Solara's theme.
- `auto` follows the browser's colour-scheme preference.
- The browser remembers the mode for the next visit, and applies it when the
  toggle mounts, over a mode the app set before.

`ThemeToggle` can also be used on its own:
`from pysepal.solara.components.map_app import ThemeToggle`.

## Floating components

The shell publishes its geometry as CSS variables on the page root:

- `--sepal-drawer-width`
- `--sepal-right-panel-width`
- `--sepal-right-panel-open`
- `--sepal-notification-right-offset`
- `--sepal-notification-pill-display` (`none` on a narrow window)
- `--sepal-top-reserved` (the height of the top bar on a narrow window)
- `--sepal-bottom-reserved`

While a step dialog is open, the shell also puts the class `sepal-modal-open` on
`body`.

The notifications use these to stay clear of the panels, so mount
`NotificationProvider()` next to the shell and they follow it. Do not mount a
`LegendComponent` over a `MapApp`: `MapView` already shows each layer's legend,
in the same place.

## Moving from the removed Vue MapApp

| pysepal 4 (Vue MapApp)                                 | pysepal 5                                                                          |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| `from pysepal.sepalwidgets.vue_app import MapApp`      | `from pysepal.solara.components.map_app import MapApp`                             |
| `MapApp.element(...)`                                  | `MapApp(...)`, same keyword arguments but the three below, which raise `TypeError` |
| `model=HasTraits()`                                    | `current_step` / `on_current_step` and `step_open` / `on_step_open`                |
| `theme_toggle=`, `language_selector=`                  | built in; pass `theme_state=` and `locales=`                                       |
| content built as widgets to keep their click handlers  | elements work too, e.g. `solara.Button(..., on_click=...)`                         |
| observing the widget's `right_panel_open`, `step_open` | `on_right_panel_open`, `on_step_open`                                              |
