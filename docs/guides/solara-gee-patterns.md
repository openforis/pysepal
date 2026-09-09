# Solara GEE Patterns

> New pysepal Solara apps must use `solara.reactive()` AppState state and
> `solara.lab.use_task` for non-blocking Earth Engine work.
> Do not scaffold new traitlets `.observe()` or `gee_interface.create_task()`
> flows for new apps.

## Session-Backed GEE Is the Default

For new Solara apps, the default pysepal setup is:

1. `@with_sepal_sessions` establishes the session for this runtime.
2. `SessionManager` creates `EESession(sepal_headers=...)`.
3. `SessionManager` wraps that session in `GEEInterface`.
4. Components retrieve that same session-backed interface with
   `get_current_gee_interface()`.

That means new Solara apps should assume they are using the full async
`ee-client` path backed by SEPAL headers.

In that mode, `GEEInterface` exposes both sync and async methods, but they do
not serve the same purpose:

- The `*_async` methods are the primary API for new Solara apps.
- The sync methods (`get_info`, `get_map_id`, `get_assets`, etc.) are bridge
  methods for blocking or legacy code.
- `GEEInterface`'s private event loop exists mainly to support those blocking
  sync wrappers and `gee_interface.create_task()`.

There is no separate public "async GEE getter". Use the regular
`get_current_gee_interface()` and call its `*_async` methods.

## Why `use_task` over `use_thread`

`solara.use_thread` works well for simple synchronous worker functions, but new
pysepal GEE apps should prefer `solara.lab.use_task` because it:

- Supports `async def` task functions, which matches the session-backed
  `GEEInterface` API.
- Returns a stable task object across renders with `.pending`, `.finished`,
  `.error`, `.exception`, `.value`, `.cancel()`, and `.is_current()`.
- Supports `dependencies=None`, which gives a clean button-triggered pattern
  instead of a reactive boolean trigger.
- Lets you opt out of thread-per-task execution with `prefer_threaded=False`,
  which is the right setting for GEE-bound coroutine tasks.

Use `use_thread` only for genuinely synchronous local work.

## Event Loop Rule for GEE

The rule is one event loop per app. `EESession` owns asyncio coordination
primitives such as locks and semaphores, and `ee-client` caches a single
`httpx.AsyncClient(http2=True)` per session. All of them bind lazily to the
first event loop that needs them, so a second loop breaks them under
contention.

There are two ways to end up with a second loop:

- `use_task(prefer_threaded=True)`. Solara runs the coroutine in a separate
  thread with its own event loop.
- `gee_interface.create_task(...)`. It hands the coroutine to `GEEInterface`'s
  private loop, running in its own thread. Because `get_info_async` delegates
  directly to `ee-client`, it runs on _whichever loop called it_ — so this is a
  second loop even when every `use_task` in the app sets
  `prefer_threaded=False`. Mixing the two scheduling styles in one app is what
  breaks, which is why the legacy `sw.TaskButton` must not be combined with
  `use_task` components.

Two consequences follow:

- Light testing can look fine. If a lock or semaphore is never contended, the
  code may appear to work across loops.
- Under contention, or once waiters are created, asyncio raises either
  `RuntimeError: ... is bound to a different event loop` or
  `RuntimeError: Non-thread-safe operation invoked on an event loop other than the current one` — which primitive loses the race varies between runs.

**The rule for new Solara GEE apps:**

- Use `await gee_interface.*_async(...)` directly for Earth Engine calls.
- When those calls live inside `solara.lab.use_task`, set
  `prefer_threaded=False` so the coroutine stays on Solara's current event
  loop.
- Use `asyncio.to_thread()` only for truly blocking local work, not for the
  normal SessionManager-backed GEE path.

```python
# CORRECT — session-backed Solara GEE call
result = await gee_interface.get_info_async(ee_object)

# CORRECT — keep GEE coroutine tasks on Solara's loop
@solara.lab.use_task(dependencies=None, raise_error=False, prefer_threaded=False)
async def gee_job(request):
    return await gee_interface.get_info_async(request.ee_object)

# NOT THE DEFAULT FOR NEW SOLARA GEE APPS
result = await asyncio.to_thread(gee_interface.get_info, ee_object)
```

## Canonical Pattern

When a page already retrieved `gee_interface = get_current_gee_interface()`, pass that same object down into `SepalMap` and any GEE-aware child components instead of inventing a parallel `async_gee_interface` path. This keeps one SessionManager-backed interface flowing through the tree.

The standard pattern for new apps is:

1. Keep request inputs, loading state, error state, result state, and submitted
   background task metadata in an `AppState` singleton built from
   `solara.reactive()`.
2. Get `gee_interface = get_current_gee_interface()` inside the Solara
   component.
