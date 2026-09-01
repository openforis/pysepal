# MapAppComponent — Solara-native MapApp layout

`MapAppComponent` is a first-class Solara component that replaces the
legacy `MapApp(v.VuetifyTemplate)`. It is usable with `with` syntax,
exposes typed dataclass props, auto-wires `ThemeState` and the scope
locale that `pysepal.i18n.current_locale` reads, and preserves the visual
design of the original `MapApp.vue` (drawer, narrow-mode bottom sheet,
dialog steps, right panel).

```{important}
**Availability — not yet shipped.** As of pysepal 3.7.0, `MapAppComponent` and
the `pysepal.solara.components.layout` package are **not present in the released
package**: the `layout` module is empty and `from pysepal.solara import
MapAppComponent` (along with the dataclasses below) raises `ImportError`. The
API documented here is the **planned target** — verify availability with
`python -c "from pysepal.solara import MapAppComponent"` before relying on it.

Until it lands, build the shell with the shipped
`pysepal.sepalwidgets.vue_app.MapApp.element(...)`. Reacton renders nested
Solara elements before they reach `MapApp`'s `List(Instance(DOMWidget))` traits,
so modern `@solara.component` tiles can be passed straight through as step /
panel `content`. The legacy `MapApp` is therefore **not** effectively deprecated
yet — it remains the supported shell until `MapAppComponent` ships.
```

## Quick start

```python
import solara

from pysepal.solara import (
    MapAppComponent,
    NotificationProvider,
    get_current_theme_state,
)
from pysepal.solara.components.layout import (
    ExternalLink,
    PanelSection,
    RightPanelConfig,
    StepConfig,
)


@solara.component
def AoiStep():
    solara.Markdown("AOI selector goes here")


@solara.component
def LayerControls():
    solara.Markdown("Layer toggles go here")


@solara.component
def Page():
    NotificationProvider()
    theme_state = get_current_theme_state()
    sepal_map = use_sepal_map(theme_state=theme_state)  # your own factory

    with MapAppComponent(
        app_title="My App",
        app_icon="mdi-earth",
        sepal_map=sepal_map,
        theme_state=theme_state,
        steps=[
            StepConfig(id=1, name="AOI", icon="mdi-map", content=AoiStep),
        ],
        right_panel_config=RightPanelConfig(title="Tools", width=400),
        right_panel_content=[
            PanelSection(title="Layers", icon="mdi-layers", content=LayerControls),
        ],
        external_links=[ExternalLink("Docs", "https://docs.example")],
    ):
        # Optional children — rendered in a slot above the main map.
        MapToolbar()
```

## Typed props

| Prop                    | Type                              | Purpose                                                                                             |
| ----------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------- |
| `app_title`             | `str`                             | Drawer header text.                                                                                 |
| `app_icon`              | `str`                             | Drawer header MDI icon.                                                                             |
| `sepal_map`             | `Optional[Widget]`                | Map widget rendered in the main area.                                                               |
| `steps`                 | `Sequence[StepConfig]`            | Left-drawer step entries.                                                                           |
| `right_panel_config`    | `Optional[RightPanelConfig]`      | Display config for the right panel chrome.                                                          |
| `right_panel_content`   | `Sequence[PanelSection]`          | Section list rendered inside the right panel.                                                       |
| `right_panel_open`      | `bool` or `solara.Reactive[bool]` | Controlled open/close state.                                                                        |
| `current_step`          | `Optional[int]` reactive          | Controlled active step id.                                                                          |
| `initial_step`          | `Optional[int]`                   | Step auto-activated on first mount.                                                                 |
| `theme_state`           | `Optional[ThemeState]`            | Defaults to `get_current_theme_state()`.                                                            |
| `locales`               | `Optional[Iterable[str]]`         | Codes the locale selector offers. Not a `Translator`: it subclasses `dict`, which reacton flattens. |
| `external_links`        | `Sequence[ExternalLink]`          | Drawer footer link tiles.                                                                           |
| `repo_url` / `docs_url` | `str`                             | Auto-derived Source / Docs / Bug links.                                                             |
| `dialog_width`          | `int`                             | Default width for `display="dialog"` steps.                                                         |
| `dialog_fullscreen`     | `bool`                            | Force dialog steps to render full-screen.                                                           |
| `on_step_action`        | `Callable[[int, str], None]`      | Fires when a dialog footer button is clicked.                                                       |
| `on_right_panel_toggle` | `Callable[[bool], None]`          | Fires when the right panel opens/closes.                                                            |

### `StepConfig.content` is a Solara render function

```python
@solara.component
def AoiStep():
    solara.Markdown("AOI selector goes here")

StepConfig(id=1, name="AOI", content=AoiStep)
```

`content` is invoked only while the step is active. The previous
content's hooks are torn down on deactivation, so resource-heavy
components (maps, GEE asset loaders) do not stay mounted in the
background.

### Right panel sections

```python
PanelSection(
    title="Legend",
    icon="mdi-format-list-bulleted",
    content=LegendComponent,   # @solara.component
    divider=True,
    description="Color ramps for each active layer",
)
```

A section's `content` is always mounted (so its state survives panel
open/close cycles). Use `right_panel_open` if you need to gate work on
panel visibility.

## Migration from the legacy MapApp

| Legacy                                                   | New                                                                                    |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `MapApp.element(main_map=[w], theme_toggle=[t])`         | `MapAppComponent(sepal_map=w, theme_state=state)`                                      |
| `steps_data=[{"id": 1, "name": "...", ...}]`             | `steps=[StepConfig(id=1, name="...", ...)]`                                            |
| `right_panel=[RightPanel(config=..., content_data=...)]` | `right_panel_config=RightPanelConfig(...)` + `right_panel_content=[PanelSection(...)]` |
| `right_panel_content=[{"title": ..., "content": [W]}]`   | `right_panel_content=[PanelSection(title=..., content=fn)]`                            |
| Eager widget construction                                | `content=` is a Solara render function (lazy)                                          |
| Manual `theme_toggle=ThemeToggle(...)` wiring            | Auto: pass `theme_state=` (or omit; falls back to `get_current_theme_state()`)         |
| Manual `language_selector=LocaleSelect(translator=...)`  | Auto: pass `locales=ms.available_locales()` (or omit)                                  |
| `model=HasTraits()` auto-link                            | Use `solara.Reactive` props (`current_step=`, `right_panel_open=`)                     |

## Notifications

Mount `NotificationProvider()` at the page root before the
`MapAppComponent`. Notification UI is automatically positioned to track
the right panel via the CSS variable
`--sepal-notification-right-offset` that the shell publishes.

```python
@solara.component
def Page():
    NotificationProvider()
    MapAppComponent(...)
```

See `docs/guides/solara-notifications.md` for the full notification API.
