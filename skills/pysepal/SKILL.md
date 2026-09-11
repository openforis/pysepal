---
name: pysepal
description: Use when working with pysepal Solara components, debugging pysepal/Solara/GEE errors, auditing pysepal-based apps for stale patterns, or before modifying any code that imports from pysepal. Covers component discovery, GEE async patterns, translations with catalog() and msg(), known error fixes, and Solara best practices.
---

# pysepal

Expertise skill for developing with pysepal — the Python library for
ipyvuetify/Solara dashboards on SEPAL. Provides component discovery, GEE
patterns, error diagnosis, and Solara best practices.

## Modes

Invoke as `/pysepal` (knowledge), `/pysepal diagnose` (error matching),
or `/pysepal audit` (stale pattern check).

> Path conventions: paths in this skill without a leading `~` or `/` are
> relative to the pysepal repo root (e.g. `docs/guides/...`,
> `pysepal/templates/...`). When working in another project, substitute the
> path of your local pysepal checkout.

## Source of truth

This skill is the source of truth for how to build a pysepal app. The package
documentation under `docs/` lags behind the code: the Voila tutorials,
`sw.App` + `ui.ipynb`, `Translator` attribute lookups, and the
`MapAppComponent` guide are out of date. Read a guide for depth. When a document
and this skill disagree, follow the skill and treat the document as stale.

Two rules come before everything else:

- An application is a `@solara.component`, and `MapApp.element(...)` is its
  shell. Never build the shell with the plain `MapApp(...)` constructor.
- Every user-facing string comes from a JSON catalogue through `msg()`. See
  "Translations" below.

## Before Anything: Discover Components

Never assume which pysepal components exist. Run discovery first from the
pysepal repo root:

```bash
python skills/pysepal-app/scripts/discover_pysepal_components.py \
  --repo-root .
```

Use the output as the only source of truth for component names and import
paths. If the script fails, ask the user for the correct pysepal repo path.

## GEE Async Pattern (Session-Backed)

Full reference: `docs/guides/solara-gee-patterns.md`

```python
# Get the session-backed interface
gee_interface = get_current_gee_interface()

# Call async methods directly — no asyncio.to_thread for GEE
result = await gee_interface.get_info_async(ee_object)
assets = await gee_interface.get_assets_async(folder)
asset  = await gee_interface.get_asset_async(asset_id)
map_id = await gee_interface.get_map_id_async(image, vis)

# use_task must keep coroutines on Solara's loop
@solara.lab.use_task(dependencies=None, raise_error=False, prefer_threaded=False)
async def gee_job(request):
    return await gee_interface.get_info_async(request.ee_object)
```

**Rules:**

- `prefer_threaded=False` on all GEE `use_task` hooks
- `await gee_interface.*_async(...)` for all Earth Engine calls
- `asyncio.to_thread(...)` only for non-GEE blocking work (file I/O, CPU)
- Pass the same `gee_interface` instance down to child components and `SepalMap`

## Solara Component Rules

### When to use Vue vs pure Solara

For complex layout (responsive positioning, CSS variables, animations,
viewport-aware sizing), use Vue templates — not `rv.*` elements. Solara
itself recommends this: _"It can be beneficial for performance, since
instead of creating many widgets from the Python side we only send data
to the frontend."_

Two patterns:

- `@solara.component_vue("Widget.vue")` — auto-generates traitlets from
  the function signature. Preferred for new widgets.
- `v.VuetifyTemplate` subclass + `.element()` — more control, used by
  existing pysepal widgets (MapApp, FileInput, TaskButton).

For simple inputs, buttons, state display — use `@solara.component` with
`rv.*` elements (cheaper, testable in pure Python).

Read `docs/guides/ipyvuetify-widgets.md` for the full
guide with examples of both approaches.

### rv. vs v. inside context managers

Inside `with rv.Something():`, always use `rv.Widget(...)`. Using
`v.Widget(...)` silently produces nothing — no error, empty DOM.

```python
# WRONG — invisible
with rv.CardActions():
    v.Btn(children=["OK"])

# CORRECT
with rv.CardActions():
    rv.Btn(children=["OK"])
```