3. Define a `@solara.lab.use_task(dependencies=None, raise_error=False, prefer_threaded=False)` task in the component.
4. On button click, build an immutable request snapshot and call the task
   manually with that snapshot.
5. Let the task return a small outcome object instead of mutating AppState
   directly.
6. Mirror the task state back into AppState in `solara.use_effect`.

Three rules matter:

- Await the session-backed `GEEInterface` async methods directly.
- Never read live reactive inputs inside a long-running task after it starts.
  Snapshot inputs first and pass them as task arguments.
- Pass the shared `gee_interface` to every helper that accepts one. Functions
  like `process_admin(gee_interface=...)` fall back to `GEEInterface()` when
  no interface is provided, which creates a throwaway instance with its own
  event loop and daemon thread on every call. This wastes resources and
  produces spurious "Closing GEEInterface" log spam on cancel/retry cycles.

## Loading, Error, and Result State in AppState

For a scaffolded app, AppState should usually contain at least:

- The current user inputs.
- `loading`: `bool`
- `error_message`: `str | None`
- `result`: computed direct result or `None`
- `submitted_task`: background task metadata or `None`

The task itself is not the source of truth for business state. The task is the
execution engine; AppState is the UI state.

This split keeps the pattern predictable:

- Button click clears stale result state and starts the task.
- `use_task` handles background execution.
- `use_effect` copies the finished/error state into AppState.
- The UI renders only from AppState.

## Direct Computation vs Background Submission

Use direct computation (via `await gee_interface.get_info_async(...)`) when:

- The result is small enough to render directly in the UI.
- The call usually finishes in a few seconds.
- You need an immediate value such as statistics, map bounds, map ids, or asset
  metadata.

Use background submission (via `await gee_interface.export_*_async(...)`) when:

- The work produces a file or asset instead of a small in-memory result.
- The reducer is large enough that timeout or memory errors are plausible.
- The user can continue working while Earth Engine finishes the job remotely.

Use `asyncio.to_thread(...)` only when a non-GEE step is actually blocking,
for example:

- local file I/O through a synchronous library
- CPU-heavy parsing or preprocessing
- legacy synchronous APIs that have no async equivalent

## Minimal Working Example

This example shows the full scaffold pattern in one file. It uses direct async
GEE calls on the session-backed interface.

```python
from dataclasses import dataclass
from typing import Any

import ee
import solara

from pysepal.solara import (
    get_current_gee_interface,
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
)
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    return setup_sessions()


class AppState:
    def __init__(self):
        self.asset_id = solara.reactive("USGS/SRTMGL1_003")
        self.scale = solara.reactive(90)
        self.loading = solara.reactive(False)
        self.error_message = solara.reactive(None)
        self.result = solara.reactive(None)


app_state = AppState()


@dataclass(frozen=True, slots=True)
class StatsRequest:
    asset_id: str
    scale: int


async def run_stats_request(gee_interface, request: StatsRequest) -> dict[str, Any]:
    image = ee.Image(request.asset_id).select(0)
    region = ee.Geometry.BBox(-123.6, 37.0, -121.8, 38.4)

    stats_object = image.reduceRegion(
        reducer=ee.Reducer.mean().combine(
            reducer2=ee.Reducer.minMax(),
            sharedInputs=True,
        ),
        geometry=region,
        scale=request.scale,
        maxPixels=1_000_000_000,
    )

    return await gee_interface.get_info_async(stats_object)


@solara.component
def StatsPanel():
    gee_interface = get_current_gee_interface()

    @solara.lab.use_task(
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )
    async def gee_job(request: StatsRequest) -> dict[str, Any]:
        return await run_stats_request(gee_interface, request)

    def sync_task_state():
        app_state.loading.value = gee_job.pending

        if gee_job.pending or gee_job.cancelled:
            return

        if gee_job.error:
            app_state.error_message.value = str(gee_job.exception)
            app_state.result.value = None
            return

        if gee_job.finished:
            app_state.error_message.value = None
            app_state.result.value = gee_job.value

    solara.use_effect(
        sync_task_state,
        [
            gee_job.pending,
            gee_job.cancelled,
            gee_job.finished,
            gee_job.error,
            gee_job.value,
            gee_job.exception,
        ],
    )

    def start_run():
        request = StatsRequest(
            asset_id=app_state.asset_id.value,
            scale=app_state.scale.value,
        )
        app_state.loading.value = True
        app_state.error_message.value = None
        app_state.result.value = None
        gee_job(request)

    with solara.Column():
        solara.InputText("Image asset id", value=app_state.asset_id)
        solara.InputInt("Scale", value=app_state.scale)
        btn_props = use_task_button(gee_job, on_start=start_run)
        TaskButtonComponent(label="Run", **btn_props, small=True)

        if app_state.loading.value:
            solara.Info("Running Earth Engine request...")
            solara.ProgressLinear(value=True)

        if app_state.error_message.value:
            solara.Error(app_state.error_message.value)
        elif app_state.result.value is not None:
            solara.Success(f"Direct result: {app_state.result.value}")


@solara.component
@with_sepal_sessions(module_name="my_solara_app")
def Page():
    setup_theme_colors()
    StatsPanel()
```

