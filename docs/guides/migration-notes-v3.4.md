# pysepal Solara Component Changes (v3.4)

> This page records the 3.4 changes. § 8 is superseded: `MapAppComponent` never
> shipped. pysepal 5 removed `pysepal.sepalwidgets` and the Vue `MapApp`; see
> [migrating-to-pysepal-5.md](./migrating-to-pysepal-5.md).

Use this document to audit and update any pysepal-based Solara app that was
scaffolded or written before these changes landed.

## 1. Component Renames and Relocations

Solara input components have moved from `pysepal.solara.components.aoi.*` and
`pysepal.sepalwidgets.file_input` into a dedicated package:
`pysepal.solara.components.inputs`.

**Naming convention**: Solara components use `OriginalName + Component` suffix.

| Old name / location                                               | New name                  | New import path                                    |
| ----------------------------------------------------------------- | ------------------------- | -------------------------------------------------- |
| `FileInputComponent` from `pysepal.sepalwidgets.file_input`       | `FileInputComponent`      | `pysepal.solara.components.inputs.file_input`      |
| `AssetSelector` from `pysepal.solara.components.aoi.asset_method` | `AssetSelectComponent`    | `pysepal.solara.components.inputs.asset_select`    |
| `PointsSelector` from `pysepal.solara.components.aoi.points`      | `PointsSelectorComponent` | `pysepal.solara.components.inputs.point_selector`  |
| `ShapeSelector` from `pysepal.solara.components.aoi.shape`        | `VectorSelectorComponent` | `pysepal.solara.components.inputs.vector_selector` |

**Shorthand import** — all four are re-exported from the package init:

```python
from pysepal.solara.components.inputs import (
    FileInputComponent,
    AssetSelectComponent,
    PointsSelectorComponent,
    VectorSelectorComponent,
)
```

**Backward compatibility**:

- `FileInputComponent` from `pysepal.sepalwidgets.file_input` still works but
  emits a `DeprecationWarning`. Update the import.
- The old names (`AssetSelector`, `PointsSelector`, `ShapeSelector`) no longer
  exist at the old locations. These were new components with no external users,
  so no deprecation shim was added.

**What to do**: search your codebase for the old import paths and rename.

## 2. Process Functions Stayed Put

The AOI processing functions did not move. They remain in the `aoi` subpackage:

```python
from pysepal.solara.components.aoi import process_asset, process_points, process_shape
```

`asset_method.py` was renamed to `asset.py`:

```python
# Old
from pysepal.solara.components.aoi.asset_method import process_asset
# New
from pysepal.solara.components.aoi.asset import process_asset
```

**What to do**: if you import `process_asset` from `aoi.asset_method`, update
to `aoi.asset`.

## 3. GEE Pattern Change: `prefer_threaded=False` and Direct Async

The documented GEE pattern has changed. The previous pattern wrapped sync
GEE methods with `asyncio.to_thread`:

```python
# OLD pattern — do not use for new code
@solara.lab.use_task(dependencies=None, raise_error=False, prefer_threaded=True)
async def gee_job(request):
    result = await asyncio.to_thread(gee_interface.get_info, ee_object)
```

The new pattern uses `GEEInterface` async methods directly and keeps the
coroutine on Solara's event loop:

```python
# NEW pattern
@solara.lab.use_task(dependencies=None, raise_error=False, prefer_threaded=False)
async def gee_job(request):
    result = await gee_interface.get_info_async(ee_object)
```

**Key changes**:

- `prefer_threaded=False` — keeps the task on Solara's event loop, avoiding
  cross-loop `RuntimeError` with `EESession`'s asyncio primitives.
- `await gee_interface.*_async(...)` — call the async GEE methods directly.
- `asyncio.to_thread(...)` is now reserved for truly blocking non-GEE work
  (local file I/O, CPU-heavy parsing, etc.).

**What to do**:

1. Change `prefer_threaded=True` to `prefer_threaded=False` on all
   `use_task` hooks that call GEE.
2. Replace `asyncio.to_thread(gee_interface.get_info, obj)` with
   `await gee_interface.get_info_async(obj)` (and similarly for
   `get_assets`, `get_asset`, `get_map_id`, `get_folder`, exports, etc.).
3. Keep `asyncio.to_thread` only for non-GEE blocking calls.

**Reference**: `docs/guides/solara-gee-patterns.md`

## 4. `AssetSelectComponent` API Changes

The component now:

- Defaults to `types=["IMAGE", "TABLE"]` (was `["TABLE"]` only).
- Exposes `loading` / `on_loading` parameters so the parent can disable
  buttons while the component is loading assets, validating, or fetching
  columns.
- Only shows column/value selectors for TABLE assets.
- Accepts an optional `gee_interface` parameter.
- Output dict now includes a `type` key alongside `asset_id`, `column`,
  `value`.

```python
AssetSelectComponent(
    types=["IMAGE", "TABLE"],
    value=asset_data,
    loading=asset_loading,       # new — reactive bool
    gee_interface=gee_interface, # new — optional, falls back to session
)
```