### No solara.Column inside rv. containers

`solara.Column` captures children into its own tree, detaching them from
the `rv.` parent.

```python
# WRONG — CardText stays empty
with rv.CardText():
    with solara.Column():
        rv.Select(...)

# CORRECT
with rv.CardText():
    rv.Select(...)
```

### MapApp layout

All map-based pysepal apps use `MapApp.element()` as the layout shell.
Do not build custom `solara.Columns` layouts. Steps and panel sections are
plain dicts; both `content` lists accept ipyvuetify widgets _and_ Solara
elements, so `@solara.component` tiles can be passed straight through.

```python
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import get_current_theme_state

# Scope-keyed theme state — no manual ThemeToggle wiring needed
theme_state = get_current_theme_state()
sepal_map = SepalMap(fullscreen=True, theme_state=theme_state, gee=True)

MapApp.element(
    app_title="My App",
    app_icon="mdi-earth",
    main_map=[sepal_map],
    steps_data=[
        {"id": 1, "name": "AOI", "icon": "mdi-map",
         "display": "step",  # or "dialog"
         "content": [AoiTile()]},
    ],
    theme_state=theme_state,
    right_panel_config={"title": "Tools", "icon": "mdi-cog", "width": 400},
    right_panel_content=[
        {"title": "Section", "icon": "mdi-cog", "content": [LayerControls()],
         # Static guidance belongs here, not in a solara.Info alert.
         "description": "Shown under the section title."},
    ],
    right_panel_open=True,
)
```

`MapAppComponent` — typed dataclass props, `with` syntax — is designed but
**not shipped**: `pysepal.solara.components.layout` does not exist and the
import raises `ImportError`. Check with
`python -c "from pysepal.solara import MapAppComponent"` before relying on
anything in `docs/guides/solara-mapapp-component.md`.

`SepalMap(theme_toggle=...)` still works but emits a `DeprecationWarning`
(`MapApp` accepts it silently). See `docs/guides/migration-notes-v3.4.md`
§ 7 for migration details.

### Reference templates

One worked example lives in the pysepal repo — read it before building a
new app to see the patterns in action:

- `demo_apps/solara_map_app/` — MapApp shell with `AoiView`
  in the right panel, `NotificationProvider` task tracking, `ExportLauncher`
  sources, and a `LegendComponent` whose layer selector is driven by the layers
  on the map. `app.py` holds the shell: `MapAppDemo` owns the UI so `Page`
  (Solara, session-authenticated) and `ui.ipynb` (Voila) can share it. The rest
  lives under `component/` — `parameter/` (layer ids, vis params), `model/`
  (dataclasses in reactives), `scripts/` (Earth Engine work, no UI), `tile/`
  (right-panel sections), `widget/` (map, layer lifecycle, floating legend).

### eager=True for dialogs in jupyter-widget contexts

Dialogs inside MapApp's `right_panel_content` or `steps_data` need
`eager=True` or the content fails to mount silently.

### value/on_value pattern

All pysepal Solara components follow the Solara reactive pattern:

```python
@solara.component
def MyComponent(
    value: Union[T, solara.Reactive[T]] = default,
    on_value: Optional[Callable[[T], None]] = None,
):
    reactive_value = solara.use_reactive(value, on_value)
    del value, on_value
```

### Exposing internal loading state

Components that do async work should expose `loading`/`on_loading` so
parents can disable buttons:

```python
AssetSelectComponent(
    value=asset_data,
    loading=asset_loading,  # parent wires this to disable submit
)
```

### Notification System

All user feedback (success, error, warnings, task progress) goes through
the centralized notification system. Do NOT add inline `solara.Error()`,
`solara.Success()`, or `Alert` widgets to components — use the notification
API instead.

**Setup:** Mount `NotificationProvider()` once at the app root:

```python
from pysepal.solara.notifications import NotificationProvider

@solara.component
def Page():
    NotificationProvider()
    MapApp.element(...)
```

**Inside Solara components** — use the hook:

