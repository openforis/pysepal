# Solara Migration Guide

> **IMPORTANT**: Read this guide BEFORE converting any ipyvuetify widget to Solara.
> Every pattern here is grounded in working code already in this repo.

## 1. Conversion Mapping Table

| ipyvuetify / traitlets                   | Solara equivalent                                                | Notes                                                                                         |
| ---------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| `class MyWidget(v.Btn, SepalWidget):`    | `@solara.component def MyWidget():`                              | Functions, not classes                                                                        |
| `t.Unicode("").tag(sync=True)`           | `solara.reactive("")` or function param                          | Module-level for shared state, param for component state                                      |
| `t.Bool(False).tag(sync=True)`           | `solara.reactive(False)` or `solara.use_state(False)`            | `use_state` for component-local                                                               |
| `@observe("trait_name")`                 | `solara.use_effect(fn, [dep])`                                   | Effect runs when dependency changes                                                           |
| `self.observe(handler, "trait")`         | `solara.use_effect(handler, [reactive.value])`                   | Same pattern                                                                                  |
| `link((w1, "v_model"), (w2, "v_model"))` | Shared `solara.reactive()` passed to both                        | No explicit linking needed                                                                    |
| `v.Btn(children=[...])`                  | `solara.Button(label=..., on_click=...)`                         | Solara has dedicated wrappers                                                                 |
| `v.Card(children=[...])`                 | `with solara.Card("title"):`                                     | Context manager pattern                                                                       |
| `v.Column(children=[...])`               | `with solara.Column():`                                          | Context manager pattern                                                                       |
| `v.Row(children=[...])`                  | `with solara.Row():`                                             | Context manager pattern                                                                       |
| `v.TextField(v_model=...)`               | `solara.InputText(value=...)` or `rv.TextField(v_model=...)`     | `rv` = `reacton.ipyvuetify`                                                                   |
| `v.Select(items=..., v_model=...)`       | `rv.Select(items=..., v_model=..., on_v_model=...)`              | Prefer `rv.Select` — `solara.Select` has different API and can't handle headers/grouped items |
| `v.Dialog(v_model=...)`                  | `v.Dialog(v_model=..., on_v_model=...)` via `reacton.ipyvuetify` | No native Solara Dialog yet                                                                   |
| `widget.hide()` / `widget.show()`        | Conditional rendering: `if visible:`                             | Don't render what shouldn't be shown                                                          |
| `toggle_loading()`                       | Reactive bool: `loading = solara.use_reactive(False)`            | Bind to `loading=loading.value`                                                               |
| `__init__(self, **kwargs)`               | Function params: `def MyWidget(value=None, on_value=None):`      | `value/on_value` is the standard interface                                                    |
| `self.children = [...]`                  | Return Solara elements from component body                       | Declarative, not imperative                                                                   |
| `VuetifyTemplate` + `.vue` file          | `reacton.ipyvuetify` or pure Solara components                   | Prefer pure Solara; use `rv` for complex vuetify                                              |

### When to use `reacton.ipyvuetify` (`rv`)

Use `import reacton.ipyvuetify as rv` when:

- Solara has no native equivalent (Dialog, Tabs, Menu, Snackbar)
- You need low-level vuetify control (custom slots, complex layouts)
- Wrapping existing Vue templates during incremental migration

Always prefer native Solara components when available.

### GEE + SessionManager Migration Rule

When migrating an ipywidgets or traitlets component that talks to Earth
Engine, assume the Solara target will use `@with_sepal_sessions` and the
session-bound `get_current_gee_interface()`.

For that architecture:

- Do not introduce a separate async GEE getter.
- Do not default to `asyncio.to_thread(gee_interface.get_info, ...)`.
- Do not scaffold new `gee_interface.create_task()` flows.
- Use `await gee_interface.*_async(...)` directly.
- If the GEE work is wrapped in `solara.lab.use_task`, set
  `prefer_threaded=False`.

```python
@solara.component
@with_sepal_sessions(module_name="my_app")
def Page():
    gee_interface = get_current_gee_interface()

    @solara.lab.use_task(
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )
    async def load_result(ee_object):
        return await gee_interface.get_info_async(ee_object)
```

Reserve `asyncio.to_thread()` for genuinely blocking local work such as file
I/O, archive handling, or CPU-heavy sync preprocessing.

## 2. Component Signature Pattern

Every converted component MUST follow this pattern:

```python
import solara
from typing import Callable, Optional, Union

@solara.component
def MyComponent(
    value: Union[str, solara.Reactive[str]] = "",
    on_value: Optional[Callable[[str], None]] = None,
    loading: Union[bool, solara.Reactive[bool]] = False,
    on_loading: Optional[Callable[[bool], None]] = None,
):
    """Component docstring (Google convention).

    Args:
        value: The current value. Can be reactive.
        on_value: Callback when value changes.
        loading: Whether the component is loading.
        on_loading: Callback when loading state changes.
    """
    # Wrap value/on_value into a single reactive — this is the standard idiom
    reactive_value = solara.use_reactive(value, on_value)
    reactive_loading = solara.use_reactive(loading, on_loading)
    del value, on_value, loading, on_loading  # Prevent accidental use of raw params

    # Component logic here...

    # Render
    with solara.Column():
        solara.Text(f"Value: {reactive_value.value}")
```

**Why `del value, on_value`?** Prevents accidentally using the raw parameter instead of the reactive wrapper. This is the pattern used in `AoiView` and `AdminLevelSelector`.

**Why `value/on_value`?** This is Solara's controlled component pattern. It lets the parent either:

- Pass a plain value (component manages its own state)
- Pass a `solara.Reactive` (parent controls the state)
- Pass an `on_value` callback (parent reacts to changes)

## 3. Hook Rules

**THE RULE: Hooks must be called in the same order on every render.**

Hooks: `use_state`, `use_effect`, `use_memo`, `use_ref`, `use_thread`, `use_reactive`, `use_task`.

### Pattern 1: NO hooks inside conditionals

```python
# WRONG
@solara.component
def MyComponent(data):
    if data:
        count, set_count = solara.use_state(0)  # BREAKS: hook inside conditional

# CORRECT
@solara.component
def MyComponent(data):
    count, set_count = solara.use_state(0)  # Always called
    # Use data conditionally AFTER hooks
    if data:
        solara.Text(f"Count: {count}")
```

### Pattern 2: NO hooks after early returns

```python
# WRONG
@solara.component
def MyComponent(data):
    if not data:
        return solara.Text("No data")  # Skips hooks below!
    value = solara.use_memo(lambda: expensive(data), [data])

# CORRECT
@solara.component
def MyComponent(data):
    value = solara.use_memo(lambda: expensive(data) if data else None, [data])
    if not data:
        return solara.Text("No data")  # Safe: hooks already called
    solara.Text(f"Result: {value}")
```

### Pattern 2b: State resets from remounts

When the parent conditionally inserts/removes siblings BEFORE a stateful child, the child gets **remounted** (state reset), not just re-rendered.

```python
# WRONG — Child remounts when data changes (sibling count changes)
@solara.component
def Page():
    data = solara.use_reactive(None)
    with solara.Column():
        if data.value is None:
            solara.Info("No data")
        else:
            solara.Success("Data set")
            solara.Markdown("Extra UI")  # Changes sibling count!
        Child()  # Gets remounted, loses state

# CORRECT — Wrap conditional siblings in a stable container
@solara.component
def Page():
    data = solara.use_reactive(None)
    with solara.Column():
        with solara.Card("Status"):  # Stable wrapper
            if data.value is None:
                solara.Info("No data")
            else:
                solara.Success("Data set")
                solara.Markdown("Extra UI")
        Child()  # Same slot, state preserved
```

**Rule of thumb**: Never change the number/order of siblings before stateful components. Use stable wrappers.

### Pattern 3: NO hooks in different branches

```python
# WRONG
@solara.component
def MyComponent(data):
    if len(data) > 0:
        avg, set_avg = solara.use_state(0)  # Different hook count per branch!
    else:
        pass

# CORRECT
@solara.component
def MyComponent(data):
    avg, set_avg = solara.use_state(None)  # Always called
    def _update():
        set_avg(calc_avg(data) if data else None)
    solara.use_effect(_update, [data])
```

### Pattern 4: NO hooks inside loops

```python
# WRONG
@solara.component
def MyComponent(items):
    for item in items:
        count = solara.use_state(0)  # Variable hook count!

# CORRECT — use a single state dict or child components
@solara.component
def MyComponent(items):
    counts = solara.use_state({})
    for item in items:
        ItemChild(item)  # Each child manages its own hooks
```

### Hook Checklist

Before submitting any Solara component, verify:

- [ ] All `use_*` calls are at the TOP of the component function
- [ ] All `use_*` calls happen in the SAME ORDER every render
- [ ] NO `use_*` calls inside `if/else` blocks
- [ ] NO `use_*` calls inside loops with variable iterations
- [ ] NO `use_*` calls AFTER early `return` statements
- [ ] NO `use_*` calls in `try/except` where try might skip hooks
- [ ] Conditional logic is INSIDE hook callbacks, not around hook calls
- [ ] Conditional rendering happens AFTER all hooks

## 4. State Management Patterns

### Module-level reactive (shared/app-wide state)

```python
# At module level — shared across all component instances
selected_method = solara.reactive("")
is_loading = solara.reactive(False)

@solara.component
def MyComponent():
    # Read: selected_method.value
    # Write: selected_method.value = "new" or selected_method.set("new")
    solara.Text(f"Method: {selected_method.value}")
```

### AppState singleton (complex apps)

For apps with many reactive variables, use a state class (pattern from sbae-design):

```python
class AppState:
    def __init__(self):
        self.file_path = solara.reactive(None)
        self.is_processing = solara.reactive(False)
        self.results = solara.reactive(None)
        self.class_areas = solara.reactive({})

    def is_ready_for_calculation(self) -> bool:
        """Validation helper — checks all preconditions before allowing computation."""
        return self.file_path.value is not None and not self.is_processing.value

    def update_class_areas(self, class_id: str, area: float):
        """Always replace with a new object — never mutate .value in place."""
        updated = self.class_areas.value.copy()
        updated[class_id] = area
        self.class_areas.value = updated  # New object triggers re-render

app_state = AppState()  # Singleton
```

### Component-local state

```python
@solara.component
def MyComponent():
    # use_state: simple local state (returns value + setter)
    count, set_count = solara.use_state(0)

    # use_reactive: local reactive (returns Reactive object)
    # Preferred when passing state to child components
    method = solara.use_reactive("ADMIN0")

    # use_ref: mutable value that does NOT trigger re-renders
    # Useful for breaking sync loops or tracking previous values
    prev_method = solara.use_ref(method.value)
    if prev_method.current != method.value:
        # Method changed — do something
        prev_method.current = method.value
```

### When to use which

| Pattern                             | When to use                                                                |
| ----------------------------------- | -------------------------------------------------------------------------- |
| `solara.reactive()` at module level | App-wide state shared across components                                    |
| `AppState` singleton                | Many related reactive variables                                            |
| `solara.use_state()`                | Simple component-local state (value + setter)                              |
| `solara.use_reactive()`             | Component-local state passed to children                                   |
| `solara.use_ref()`                  | Mutable value that should NOT trigger re-renders (prev values, sync flags) |
| `value/on_value` params             | Component inputs controlled by parent                                      |

### Editable drafts and published values

Use `solara.use_reactive(value, on_value)` directly when the editable value is also
the component's output. A composite form sometimes needs a separate draft: a points
picker must keep the selected CSV and column choices while publishing `None` until
all required columns are selected.

Keep related editable fields in one draft dict or object. A user changing the file
should replace that draft and reset dependent column choices together. An external
restore supplies the whole selection, including its column choices. Async loaders
return available options; they should not replay an earlier restore over newer edits.

The internal [`_use_draft` helper](../../pysepal/solara/hooks.py) supports this
distinction in pysepal's vector, points, and asset selectors:

- It returns a reactive draft and a `publish(output)` callback.
- External value changes replace the draft, including a change to `None`.
- Publishing an output leaves the draft intact. Use `publish(None)` to report an
  incomplete selection without discarding the user's edits.
- Setting a value equal to the current published value produces no change event.
  Resetting an incomplete form that already publishes `None` needs an explicit
  reset action; `AoiView` exposes this through `clear_ref`.

`_use_draft` is a private implementation helper, not a supported app API. App
authors should use the selectors' public `value`/`on_value` interface. It is not
needed for ordinary inputs or for loading flags and option lists.