## Notes on the Example

- `dependencies=None` makes the task manual. It only runs when the user clicks a
  button.
- The request snapshot is a frozen dataclass. The task always runs against the
  exact inputs that were visible when the user clicked.
- The task returns a value. It does not mutate AppState directly.
- `sync_task_state()` is the only place that copies task state into AppState.
- `prefer_threaded=False` is deliberate. For session-backed GEE coroutines, we
  want one stable event loop, not a per-task thread loop.

## Recommended Scaffold Boilerplate

For new apps, the scaffolder should generate:

- An `AppState` with `loading`, `error_message`, `result`, and any
  background-submission metadata the workflow needs.
- A request dataclass and, when useful, an outcome dataclass.
- A `use_task(dependencies=None, raise_error=False, prefer_threaded=False)`
  hook inside the page or main feature component.
- A `solara.use_effect` block that mirrors the task state into AppState.
- A pure async function in `component/scripts/` that receives
  `gee_interface` plus the request snapshot and awaits `gee_interface.*_async`
  methods directly.

## Blocking I/O in Solara Components

`use_effect` runs synchronously on the render thread. Blocking I/O in a
`use_effect` freezes the UI. Solara recommends `use_task` or `use_thread`
for anything over ~100 ms.

For GEE/container apps, user-file I/O is not local filesystem I/O. Always read,
write, list, and create user files through the session `SepalClient`. Do not
wrap `Path.open`, `Path.write_text`, `os.listdir`, `os.walk`, `glob`, or
server-local `gpd.read_file(path)` calls in `asyncio.to_thread()` for user
workspace data; that only moves an unsafe container-filesystem access off the
render thread. If a library accepts bytes or a file-like object, first load the
user's file with `sepal_client.files.read_bytes(...)` and pass an in-memory object. If
the library only accepts local paths, do not wire that workflow into a
GEE/container app until there is a remote-aware pysepal adapter for it.

**For async task functions** that read user files, keep the file access through
`SepalClient` and move the synchronous HTTP/parsing work off the render thread:

```python
import io

async def load_user_csv(sepal_client, remote_path: str):
    payload = await asyncio.to_thread(sepal_client.files.read_bytes, remote_path)
    return await asyncio.to_thread(pd.read_csv, io.BytesIO(payload))
```

**For component-internal loading** (column lists, metadata), use `use_task`
with the request inputs as dependencies. In the component body:

```python
path = remote_path.value

async def _load_columns():
    if not path:
        return []
    payload = await asyncio.to_thread(sepal_client.files.read_bytes, path)
    frame = await asyncio.to_thread(pd.read_csv, io.BytesIO(payload), nrows=0)
    return list(frame.columns)

column_task = solara.lab.use_task(
    _load_columns,
    dependencies=[sepal_client, path],
    raise_error=False,
    prefer_threaded=False,
)

column_items = (column_task.value or []) if column_task.finished else []
loading_columns = column_task.pending
```

Bind `column_items` and `loading_columns` directly to the selector. The task reruns
when the client or path changes, including when the path is cleared; no trigger
effect or reactive copy of its result is needed. Report errors from an effect
observing `column_task.exception` through `use_notifications()`.