```python
from pysepal.solara.notifications import use_notifications

@solara.component
def MyComponent():
    notifications = use_notifications()

    # Toasts (auto-dismiss after 3s, click to dismiss)
    notifications.success("Done!")
    notifications.error("Failed!")
    notifications.warning("Check config")
    notifications.info("Processing...")

    # Task tracking (shows in pill + logger)
    async def process():
        with notifications.track("Processing data", total_steps=3) as task:
            task.step("Loading...")
            await do_work()
            task.step("Computing...")
            await do_more()
            task.step("Finalizing...")
        notifications.success("Complete!")

    solara.lab.use_task(process, dependencies=None, raise_error=False)
```

**Outside components** (scripts, decorators, background threads):

```python
from pysepal.solara.notifications import notify, track_task

notify("Export failed", type_="error")

with track_task("Exporting", total_steps=2) as task:
    task.step("Preparing...")
    task.step("Uploading...")
```

**Architecture:**

- `state.py` — frozen dataclasses (Toast, TrackedTask, TaskMilestone)
- `bus.py` — kernel-scoped NotificationBus with dedup, error replacement,
  queue cap, task retention cap, refcounted registry
- `notifier.py` — Notifier publisher + TaskTracker context manager
- `hook.py` — `use_notifications()` Solara hook
- `provider.py` — `NotificationProvider` root component
- `notification_ui.py` + `NotificationUI.vue` — Vue-rendered UI
- `globals.py` — `notify()` / `track_task()` escape hatches

**Key rules:**

- `NotificationProvider` must be mounted BEFORE components that call
  `use_notifications()`. On the first render before the provider's
  `use_effect` fires, the hook returns a `NoopNotifier` (silent fallback).
- Errors replace previous errors on the bus (only the latest is kept).
- The Vue UI subscribes to the bus via `Reactive.subscribe()`, NOT by
  reading `.value` in the render body. This prevents notification changes
  from triggering parent component re-renders (which would disrupt
  MapApp layout).
- The task pill position tracks MapApp's right panel via CSS variable
  `--sepal-notification-right-offset` set on `document.documentElement`
  by `MapApp.vue`. No DOM polling.
- The `@catch_errors` decorator is NOT modified. It continues to work
  with legacy Alert widgets only. The notification system is independent.

**Reference demo:**
`demo_apps/solara_map_app/` — provider in `app.py`,
`use_notifications` in `component/tile/process.py`

### Export System (ExportLauncher)

Apps that produce exportable GEE layers (images / feature collections)
should use `ExportLauncher` — a single button that opens a dialog covering
Earth Engine asset, Google Drive, and SEPAL workspace destinations through
one async engine. Do NOT roll your own export flow unless the dialog
genuinely cannot express your requirements.

**Setup:** declare one `ExportSource` per exportable layer and drop the
launcher in the right panel or toolbar:

```python
from pysepal.solara.components.export import ExportLauncher, ExportSource, ResolvedExport

sources = (
    ExportSource(
        id="dem",
        label="Elevation (DEM)",
        kind="image",               # "image" or "table"
        resolve=lambda: ResolvedExport(
            ee_object=ee.Image("USGS/SRTMGL1_003").clip(aoi.value),
            default_name="SRTM_elevation",
            region=aoi.value,
            default_scale=30,
        ),
    ),
)

ExportLauncher(sources=sources, button_text=True)
```

**Key rules:**

- `ExportSource.resolve` is a 0-arg callable invoked lazily when the user
  presses Export — keep it pure and read reactive state inside. This is
  where AOI clipping, compositing, etc. should happen.
- The dialog kind and the real `ee` kind returned by `resolve()` must
  agree; mismatches surface as an error toast rather than a crash.
- File formats must use canonical REST enum strings: `"GEO_TIFF"` (not
  `"GeoTIFF"`), `"GEO_JSON"` (not `"GeoJSON"`), `"SHP"`, `"CSV"`, `"KML"`,
  `"KMZ"`. The constants `DEFAULT_IMAGE_FILE_FORMAT`,
  `DEFAULT_TABLE_FILE_FORMAT`, and the `value` fields of
  `TABLE_FILE_FORMATS` already use canonical strings.