**What to do**: if you use `AssetSelector` or `AssetSelectComponent`, check
that you handle the new `type` key in the output dict and consider wiring
`loading` to disable submit buttons.

## 5. `AoiView` Internal Changes

- Uses the new component names internally (`AssetSelectComponent`,
  `PointsSelectorComponent`, `VectorSelectorComponent`).
- The `add_ee_layer` call now runs inside `process_aoi` via
  `asyncio.to_thread` (on a worker thread) instead of in
  `handle_task_state` (on the event loop). This prevents the cross-loop
  `RuntimeError` with `eeclient`'s HTTP/2 connections.
- The "Select AOI" button is now disabled while `AssetSelectComponent` is
  loading.

**What to do**: if you override or extend `AoiView` behavior, verify your
code is compatible with these changes. If you only use `AoiView` as a
black box, no action needed.

## 6. New Documentation

- `docs/guides/ipyvuetify-widgets.md` — guide for creating custom
  `v.VuetifyTemplate` widgets (Python + Vue structure, data sync, event
  handling, component embedding, troubleshooting).

## 7. Theme: `theme_toggle=` → `theme_state=`

Theme source of truth moved from per-widget `ThemeToggle` observers to a
`ThemeState` keyed by the runtime scope. Fixes theme freezes after Solara
re-renders.

**Old pattern:**

```python
theme_toggle = ThemeToggle()
theme_toggle.observe(lambda e: setattr(theme, "dark", e["new"]), "dark")

SepalMap(gee_interface=gee_interface, theme_toggle=theme_toggle)
MapApp.element(..., theme_toggle=[theme_toggle])
```

**New pattern:**

```python
from pysepal.solara import get_current_theme_state

theme_state = get_current_theme_state()

SepalMap(gee_interface=gee_interface, theme_state=theme_state)
MapApp.element(..., theme_state=theme_state)
```

**Key points:**

- `get_current_theme_state()` returns the scope-keyed `ThemeState`; no
  manual `ThemeToggle` or `theme.dark` observer needed. `MapApp` creates
  its own toggle if none is supplied. Theme is UI state, not SEPAL session
  state — it is not seeded from `~/.sepal-ui-config` (deprecated, issue #977).
- `SepalMap(theme_toggle=...)` still works but emits `DeprecationWarning`.
- `ThemeState` exposes `.mode` (`"dark"` | `"light"` | `"auto"`) and `.dark`
  (resolved boolean). Use `use_theme_dark()` to reactively observe from a
  Solara component.
- Auto mode now tracks system `prefers-color-scheme` live.

**What to do**: remove `theme_toggle = ThemeToggle()` + `theme_toggle.observe(...)`
boilerplate; swap `theme_toggle=` for `theme_state=` on `SepalMap` and `MapApp`.

## Audit Checklist

- [ ] Search for old import paths (`asset_method`, `AssetSelector`,
      `PointsSelector`, `ShapeSelector`, `sepalwidgets.file_input.FileInputComponent`)
      and update them.
- [ ] Search for `prefer_threaded=True` on GEE-related `use_task` hooks
      and change to `prefer_threaded=False`.
- [ ] Search for `asyncio.to_thread(gee_interface.` and replace with
      `await gee_interface.*_async(...)`.
- [ ] If using `AssetSelectComponent`, handle the `type` key in the output
      dict and wire the `loading` parameter.
- [ ] Verify `add_ee_layer` calls are not made from sync `use_effect`
      handlers — they must run from a thread or from inside an async task.
- [ ] Remove manual `theme_toggle = ThemeToggle()` + `theme.observe(...)`
      wiring; use `get_current_theme_state()` and pass `theme_state=` to
      `SepalMap` / `MapApp` instead.

## 8. MapApp → MapAppComponent

```{important}
**Not yet available** (as of pysepal 3.7.0): `MapAppComponent` and
`pysepal.solara.components.layout` are not in the released package — the module
is empty and the imports raise `ImportError`. Keep using `MapApp.element`
(reacton renders `@solara.component` tiles passed as `content`). The guidance
below describes the **planned target**, not the current state.
```

Once it ships, prefer `pysepal.solara.components.layout.MapAppComponent`
(re-exported as `pysepal.solara.MapAppComponent`) over the
`pysepal.sepalwidgets.vue_app.MapApp` VuetifyTemplate. The new component:

- Is a `@solara.component` usable with `with MapAppComponent(...): ...`.
- Exposes typed dataclass props: `StepConfig`, `PanelSection`,
  `RightPanelConfig`, `StepAction`, `ExternalLink`.
- Auto-wires `ThemeState` and `Translator` (no manual `ThemeToggle()`
  construction needed).
- Renders only the active step's content (lazy `content=` callables).
- Preserves the visual design of `MapApp.vue` (drawer, narrow-mode
  bottom sheet, dialog steps, right panel).

See `docs/guides/solara-mapapp-component.md` for the migration map. The
legacy class still works but emits a `DeprecationWarning`.
