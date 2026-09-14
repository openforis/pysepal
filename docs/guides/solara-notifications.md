# Solara Notifications with pysepal

> Use this guide when a pysepal Solara app needs user-facing toast notifications,
> running-task status, or a shared floating notification UI.

## What the Notification System Is

The pysepal notification system is a kernel-scoped, in-memory UI notification
layer for Solara apps.

It provides:

- toast notifications for success, info, warning, error, and cancel states
- a floating task pill for active work
- a task log derived from tracked task history
- a Vue-backed overlay that integrates with `MapApp`

It does **not** provide:

- durable event storage
- cross-kernel or cross-process messaging
- audit logging
- guaranteed delivery after kernel restart

Use it for live app UX, not for backend workflow persistence.

## Core Pieces

The main API lives in `pysepal.solara.notifications`:

- `NotificationProvider` — mounts the notification UI and owns the kernel-scoped bus
- `use_notifications()` — returns a `Notifier` bound to the current kernel bus
- `notify()` and `track_task()` — global escape hatches for non-component code
- `Notifier.track(...)` — returns a `TaskTracker` context manager for long-running work
- `NoopNotifier` — what `use_notifications()` returns with no provider mounted; it
  warns and logs rather than dropping messages quietly

Conceptually:

1. `NotificationProvider()` mounts once at app-shell level.
2. Components call `use_notifications()`.
3. Components publish toasts or tracked tasks.
4. The notification UI reacts to the shared bus state.

## Scope Rules

The isolation boundary is the live app runtime session, not the route.
Notifications are scoped to the current app runtime in three contexts:

- Solara server apps launched with `solara run`
- Voila apps launched from a notebook kernel
- Plain Jupyter Notebook/Lab, scoped to the active notebook kernel

- One browser page connection usually maps to one Solara virtual kernel under `solara run`.
- Voila and Jupyter scope to the active notebook kernel.
- The notification bus is keyed by the pysepal runtime session id.
- Routes inside the same live page share the same notification history.
- Separate browser page loads get separate kernels and therefore separate histories.

This means:

- mount one provider per app shell
- allow many consumers to call `use_notifications()`
- do not assume route changes create isolated notification buses

If an app launcher opens `/fcdm` and `/basin-rivers` as separate pages, each app
gets its own history. If those are route transitions inside one live page, they
share the same history.

## Mounting Pattern

Mount `NotificationProvider()` once near the top of the app shell.

### Single-page app

```python
@solara.component
@with_sepal_sessions(module_name="my_app")
def Page():
    setup_theme_colors()
    NotificationProvider()
    AppContent()
```

### Multipage app with shared layout

If all routes should share one notification surface, mount the provider in the
shared layout instead of inside each page.

```python
@solara.component
def Layout(children=[]):
    NotificationProvider()
    solara.Column(children=children)
```

### Voila apps

Voila apps use the same mounting pattern:

```python
@solara.component
def Page():
    NotificationProvider()
    AppContent()
```

The provider uses the active Voila notebook kernel as the notification bus
scope. No Solara server context is created or required.

### What not to do

Do not mount a separate provider in every page if those pages can coexist in the
same kernel. The bus is shared anyway, and multiple providers can render
multiple overlays against the same state.

## Using `use_notifications()` Inside Components

The normal component pattern is:

```python
from pysepal.solara.notifications import NotificationProvider, use_notifications

@solara.component
def ResultsPanel():
    notifications = use_notifications()

    def handle_ready():
        notifications.success("Results loaded")
```

Toast methods:

- `success(message)`
- `info(message)`
- `warning(message)`
- `error(message)`
- `cancel(message)`
- `dismiss(toast_id)`

If no provider is mounted, `use_notifications()` returns a `NoopNotifier`.
That means toast calls are silently dropped unless the component provides its own
fallback UX.

## Tracking Long-Running Tasks

Use `notifications.track(...)` together with `solara.lab.use_task` for
non-blocking work.

```python
@solara.component
def StatsPanel():
    notifications = use_notifications()
    gee_interface = get_current_gee_interface()

    @solara.lab.use_task(
        dependencies=None,
        raise_error=False,
        prefer_threaded=False,
    )
    async def run_job(request):
        with notifications.track("Loading statistics", total_steps=3) as task:
            task.step("Validating input")
            task.step("Querying Earth Engine")
            result = await gee_interface.get_info_async(request.ee_object)
            task.step("Formatting result")
            return result
```