- `ee-client >= 2.5.2` is required (pyproject.toml enforces). 2.5.1 had a
  table-to-asset serializer bug.
- SEPAL-workspace target is auto-disabled when no session-backed
  `SepalClient` is available — don't pass one explicitly in normal apps,
  `use_export_dialog` picks it up via `get_current_sepal_client()`.
- The dialog stays open after success (users often want to copy the asset
  path / task id). Do NOT auto-close unless you have a specific reason.
- Multiple sources group by kind (Images vs Feature collections) with a
  Vuetify subheader + divider automatically; single-kind inputs render
  flat.
- For custom layouts (menu trigger, multiple open buttons, etc.) use
  `use_export_dialog(sources=...)` + render `ExportDialog(controller=...)`
  yourself. The controller exposes `open_dialog`, `close_dialog`,
  `submit_export`, `result`, `task`.

**Architecture:**

- `export_models.py` — `ExportSource`, `ResolvedExport`, `ExportRequest`,
  `ExportResult`, pure helpers (`sanitize_export_name`,
  `resolve_asset_folder`, `resolve_sepal_folder`, `infer_export_kind`)
- `export_engine.py` — pure async `submit_export_request(...)`; handles
  folder creation, EE task submission, Drive staging for SEPAL targets,
  cleanup
- `export_hook.py` — `use_export_dialog(...)` controller; holds the
  reactive dialog state and the `solara.lab.use_task` runner
- `export_dialog.py` — `ExportDialog` modal UI
- `export_launcher.py` — `ExportLauncher` one-button entry point
- `export.py` — public import surface + legacy `ExportDataComponent` compat
  wrapper

**Testing pattern:** pure-function helpers test normally; render-tree
tests must wrap `.widget(...)` in `asyncio.run(...)` so
`solara.lab.use_task` can schedule at mount. Post-selection assertions
(destination RadioGroup, scale BtnToggle) require driving the controller
into a selected+open state before the walk — see
`tests/test_solara/test_export_component.py::_render` and
`_render_preselected_dialog`.

**Reference demo:**
`demo_apps/solara_map_app/component/scripts/exports.py` (sources)
and `component/tile/export.py` (launcher)

**Full guide:** `docs/guides/solara-export.md`

### Async Button Pattern (TaskButtonComponent)

All buttons that trigger async work must use `TaskButtonComponent`.
Read `docs/guides/solara-gee-patterns.md` § "Async
Button Convention" for the canonical pattern, rules, and cancel semantics.

### AOI Method Restrictions

GEE/container apps must exclude SHAPE and POINTS methods — they read local
files and assume server-local paths. Use `methods=["-SHAPE", "-POINTS"]`
or an explicit allowlist. Read
`docs/guides/solara-gee-patterns.md` § "AOI Method
Restrictions" for the full matrix.

### Blocking I/O in Components

Never do blocking file I/O inside `use_effect` — it freezes the UI.
Use `use_task` + `asyncio.to_thread` instead. Read
`docs/guides/solara-gee-patterns.md` § "Blocking I/O
in Solara Components" for the pattern.

An `asyncio.to_thread` worker has no kernel context. Do not call `msg()` or
`notify()` in it. Return the result and publish after the `await`. See
"Translations" § "Workers and the locale".

## Translations (`pysepal.i18n`)

Every user-facing string comes from a JSON catalogue through one lookup,
`msg("dotted.key")`. `Translator` attribute lookups (`ms.section.key`),
`pysepal.message.ms`, `LocaleState`, `use_locale()` and `locale_state=` are
gone from Solara apps. `Translator` survives only for the legacy Voila widgets.

**Layout.** The app owns `component/message/`: one `__init__.py` and one folder
per locale. English is the source of truth. Every other locale is an overlay,
and a key it lacks falls back to English.

```
component/message/
├── __init__.py       # messages = catalog(...); msg = messages.msg
├── en/app.json       # every key lives here
├── es/app.json       # overlay
└── fr/app.json
```

```python
# component/message/__init__.py
from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent)
msg = messages.msg
```

```json
{
  "app": { "title": "Risk mapping" },
  "toasts": {
    "saved": "Saved {name}",
    "cleared": {
      "one": "{count} layer removed",
      "other": "{count} layers removed"
    }
  }
}
```