For AOI persistence, the **draft** is the editable form, the **spec** records the
selection inputs, and the **result** holds the processed AOI. See
[Persist and restore an AOI](solara-app-builder.md#persist-and-restore-an-aoi) for
the public API and clear behavior.

## 5. Threading and Async Patterns

### `solara.lab.use_task` (preferred for new code)

```python
@solara.component
def MyComponent():
    async def fetch_data():
        result = await some_async_operation()
        return result

    task = solara.lab.use_task(
        fetch_data,
        dependencies=None,  # None = manual trigger via task()
        raise_error=False,
    )

    solara.Button("Fetch", on_click=task, disabled=task.pending)

    if task.pending:
        solara.ProgressLinear(indeterminate=True)
    elif task.finished:
        solara.Success(f"Done: {task.value}")
    elif task.error:
        solara.Error(f"Error: {task.exception}")
```

### Internal task state and result publication

For component-internal loading, derive option lists from `task.value` when
`task.finished`, and loading indicators from `task.pending`. Separate reactive
copies and effects that keep those copies synchronized are unnecessary. Include
all inputs that determine the request in the task dependencies, such as both the
file path and selected column. See the
[column-loading example](solara-gee-patterns.md#blocking-io-in-solara-components).

When a result must outlive the component, publish it into parent-owned state from
an effect after `task.finished`. Task functions return the result; completion
callbacks run in that effect. A callback may hide or unmount the component, so
calling it inside a still-running task can trigger cleanup during that task.
The same effect can expose `loading`/`on_loading` when a parent needs it.

Cancel pending work when a restore or clear supersedes a manually started request,
even if the new selection will not start another run. On unmount, cancel work and
release resources owned by the component while preserving parent-owned results;
an explicit clear is what resets those results. If cleanup can run inside the task
itself, guard cancellation with `task.pending and not task.is_current()`.

Cancellation cannot undo side effects already performed by a task or stop a
blocking operation already running through `asyncio.to_thread`. Prefer returned
outcomes over writes to external state, and guard unavoidable side effects against
an obsolete request or an unmounted owner after an `await`.

### `solara.use_thread` (legacy, still works)

```python
@solara.component
def MyComponent():
    # cancel parameter is OPTIONAL — only needed for cooperative cancellation
    # Workers can also be simple no-arg functions: def worker(): ...
    def worker(cancel: threading.Event):
        for i in range(100):
            if cancel.is_set():
                return None
            time.sleep(0.1)
        return "done"

    result = solara.use_thread(worker, dependencies=[], intrusive_cancel=False)

    if result.state == solara.ResultState.RUNNING:
        solara.ProgressLinear(indeterminate=True)
    elif result.state == solara.ResultState.FINISHED:
        solara.Success(f"Result: {result.value}")
    elif result.state == solara.ResultState.ERROR:
        solara.Error(f"Error: {result.error}")
```

### `use_task` vs `use_thread` API differences

These two hooks have **different return types** — don't confuse them:

| Attribute            | `use_thread` (returns `Result`)        | `use_task` (returns `Task`)  |
| -------------------- | -------------------------------------- | ---------------------------- |
| The exception object | `result.error` (Exception)             | `task.exception` (Exception) |
| Error check          | `result.state == ResultState.ERROR`    | `task.error` (bool)          |
| Running check        | `result.state == ResultState.RUNNING`  | `task.pending` (bool)        |
| Done check           | `result.state == ResultState.FINISHED` | `task.finished` (bool)       |
| Cancel               | `result.cancel()`                      | `task.cancel()`              |

### Key rules

- **Always provide `dependencies`** — omitting runs on every render
- **`dependencies=[]`** — runs once on mount
- **`dependencies=None`** — manual trigger only (for `use_task`)
- **Prefer `use_task`** over `use_thread` for new code (better performance, async support)
- **Check cancellation** in long loops when using `use_thread`
- **Batch state updates** — don't call `set_state` on every iteration

### Effects for reactive calculations

```python
@solara.component
def MyComponent():
    result = solara.use_reactive(None)

    def auto_calculate():
        if app_state.is_ready_for_calculation():
            result.set(compute(app_state.file_path.value))

    solara.use_effect(auto_calculate, [
        app_state.target_error.value,
        app_state.confidence_level.value,
    ])
```

## 6. Anti-Patterns

### Mutating reactive values in place

```python
# WRONG — Solara won't detect the change
my_list = solara.reactive([1, 2, 3])
my_list.value.append(4)  # Mutation, no re-render!

# CORRECT — Replace with a new object
my_list.value = [*my_list.value, 4]
```

### Returning different root widgets per state

```python
# WRONG — Solara keeps the first root alive
@solara.component
def MyComponent(has_data):
    if has_data:
        return solara.Card("Data view")  # Different root!
    else:
        return solara.Text("No data")    # Different root!

# CORRECT — Stable root, swap children
@solara.component
def MyComponent(has_data):
    with solara.Column():  # Stable root
        if has_data:
            solara.Card("Data view")
        else:
            solara.Text("No data")
```

### Hot reload masking bugs

Hot reloads rebuild the widget tree from scratch and can hide structural issues. If a reactive value changes but the component doesn't re-render, the fix is to ensure a stable root element — not to rely on hot reload.

### Imperative widget manipulation

```python
# WRONG — ipyvuetify thinking
widget.children = [new_child]
widget.hide()
widget.disabled = True

# CORRECT — Solara thinking (declarative)
@solara.component
def MyComponent():
    visible = solara.use_reactive(True)
    if visible.value:
        solara.Button("Click", disabled=not ready)
```

## 7. Conversion Checklist

For each ipyvuetify widget being converted:

### Preparation

- [ ] Read the original widget source completely
- [ ] Identify all traitlets (traits with `.tag(sync=True)`)
- [ ] Identify all `@observe` handlers
- [ ] Identify all bidirectional links (`link()`, `directional_link()`)
- [ ] Identify Vue templates if any (`template_file`, `.vue` files)
- [ ] Identify the public API (methods users call)

### Conversion

- [ ] Create `@solara.component` function with `value/on_value` signature
- [ ] Map traitlets to reactive state (`use_reactive`, `use_state`, or params)
- [ ] Convert `@observe` handlers to `use_effect` with explicit dependencies
- [ ] Convert imperative show/hide to conditional rendering
- [ ] Convert `children` manipulation to declarative Solara elements
- [ ] Replace Vue templates with Solara components or `reacton.ipyvuetify`

### Verification

- [ ] All hooks at the top, same order every render (see Hook Checklist)
- [ ] Stable root element (no conditional root returns)
- [ ] No in-place mutation of reactive values
- [ ] `del value, on_value` after `use_reactive` wrapping
- [ ] Google-convention docstring with Args section
- [ ] No early returns before hooks

## 8. Reference Examples

### Simple conversion: AdminButton

**Location**: `pysepal/solara/components/admin.py`

Shows: `use_state` for local state, `reacton.ipyvuetify` for Dialog/Tabs, conditional rendering instead of show/hide. Note: does not use `value/on_value` pattern because it has no parent-controlled state — it's a self-contained admin panel.

### Complex conversion: AoiView

**Location**: `pysepal/solara/components/aoi/aoi_view.py`

Shows: `value/on_value` pattern, `use_reactive` + `del`, `use_effect` for side effects, `use_task` for async processing, stable render tree, cleanup on unmount.

### Full app reference: sbae-design

**Location**: `~/1_modules/sbae-design/`

Shows: AppState singleton, MapApp layout, `use_thread` for long operations, `use_effect` for reactive calculations, modal/dialog management, strategy pattern.

## 9. Widget Conversion Status

### Already converted (Solara-native)

- `AdminButton` → `pysepal/solara/components/admin.py`
- `AoiView` → `pysepal/solara/components/aoi/aoi_view.py`
- `AoiResult` → `pysepal/solara/components/aoi/aoi_result.py`

### Bridge wrappers (ipyvuetify widget exposed via Solara, not truly converted)

- `FileInputComponent` → `pysepal/sepalwidgets/file_input.py` (wraps the ipyvuetify `FileInput` via `.element()` with manual state sync — not a Solara-native component)

### Pending conversion (in `pysepal/sepalwidgets/`)

- `Btn`, `DownloadBtn`, `TaskButton` (btn.py)
- `Alert`, `StateBar`, `Banner`, `Divider` (alert.py)
- `DatePicker`, `FileInput`, `AssetSelect`, `NumberField`, `SimpleSlider` (inputs.py)
- `Tile`, `TileAbout`, `TileDisclaimer` (tile.py)
- `Radio`, `RadioGroup` (radio.py)
- `Markdown`, `CopyToClip`, `StateIcon` (widget.py)
- `Dialog`, `Tooltip` (sepalwidget.py)
- `MapApp`, `ThemeToggle`, `RightPanel` (vue_app.py) — already work with Solara via Vue templates
- `App`, `AppBar`, `NavDrawer`, `DrawerItem`, `Footer` (app.py) — legacy layout, MapApp is the replacement