Use task tracking when:

- the work is async or long-running
- the user benefits from a visible running-state indicator
- you want a task log instead of only final toasts

Use plain toasts when:

- the event is immediate
- there is no meaningful progress to report

## Recommended Async Pattern

For new GEE-based Solara apps:

- use `solara.reactive()` AppState
- use `solara.lab.use_task(..., prefer_threaded=False)`
- snapshot request inputs before starting work
- use `notifications.track(...)` inside the task body
- mirror task results back into AppState in `solara.use_effect`

This matches the current session-backed async GEE path and avoids loop-hopping
problems.

## When No Provider Is Mounted

`use_notifications()` returns a `NoopNotifier`, and nothing reaches the screen.
That is not silent:

- resolving without a bus raises a `UserWarning` naming `NotificationProvider`,
  once per call site
- every dropped message is logged at `WARNING` with its text, so an error the
  user never saw is still findable in the server log

Treat both as a bug report about the app, not as a supported mode. A missing
provider means the error channel is off, and an app whose failures go nowhere
looks like an app that never fails. Mount `NotificationProvider()` once at the
root, above every component that notifies.

If a component genuinely has to run both inside and outside a shell — a widget
published for reuse, say — check what you got back and fall back to inline
feedback:

```python
from pysepal.solara.notifications import NoopNotifier, use_notifications

notifications = use_notifications()
standalone = isinstance(notifications, NoopNotifier)
```

## Global Escape Hatches

```python
from pysepal.solara.notifications import notify, track_task
```

- `notify(message, type_="info")` — one toast, no component
- `track_task(title, total_steps=None)` — the same context manager
  `notifications.track(...)` returns

Both resolve the current scope's bus themselves, which is the whole point:
there is no notifier to receive and no prop to thread. Reach for them where a
hook cannot go.

**A decorator wrapping app callbacks.** It has no component to call
`use_notifications()` from, and threading a notifier through every decorated
function would defeat the decorator:

```python
from functools import wraps

from pysepal.solara.notifications import notify


def report_failures(func):
    """Turn an unhandled exception into a toast, and re-raise it."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as error:
            notify(str(error), type_="error")
            raise

    return wrapper
```

**A worker thread.** `asyncio.to_thread` copies the kernel context, so the
scope still resolves and the toast lands on the right connection's bus:

```python
import asyncio

from pysepal.solara.notifications import track_task


def convert_rasters(paths):
    """Blocking file work; no component on this stack."""
    with track_task("Converting rasters", total_steps=len(paths)) as task:
        for path in paths:
            task.step(f"Converting {path.name}")
            _convert(path)


await asyncio.to_thread(convert_rasters, paths)
```

**A script or a notebook cell** that drives app code directly and has no render
context at all.

Caveats:

- with no provider mounted, `notify()` logs the message at `WARNING` and drops
  the toast; `track_task()` returns a tracker that logs and does nothing
- they resolve the scope on every call, so a long loop should open one
  `track_task` rather than emit a toast per iteration
- inside a component, prefer `use_notifications()`: it memoizes on the bus and
  keeps the dependency visible in the component body

## MapApp Integration

The notification UI is designed to coexist with `MapApp`.

`MapApp.vue` publishes CSS custom properties such as
`--sepal-notification-right-offset`, and the Vue notification UI uses them to
position the task pill relative to the right panel.

Practical rule:

- if the app uses `MapApp`, mount `NotificationProvider()` in the same page or
  shell so the overlay can consume the active layout variables

## Safety and Limits

The notification system is safe for live, per-kernel app UX.

It is not a replacement for durable logs or event infrastructure.

Important limits:

- state is in-memory only
- restart the kernel and history is lost
- identical toasts are deduplicated within a short time window
- only the newest error toast is retained in the toast queue
- only the newest few toasts are visible in the overlay
- finished task history is capped and older finished tasks are pruned

One guarantee it does make: a subscriber may publish to the bus from inside
its own callback. The nested publication is deferred until the dispatch in
progress finishes, so every subscriber ends on the state the bus holds
rather than on whichever list reached it last.

## Default Scaffold Rule

When building a new pysepal Solara app that has async work or user-visible
status transitions:

- mount `NotificationProvider()` once in the app shell
- use `use_notifications()` inside pages and major tiles
- use `notifications.track(...)` for long-running jobs
- use final success/error/cancel toasts for task completion state
- do not build a second custom alert system unless the app has a very specific
  UX reason