**Use.** Import `messages` and `msg` from the app's own package, not from
pysepal:

```python
from component.message import messages, msg

@solara.component
def Page():
    NotificationProvider()
    MapApp.element(
        app_title=msg("app.title"),
        locales=messages.available_locales(),  # the shell mounts the language selector
    )
```

- `msg("toasts.saved", name=layer)` fills named placeholders. Only bare
  `{name}` placeholders are valid: no `{0}`, no `{area:.2f}`, no `{obj.attr}`.
  Format numbers in the caller and pass the string.
- `msg("toasts.cleared", count=n)` selects the plural form when the English
  key is a plural node: an object whose keys are CLDR categories (`one`,
  `other`, and per language `zero`, `two`, `few`, `many`). Each locale writes
  only the categories its rules use; Babel supplies the rules. On any other key
  `count` is an ordinary placeholder.
- A component that calls `msg()` re-renders when the language changes, also
  through a helper on its call stack. Keys may come from data, for example a
  registry table that stores keys.
- `current_locale()` / `set_locale(code)` from `pysepal.i18n` read and change
  the locale. It is one Solara reactive per kernel, so users never share it. A
  selector's first browser mount overwrites it (localStorage, then
  `navigator.language`, then English), so `set_locale` cannot seed a default.
- Without `MapApp`, mount `LocaleSelectComponent(locales=...)` from
  `pysepal.solara.components.locale_select` inside the component.
- `messages.check()` returns a tuple of `CatalogProblem(code, locale, key, detail)`. Assert it is empty in a test. Codes: `missing_key`, `extra_key`,
  `placeholder_mismatch`, `malformed_template`, `shape_mismatch`,
  `unsupported_plural_category`, `unreadable_locale`.
- `catalog(folder)` is strict: a missing English key or a malformed English
  template raises. `catalog(folder, strict=False)` renders `⟦key⟧` instead. A
  translator's mistake never raises: it is reported once in the log and
  English shows. An empty string in a translation (Pontoon export) means "not
  translated" and also shows English.
- pysepal's own strings: `from pysepal.message import msg`.

**Workers and the locale.** Solara keys the kernel context by thread:

| Code runs in                                                                                                    | Sees the user's locale                   |
| --------------------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| A render, an event handler, a `use_task` body (threaded or not), a `threading.Thread` created inside the kernel | yes                                      |
| `asyncio.to_thread`, any executor thread, a thread created at import                                            | no: the process default, usually English |

Let such workers return results, or a message key plus named values, and call
`msg()` in the UI context that receives them. Never call `msg()` from a pool
thread. A `prefer_threaded=True` body keeps the locale but runs on its own
event loop, so it must stay on the synchronous GEE API (see the event-loop
error below).

**Migrating a 3.x app:**

| 3.x                                            | 4.0                                                |
| ---------------------------------------------- | -------------------------------------------------- |
| `ms = Translator(folder, target=locale)`       | `messages = catalog(folder)`; `msg = messages.msg` |
| `ms.section.key`                               | `msg("section.key")`                               |
| `ms.section.key.format(x)`, `{0}` in JSON      | `msg("section.key", name=x)`, `{name}` in JSON     |
| `"layer(s)"`                                   | a plural node with `one` / `other`, and `count=`   |
| `use_locale()`, `LocaleState`, `locale_state=` | `current_locale()` / `set_locale()`                |
| `language_selector=[LocaleSelect(...)]`        | `locales=messages.available_locales()`             |

All four `demo_apps/` are translated (en, es, fr); `solara_raster_app` shows
plural nodes. Full text: `docs/source/tutorials/translate-app.rst` and
`docs/guides/migration-v4.md` § 6.

## Charts and Graphs

**Always use `ipecharts`** for charts in pysepal apps — bar, line, pie,
scatter, heatmap, 3D, network graphs, etc. Do not use matplotlib,
plotly, or other charting libraries unless the user explicitly asks.