For results published to parent-owned state, use an effect after the task finishes.
See [Internal task state and result publication](solara-migration.md#internal-task-state-and-result-publication)
for cancellation and unmount behavior.

## AOI Method Restrictions

AoiView's `methods` parameter controls which selection methods are available.
Not all methods are safe in all deployment contexts.

| Method       | Requires              | Safe in GEE/container apps          | Safe in local/Voila    |
| ------------ | --------------------- | ----------------------------------- | ---------------------- |
| `ADMIN0/1/2` | GEE (GAUL) or GADM    | Yes                                 | Yes                    |
| `DRAW`       | Map + DrawControl     | Yes                                 | Yes                    |
| `ASSET`      | GEE asset access      | Yes                                 | Yes (with credentials) |
| `SHAPE`      | Local filesystem read | **No** — assumes server-local paths | Yes                    |
| `POINTS`     | Local filesystem read | **No** — same as SHAPE              | Yes                    |

### GEE / Container apps (multi-user, Docker)

Restrict to methods that don't read local files:

```python
AoiView(
    value=aoi_data,
    methods=["-SHAPE", "-POINTS"],  # exclude file-based methods
    gee=True,
    map_=sepal_map,
)
```

Or explicitly include only what you need:

```python
AoiView(
    value=aoi_data,
    methods=["ADMIN0", "ADMIN1", "ADMIN2", "DRAW", "ASSET"],
    gee=True,
    map_=sepal_map,
)
```

SHAPE and POINTS read files with `gpd.read_file` / `pd.read_csv` via
`asyncio.to_thread`. While this no longer blocks the event loop, the file
paths are server-local and may not resolve to the user's intended files in
a multi-user container. Use ASSET for GEE-backed vector data instead.

### Local / Voila apps (single-user)

All methods are safe:

```python
AoiView(
    value=aoi_data,
    methods="ALL",
    gee=False,
    map_=sepal_map,
)
```

## Async Button Convention

All buttons that trigger async work must use `TaskButtonComponent` — a single
toggle button that switches between action and cancel states. Do not render a
separate cancel button below the action button.

```python
from pysepal.solara.components.task_button import TaskButtonComponent, use_task_button

task = solara.lab.use_task(
    my_async_fn, dependencies=None, raise_error=False, prefer_threaded=False,
)
cancel_reason = solara.use_ref(None)

# Effect mirrors task state → app state (always use full dependency set)
def handle_task_state():
    if task.pending:
        app_state.loading.value = True
        return
    app_state.loading.value = False
    if task.finished and task.value is not None:
        app_state.result.value = task.value
    elif task.error:
        app_state.error_message.value = str(task.exception)
    elif task.cancelled:
        if cancel_reason.current == "user":
            app_state.error_message.value = "Cancelled"
        cancel_reason.current = None

solara.use_effect(
    handle_task_state,
    [task.pending, task.finished, task.error, task.cancelled],
)

def start():
    cancel_reason.current = None
    app_state.loading.value = True
    task(StatsRequest(asset_id=app_state.asset_id.value, scale=app_state.scale.value))

btn_props = use_task_button(task, on_start=start, cancel_reason_ref=cancel_reason)
TaskButtonComponent(label="Run", **btn_props, small=True, block=True)
```

### Rules

1. Task functions return outcomes — never mutate reactive state directly.
2. Build an immutable request snapshot at click time.
3. Single toggle button — no separate cancel button. Ever.
4. `prefer_threaded=False` for GEE coroutines.
5. `task.value is not None` — never use bare truthiness (DataFrames can be falsey).
6. Idempotent map operations — use stable layer keys, replace not accumulate.
7. Full effect dependencies — `[task.pending, task.finished, task.error, task.cancelled]`.

### Non-GEE blocking I/O

Wrap sync functions that do CPU-heavy work or read packaged, non-user assets
with `asyncio.to_thread` inside the `use_task` async function. The button
wiring is identical:

```python
async def compute_summary(request):
    result = await asyncio.to_thread(build_summary_table, request.records)
    return SummaryOutcome(rows=result)

task = solara.lab.use_task(compute_summary, dependencies=None, raise_error=False, prefer_threaded=False)
btn_props = use_task_button(task, on_start=lambda: task(snapshot))
TaskButtonComponent(label="Compute", **btn_props, block=True)
```

### Cancel semantics

| Task type                           | What `task.cancel()` does                                               |
| ----------------------------------- | ----------------------------------------------------------------------- |
| GEE async (`get_info_async`, etc.)  | Stops the local coroutine                                               |
| Remote EE export (`export_*_async`) | Stops local wait — does **not** cancel the remote job                   |
| `asyncio.to_thread(sync_fn)`        | Cancels the async wrapper; thread keeps running but result is discarded |

## When `asyncio.to_thread()` Is Still Appropriate

`asyncio.to_thread()` is still valid in Solara apps. It is just not the default
pattern for SessionManager-backed GEE calls.

Use it for:

- blocking reads of packaged app assets or archive libraries that are not user
  workspace files
- CPU-heavy synchronous transformations
- legacy sync-only helpers that are unrelated to the session-backed GEE path
- intentionally using the local single-user `GEEInterface` sync bridge outside
  the standard SEPAL-header Solara architecture

## `GEEInterface` Notes

No functional `GEEInterface` changes are required for this pattern.

The existing async API surface is sufficient for new Solara apps. The sync API
surface remains useful for notebooks, local scripts, and legacy code. The main
documentation requirement is to describe the intended Solara usage correctly:
new session-backed apps should be async-first.

## Notifications for Async Work

When a task is user-visible, pair `solara.lab.use_task` with the pysepal
notification system instead of inventing a separate alert flow.

Default pattern:

1. Mount `NotificationProvider()` once in the page or shared layout.
2. Call `use_notifications()` inside the component that owns the task.
3. Wrap the async body in `with notifications.track(...):`.
4. Publish final success, error, or cancel feedback after the task settles.

Use notifications for UX, not persistence. The notification bus is kernel-scoped
and in-memory.

For detailed shell placement, route/kernel scope, and fallback behavior, read
[Solara Notifications](./solara-notifications.md).