Read `docs/guides/ipecharts.md` before creating any
chart. It covers both approaches (`EChartsRawWidget` for quick prototypes,
`EChartsWidget` for reactive dashboards), Solara integration via
`.element()`, event handling, theming, and common gotchas.

```python
# Solara integration — mount with .element()
from ipecharts import EChartsWidget
from ipecharts.option import Option, XAxis, YAxis
from ipecharts.option.series import Bar

option = Option(
    xAxis=XAxis(type="category", data=categories),
    yAxis=YAxis(type="value"),
    series=[Bar(data=values)],
)
EChartsWidget.element(option=option, style={"height": "300px"})
```

## Known Error Patterns

### `RuntimeError: ... is bound to a different event loop`

**Cause:** `prefer_threaded=True` on a `use_task` that calls GEE async methods,
or `map_.add_ee_layer` called from a sync `use_effect` handler. Solara's
`use_task(prefer_threaded=True)` creates a new `asyncio.new_event_loop()` per
invocation. `EESession`'s asyncio primitives (`Lock`, `BoundedSemaphore`) and
`httpx.AsyncClient(http2=True)` bind to the first loop they see. A
start/cancel/start cycle hits a second loop → RuntimeError.

**Fix:**

- Set `prefer_threaded=False` on the `use_task` — this runs the coroutine on
  Solara's stable kernel event loop instead of a throwaway per-task loop
- Move `add_ee_layer` into the async task via `asyncio.to_thread`:
  ```python
  await asyncio.to_thread(map_.add_ee_layer, fc, vis, "aoi", autocenter=True)
  ```

### Excessive "Closing GEEInterface..." log messages

**Cause:** A helper like `process_admin()` is called without `gee_interface=`,
so it creates a throwaway `GEEInterface()` per call — each with its own event
loop + daemon thread. When GC collects them, `__del__` logs the close.

**Fix:** Pass the shared session interface to all helpers that accept one:

```python
result = await process_admin(
    method=method,
    admin_code=code,
    gee=True,
    gee_interface=get_current_gee_interface(),
)
```

### `TypeError: n[o].bind is not a function`

**Cause:** Object-style Vue watchers on Python-synced props in VuetifyTemplate.

**Fix:** Use simple function watchers, `mounted()` instead of `immediate: true`.

Reference: `docs/guides/ipyvuetify-widgets.md`

### Silent empty widgets (no error)

**Cause:** `v.Widget(...)` used inside `with rv.Something():` context, or
`solara.Column` wrapping `rv.` elements.

**Fix:** Use `rv.Widget(...)` throughout, avoid mixing `solara.Column` with
`rv.` containers.

### `Collection.loadTable: Expected asset to be a Collection, found 'Image'`

**Cause:** `ee.FeatureCollection(asset_id)` called on an IMAGE asset, usually
from a race condition where `selected_column` holds a stale non-"ALL" value
after `asset_id` changed.

**Fix:** Guard column/value operations on `asset_type.value == "TABLE"`.

## Component Naming Convention

Solara components use `OriginalName + Component` suffix:

| Component                 | Package                                 |
| ------------------------- | --------------------------------------- |
| `FileInputComponent`      | `pysepal.solara.components.inputs`      |
| `AssetSelectComponent`    | `pysepal.solara.components.inputs`      |
| `PointsSelectorComponent` | `pysepal.solara.components.inputs`      |
| `VectorSelectorComponent` | `pysepal.solara.components.inputs`      |
| `TaskButtonComponent`     | `pysepal.solara.components.task_button` |
| `AoiView`                 | `pysepal.solara.components.aoi`         |
| `NotificationProvider`    | `pysepal.solara.notifications`          |

Run discovery for the full current list — do not rely on this table.

## Guides (read when needed)

### pysepal guides (`docs/guides/`)

| Guide                     | When to read                                                        |
| ------------------------- | ------------------------------------------------------------------- |
| `solara-gee-patterns.md`  | Any GEE work in Solara                                              |
| `solara-app-builder.md`   | Scaffolding or restructuring an app                                 |
| `solara-export.md`        | Adding export to EE asset / Drive / SEPAL workspace                 |
| `solara-migration.md`     | Converting ipyvuetify widget to Solara                              |
| `ipyvuetify-widgets.md`   | Creating a new `v.VuetifyTemplate` widget                           |
| `ipecharts.md`            | Creating charts/graphs (ipecharts is the standard for pysepal apps) |
| `local-tile-servers.md`   | Serving localtileserver / vectortileserver tiles to the browser     |
| `migration-notes-v3.4.md` | Auditing an existing app for stale patterns                         |
| `migration-v4.md`         | Moving a 3.x app to 4.0: sessions, locale, `catalog()`              |

Tutorial: `docs/source/tutorials/translate-app.rst` — writing catalogues,
plural nodes, `check()`.

### Solara framework source

When a Solara pattern is unclear, missing from pysepal docs, or you need
to verify how a hook or component works under the hood, query the Solara
source directly. Either browse the upstream repo
(<https://github.com/widgetti/solara>) or, if you have a local checkout,
inspect:

- `solara/` — core framework (hooks, components, server)
- `solara/lab/` — experimental APIs (`use_task`, etc.)
- `docs/` — official documentation and examples
- `tests/` — test suite showing intended usage patterns

**If any guide file is unreachable, STOP and ask the user for the correct
pysepal repo path. Do not generate code against missing documentation.**

## Audit Checklist

When invoked with `/pysepal audit`, check the current project for:

- [ ] Old imports: `asset_method`, `AssetSelector`, `PointsSelector`, `ShapeSelector`
- [ ] `prefer_threaded=True` (or missing `prefer_threaded`) on GEE `use_task` hooks
- [ ] `process_admin()` / `process_asset()` called without `gee_interface=` (creates throwaway instances)
- [ ] `asyncio.to_thread(gee_interface.` wrapping GEE calls
- [ ] `add_ee_layer` called from sync `use_effect` handlers
- [ ] `v.Widget(...)` inside `with rv.Something():` contexts
- [ ] Missing `loading` parameter on `AssetSelectComponent`
- [ ] Separate cancel button below action button (use `TaskButtonComponent` instead)
- [ ] `solara.Button` with `disabled=task.pending` for async actions (use `TaskButtonComponent`)
- [ ] Blocking sync work in `use_thread` instead of `use_task` + `asyncio.to_thread`
- [ ] Bare `task.value` truthiness instead of `task.value is not None`
- [ ] `use_effect` with incomplete dependency list (must include pending, finished, error, cancelled)
- [ ] `methods="ALL"` in GEE/container apps (must exclude SHAPE and POINTS)
- [ ] Blocking file I/O (`gpd.read_file`, `pd.read_csv`) directly in `use_effect` (use `use_task` + `asyncio.to_thread`)
- [ ] Inline `solara.Error()` / `solara.Success()` / `Alert()` for user feedback (use `use_notifications()` + `NotificationProvider`)
- [ ] Reading `bus.toasts.value` or `bus.tasks.value` in a Solara render body (use `Reactive.subscribe()` in `use_effect` to avoid triggering parent re-renders)
- [ ] Manual `ThemeToggle()` + `theme.observe(...)` wiring, or `theme_toggle=` on `SepalMap` / `MapApp` (use `get_current_theme_state()` + `theme_state=`)
- [ ] `Translator(...)`, `from component.message import ms`, or `ms.` attribute lookups (use `catalog()` + `msg("dotted.key")`)
- [ ] `use_locale()`, `LocaleState`, `locale_state=`, `LocaleSelect.bind_locale_state()` (use `current_locale()` / `set_locale()`; pass `locales=` to `MapApp.element`)
- [ ] Positional or formatted placeholders in JSON catalogues (`{0}`, `{area:.2f}`, `{obj.attr}`) (named `{name}` only; format in the caller)
- [ ] `"layer(s)"`-style strings where a plural node with `count=` belongs
- [ ] `msg()` called inside `asyncio.to_thread` or an executor worker (return a key + named values; translate in the UI context)
- [ ] No test asserting `messages.check() == ()`
- [ ] `MapApp(...)` constructed directly instead of `MapApp.element(...)` inside a `@solara.component`

Read `docs/guides/migration-notes-v3.4.md` for the
full breaking changes list.
