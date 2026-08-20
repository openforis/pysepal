# Building Solara Apps with pysepal

> **IMPORTANT**: Read this guide BEFORE creating a new SEPAL module with pysepal + Solara.
> Every pattern here is grounded in working apps: `sepal_mgci`, `se.plan`, `sbae-design`.
>
> For new GEE-based Solara apps, use the `solara.reactive()` +
> `solara.lab.use_task(prefer_threaded=False)` pattern in
> [Solara GEE Patterns](./solara-gee-patterns.md) and await
> `gee_interface.*_async(...)` directly.
> User files in GEE/container apps must always be read, listed, created,
> and written through the session `SepalClient`; never write user data to the
> container filesystem.
> For user-facing app status, mount `NotificationProvider()` once at the app
> shell and follow [Solara Notifications](./solara-notifications.md).
> The traitlets `create_task()` and `.observe()` flows are legacy patterns for
> existing apps, not new scaffolds.

## 1. Entry Point Pattern

Every pysepal Solara app follows this exact initialization sequence in `solara_app.py`:

```python
import solara
from pysepal.solara import (
    setup_sessions,
    setup_solara_server,
    setup_theme_colors,
    with_sepal_sessions,
    get_current_gee_interface,
    get_current_sepal_client,
    get_current_drive_interface,
)

# 1. Server setup (module level, runs once)
setup_solara_server(extra_asset_locations=[])

# 2. Session setup (per kernel, runs on each new browser tab)
@solara.lab.on_kernel_start
def on_kernel_start():
    return setup_sessions()

# 3. Main component with session decorator
@solara.component
@with_sepal_sessions(module_name="my_module_name")
def Page():
    setup_theme_colors()

    # 4. Get session interfaces (per-user, per-tab)
    gee_interface = get_current_gee_interface()
    sepal_client = get_current_sepal_client()

    # 5. Pass interfaces to components/models
    # ...your app here...
```

### Initialization order matters

1. `setup_solara_server()` — module level, configures Solara (kernel timeout, assets)
2. `setup_sessions()` — in `@solara.lab.on_kernel_start`, creates SessionManager
3. `@with_sepal_sessions` — on `Page()`, establishes the session for this runtime
4. `get_current_*()` — inside component, retrieves session-bound interfaces

### Where credentials come from

pysepal decides a session's credential source from **runtime topology** — what
kind of process the app is in — and never by probing credentials or checking
whether a request carries headers. In order:

| Condition                                  | Source           | Meaning                                             |
| ------------------------------------------ | ---------------- | --------------------------------------------------- |
| `PYSEPAL_DEV_AUTH` armed, no SEPAL headers | `DEV_AUTH`       | one developer login for the whole process           |
| `SEPAL=true` (a SEPAL sandbox)             | `PROCESS`        | app-manager app; the machine credentials are yours  |
| `PYSEPAL_LOCAL_EE` armed, no SEPAL headers | `PROCESS`        | your own Earth Engine credentials, for local dev    |
| running under a Solara server              | `PER_CONNECTION` | app-launcher container; one identity per connection |
| anything else (Voila, Jupyter, a script)   | `PROCESS`        | machine credentials                                 |

`PER_CONNECTION` never falls back. Missing or invalid SEPAL headers there raise
`MissingSepalHeadersError`, because an app-launcher container mounts the
_platform_ GEE service-account key at `~/.config/earthengine/credentials` — a
fallback would silently hand every user that one identity.

Real SEPAL headers always win over `PYSEPAL_DEV_AUTH`, so arming it in a
deployed container changes nothing. The same holds for `PYSEPAL_LOCAL_EE`, which
is the local-development switch for an app that only needs Earth Engine: it runs
`solara run` on your own `~/.config/earthengine/credentials` with no SEPAL login,
and therefore with no `SepalClient`.

The two are mutually exclusive and `PYSEPAL_DEV_AUTH` wins — it is rule 1,
`PYSEPAL_LOCAL_EE` is rule 3, so arming both leaves the second inert. Reach for
`PYSEPAL_DEV_AUTH` when the app needs the SEPAL side (file storage, exports to
your workspace) and `PYSEPAL_LOCAL_EE` when it only talks to Earth Engine.
`PYSEPAL_LOCAL_EE` changes nothing outside `solara run`: Voila, Jupyter and
scripts already resolve `PROCESS` from the same credentials file.

`get_current_sepal_client()` returns `None` on a `PROCESS` runtime that has no
SEPAL identity of its own — a laptop notebook or a CI script. In a SEPAL
sandbox it returns a real client, so code that branches on
`if sepal_client:` takes the SEPAL API path there and the local-filesystem path
elsewhere.

### The `@with_sepal_sessions` decorator

This decorator is **required** on the main `Page()` component whenever the app
needs `GEEInterface`, `SepalClient` or `GDriveInterface` — which is almost every
app. An app that needs none of them omits it; see
[Apps that don't use Earth Engine](#apps-that-dont-use-earth-engine) below. It:

- Establishes the session for this runtime: per connection under a Solara
  server, otherwise the process session
- Provides `GEEInterface`, `SepalClient` and `GDriveInterface`
- Raises on missing or invalid SEPAL headers in a per-connection runtime,
  instead of waiting for headers that will never arrive
- Handles auth errors gracefully

```python
@solara.component
@with_sepal_sessions(module_name="sdg_indicators/15.4.2")
def Page():
    # This only renders after session is ready
    gee_interface = get_current_gee_interface()  # Session already established above
```

### Apps that don't use Earth Engine

Two shapes, and only one of them needs a session at all.

**The app needs nothing from SEPAL** — pure UI, local computation, or its own
API. Drop `@with_sepal_sessions` and keep the rest of the entry point:

```python
import solara
from pysepal.solara import setup_sessions, setup_solara_server, setup_theme_colors

setup_solara_server(extra_asset_locations=[])


@solara.lab.on_kernel_start
def on_kernel_start():
    return setup_sessions()


@solara.component
def Page():
    setup_theme_colors()
    # ...your app here...
```

Keep `setup_sessions()` even though there is no session to create. The cleanup
function it returns is what clears this connection's scoped UI state — theme,
locale — when the kernel shuts down. Without it that state accumulates one entry
per connection for the life of the process.

Everything that is not a credential still works: theme, locale, notifications
and every `sepalwidgets` component. `get_current_theme_state()` never raises, by
design. `get_current_sepal_client()` returns `None`, and
`get_current_gee_interface()` raises `SepalSessionError` — do not call it.

This shape runs under `solara run` with no SEPAL headers and no
`PYSEPAL_LOCAL_EE`, because nothing ever asks for a credential.

**The app needs SEPAL file storage but not Earth Engine.** Keep the decorator —
`SepalClient` only exists inside a session. Know what it costs today:
`_create_connection_session` builds `EESession`, `GEEInterface`, `SepalClient`
and `GDriveInterface` unconditionally, so every connection gets an Earth Engine
event-loop thread it never uses. Making that build lazy is planned for 4.1 and
changes no API you write against.

#### Maps without Earth Engine

Pass `gee=False`. `SepalMap` defaults to `gee=True`, and in a non-GEE app that
default does something you do not want:

```python
SepalMap(gee=False)   # local rasters, vectors, basemaps, PMTiles
```

With `gee=True` and no `gee_interface=`, `SepalMap.__init__` builds a
session-less `GEEInterface` **and** calls `su.init_ee()`, which reads
`~/.config/earthengine/credentials` directly and initialises the global `ee`
module. In an app-launcher container that file is the platform service account.

Since 4.0 a session-less `GEEInterface` **raises `SepalSessionError` in a
per-connection runtime**, and the map inherits that: `SepalMap()` with no
`gee_interface` fails in a container instead of rendering on the platform
identity. The same guard covers `AoiModel`, the `sepalwidgets` asset inputs and
`process_admin`, which all have the same `gee_interface or GEEInterface()`
fallback. Elsewhere — a notebook, a script, a SEPAL sandbox — nothing changes:
those runtimes own their machine credentials.

So in a container app, always pass one or the other:

```python
SepalMap(gee=False)                                    # no Earth Engine layers
SepalMap(gee_interface=get_current_gee_interface())    # Earth Engine layers
```

## Notification Shell Pattern

New pysepal Solara apps that perform async work should treat notifications as a
first-class part of the app shell.

Default rule:

- mount `NotificationProvider()` once near the top of the app shell
- let child pages, tiles, and widgets call `use_notifications()`
- do not mount a separate provider in every subpage unless each page truly runs
  in a separate kernel

The notification bus is scoped to the current pysepal app runtime session, not
the route. Under `solara run`, that scope is the Solara virtual kernel. Under
Voila or a plain Jupyter notebook, that scope is the active notebook kernel. If
routes are rendered inside
one live page, they share notification history. If an app launcher opens each
route as a separate browser page load, each page gets its own runtime session
and its own notification history.

For the full architecture and usage patterns, read
[Solara Notifications](./solara-notifications.md).

## Export Shell Pattern

Apps that produce GEE-backed layers users might want to take out of the app
should drop in `ExportLauncher`. It handles Earth Engine asset, Google Drive,
and SEPAL workspace targets through one button, including folder creation
and Drive-to-SEPAL staging. Declare one `ExportSource` per exportable layer
and pass the tuple to `ExportLauncher(sources=...)`.

For the full component API (sources, `ResolvedExport`, canonical file-format
constants, `use_export_dialog` for custom layouts, and testing helpers),
read [Solara Export](./solara-export.md).

## 2. Session Interfaces

Three interfaces are available per user session:

| Interface         | Getter                                       | Purpose                                                                                               |
| ----------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `GEEInterface`    | `get_current_gee_interface()`                | Earth Engine API calls (async/sync)                                                                   |
| `SepalClient`     | `get_current_sepal_client(module_name=None)` | SEPAL file/task operations; one client per `module_name`, defaulting to the route currently rendering |
| `GDriveInterface` | `get_current_drive_interface()`              | Google Drive export/import                                                                            |

### One session, one client per module

A kernel holds exactly one session — one `GEEInterface` (and therefore one private
event loop), one `GDriveInterface` — and a `SepalClient` per `module_name`. Each
`@with_sepal_sessions(module_name="…")` route gets its own results directory, and
`get_current_sepal_client()` inside that route returns that route's client. Pass
`module_name` explicitly to reach another route's client.

### Theme is not session state

`get_current_theme_state()` is keyed by the runtime scope, not by the SEPAL session:
it never raises and never touches credentials, so it works identically under
`solara run`, Voila, plain Jupyter and pytest. A fresh state starts at `mode="auto"`.
The legacy `~/.sepal-ui-config` theme file is removed in 4.0 — theme state is
never read from or written to disk.

### Getting interfaces

Always call getters **inside the component**, never at module level:

```python
# WRONG — gets fallback without headers
gee_interface = get_current_gee_interface()  # Module level!

@solara.component
def Page():
    ...

# CORRECT — gets session-bound interface with sepal headers
@solara.component
@with_sepal_sessions(module_name="my_app")
def Page():
    gee_interface = get_current_gee_interface()
```

### Passing interfaces to sub-components

```python
@solara.component
@with_sepal_sessions(module_name="my_app")
def Page():
    gee_interface = get_current_gee_interface()
    sepal_client = get_current_sepal_client()

    # Pass to models
    model = MyModel(gee_interface=gee_interface, sepal_client=sepal_client)

    # Pass to map
    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(gee=True, gee_interface=gee_interface),
        [id(gee_interface)],
    )

    # Pass to tiles/widgets
    MyTile(model=model, map_=sepal_map)
```

### User file boundary

For GEE/container apps, `SepalClient` is the only runtime API for user files.
This rule applies both in local development and after deployment behind the
SEPAL app launcher. The container filesystem is for application code, Python
packages, and bundled static assets; it is not a user workspace and should not
receive user uploads, generated reports, CSVs, rasters, recipes, or temporary
state.

Do not use `pathlib.Path`, `os`, `shutil`, `glob`, `open()`, or library calls
that walk/read/write server-local paths for user data. Those calls inspect the
container, not the authenticated user's SEPAL workspace, and they can mix users
or lose data when the container restarts.

Use the session client instead:

```python
@solara.component
@with_sepal_sessions(module_name="my_app")
def Page():
    sepal_client = get_current_sepal_client()

    results_dir = sepal_client.files.mkdir(
        f"{sepal_client.results_path}/exports",
        parents=True,
    )
    sepal_client.files.write(f"{results_dir}/summary.csv", csv_text, overwrite=True)
    content = sepal_client.files.read_bytes(f"{results_dir}/summary.csv")
    files = sepal_client.files.list(str(results_dir))
```

Remote paths are POSIX-style strings relative to the user's SEPAL workspace, or
absolute paths under `/home/sepal-user`. Do not branch on `DEPLOY_ENV` to fall
back to local filesystem writes for a container app; keep the same
`SepalClient` path in tests, local runs, and production.

### GEEInterface async methods

The session-bound `GEEInterface` returned by `get_current_gee_interface()`
already exposes both sync and async methods. For new Solara apps, the async API
is the default. There is no separate async getter.

When you call those methods inside `solara.lab.use_task`, set
`prefer_threaded=False` so the GEE coroutine stays on Solara's current event
loop instead of hopping to a per-task thread loop.

```python
@solara.lab.use_task(
    dependencies=None,
    raise_error=False,
    prefer_threaded=False,
)
async def load_stats(ee_object):
    return await gee_interface.get_info_async(ee_object)


# Fetch asset info
info = await gee_interface.get_asset_async(asset_id)

# List user's assets
assets = await gee_interface.get_assets_async(folder)

# Get computed value
result = await gee_interface.get_info_async(ee_object)

# Export to Drive or Assets
await gee_interface.export_table_to_drive_async(collection, description, folder)
await gee_interface.export_image_to_asset_async(image, asset_id=asset_id)
```

`gee_interface.create_task(...)` remains available for legacy code paths, but it
is not the scaffold default for new Solara apps.

## 3. Directory Structure

```
my_module/
├── solara_app.py              # Entry point
├── run_solara.sh              # Dev run script (sources .env)
├── .env                       # Environment variables
├── requirements.txt           # Dependencies
├── Dockerfile                 # Container build
├── docker-compose.yml         # SEPAL platform deployment
├── docker-compose.override.yml # Local dev overrides
├── supervisord.conf           # Process management
├── logging_config.toml        # Logging configuration
├── component/
│   ├── model/                 # State management
│   │   ├── __init__.py
│   │   ├── app_model.py       # UI state (steps, active tab, etc.)
│   │   └── state_manager.py   # AppState with solara.reactive() (or traitlets Model)
│   ├── tile/                  # Major UI sections (dialogs, panels)
│   │   ├── __init__.py
│   │   ├── upload.py
│   │   ├── export.py
│   │   └── landing.py
│   ├── widget/                # Reusable Solara components
│   │   ├── __init__.py
│   │   ├── map.py             # SepalMap extension
│   │   └── custom_widgets.py
│   ├── scripts/               # Pure Python logic (no UI)
│   │   ├── __init__.py
│   │   └── calculations.py
│   └── parameter/             # Constants, paths, config
│       ├── __init__.py
│       └── directory.py       # Local/remote file management
└── assets/                    # Static files (CSS, images)
```

## 4. State Management

### Option A: AppState singleton with `solara.reactive()` (required for new apps)

```python
# component/model/state_manager.py
import solara

class AppState:
    def __init__(self):
        self.file_path = solara.reactive(None)
        self.aoi_data = solara.reactive(None)
        self.results = solara.reactive(None)
        self.is_processing = solara.reactive(False)

    def is_ready_for_calculation(self) -> bool:
        return self.file_path.value is not None

app_state = AppState()

# Usage in components:
# from component.model import app_state
# app_state.file_path.value = "/path/to/file"
```

### Option B: traitlets Model (legacy only, used by sepal_mgci, se.plan)

```python
# component/model/model.py
from pysepal.model import Model
import traitlets as t

class MyModel(Model):
    file_path = t.Unicode(None, allow_none=True).tag(sync=True)
    results = t.Dict({}).tag(sync=True)

    def __init__(self, gee_interface=None, sepal_client=None, **kwargs):
        self.gee_interface = gee_interface
        self.sepal_client = sepal_client
        super().__init__(**kwargs)
```

### When to use which

| Pattern                          | Use when                                             |
| -------------------------------- | ---------------------------------------------------- |
| `AppState` + `solara.reactive()` | New apps, pure Solara components                     |
| traitlets `Model`                | Existing apps, ipyvuetify widgets, need `.observe()` |

### Persist and restore an AOI

`AoiView` has two channels. `value`/`on_value` carries the `AoiResult` — the
GeoDataFrame and the Earth Engine object — which is not serializable. `spec`/`on_spec`
carries the `AoiSpec`, the small JSON-safe record of what the user picked. Persist the
spec; the result is rebuilt from it.

```python
from pysepal.solara.components.aoi import AoiSpec, AoiView

@solara.component
def Page():
    aoi = solara.use_reactive(None)
    spec = solara.use_memo(load_saved_spec, [])  # AoiSpec | None

    AoiView(value=aoi, spec=spec, on_spec=save_spec, map_=my_map)
```

`save_spec` receives an `AoiSpec`; store `spec.to_dict()` and rebuild it with
`AoiSpec.from_dict(...)`. Setting `spec` to a different value restores again — the
component does not need a remount.

By default a restored spec is processed straight away, so `aoi.value` holds a usable
result and the map shows the AOI. Pass `autoselect=False` to fill the form and leave
the run to the user.

Clearing the AOI publishes `None` on this channel, so `save_spec(None)` records the
clear and the next load starts empty rather than resurrecting what the user threw away.
Setting `spec` to `None` from outside is a no-op, not a reset — use `clear_ref` for that.

A spec naming a method the picker does not offer is refused with a warning, so an ASSET
spec cannot be restored into a `gee=False` view.

**Deployment note.** SHAPE and POINTS specs carry a file path on the machine that ran
the picker. Those two methods are not safe in multi-user container apps (see
"AOI Method Restrictions" in `solara-gee-patterns.md`), so a persisted path is only
meaningful for local and Voila deployments.

`demo_apps/solara_aoi_app/` is a runnable version of exactly this.

## 5. Map Integration

```python
from pysepal import mapping as sm
from pysepal.sepalwidgets.vue_app import MapApp
from pysepal.solara import get_current_theme_state

@solara.component
def Page():
    gee_interface = get_current_gee_interface()

    # Scope-keyed theme state (dark/light mode; auto follows system)
    theme_state = get_current_theme_state()

    # Create map with GEE support (memoized to avoid re-creation)
    sepal_map = solara.use_memo(
        lambda: sm.SepalMap(
            gee=True,
            gee_interface=gee_interface,
            theme_state=theme_state,
        ),
        [id(gee_interface)],
    )

    # Use MapApp layout (map background + sidebar + right panel)
    MapApp.element(
        app_title="My App",
        app_icon="mdi-earth",
        main_map=[sepal_map.get_map_widget()],
        theme_state=theme_state,
        steps_data=[...],
        right_panel_content=[...],
    )
```

> `SepalMap(theme_toggle=...)` / `MapApp.element(theme_toggle=[...])` still
> work but emit a `DeprecationWarning`. See `migration-notes-v3.4.md` § 7.

## 6. Button & Icon Sizing

The right panel and dialogs are narrow (~450 px). Use `small=True` on all
buttons and chips inside them. Navigation drawer icons keep default size.

| Context                                                      | Rule                                           |
| ------------------------------------------------------------ | ---------------------------------------------- |
| Buttons in right panel / sidebar content                     | `small=True` (add `block=True` for full-width) |
| Icon-only buttons (close, edit, toolbar)                     | `icon=True, small=True`                        |
| Chips (stats, tags, year selectors)                          | `small=True` (or `x_small=True` for inline)    |
| Dialog action buttons (OK / Cancel)                          | `small=True`                                   |
| Navigation drawer icons (`steps_data`, `right_panel_config`) | Default size — never `small=True`              |

## 7. Deployment

### `.env` file

```bash
PYSEPAL_DEV_AUTH=1                  # One developer login for the process (local dev only)
LOCAL_SEPAL_USER=admin              # Dev credentials
LOCAL_SEPAL_PASSWORD=yourpassword
SEPAL_HOST=yourinstance.sepal.io    # SEPAL platform host

# Alternative to the four lines above for a GEE-only app: no SEPAL login, no
# SepalClient, Earth Engine from ~/.config/earthengine/credentials.
# PYSEPAL_LOCAL_EE=1
```

### `run_solara.sh` (local dev)

```bash
#!/bin/bash
SOLARA_FILE="${1:-solara_app.py}"
PORT="${2:-8900}"

# Source .env
while IFS= read -r line; do
  [[ $line =~ ^#.*$ || -z $line ]] && continue
  if [[ $line =~ ^([^=]+)=(.*)$ ]]; then
    export "${BASH_REMATCH[1]}=${BASH_REMATCH[2]}"
  fi
done < .env

solara run "$SOLARA_FILE" --port $PORT --no-open
```

### `Dockerfile`

```dockerfile
FROM mambaorg/micromamba:latest

USER root
RUN apt-get update && apt-get install -y supervisor netcat-openbsd curl && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/local/lib/myapp

COPY requirements.txt .
RUN micromamba create -n myapp python=3.10 pip -c conda-forge -y && \
    micromamba run -n myapp pip install -r requirements.txt

COPY . .
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 8765
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
```

### `supervisord.conf`

```ini
[supervisord]
nodaemon=true

[program:solara]
command=bash -c "micromamba run -n myapp solara run solara_app.py --host=0.0.0.0 --root-path=/api/app-launcher/my_module --production --port=8765"
autostart=true
autorestart=true
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
```

### `docker-compose.yml`

```yaml
services:
  myapp:
    build: .
    volumes:
      - ${EE_CREDENTIALS_PATH:-${HOME}/.config/earthengine/credentials}:/root/.config/earthengine/credentials
    environment:
      FORWARDED_ALLOW_IPS: "*"
      SEPAL_HOST: "${SEPAL_HOST}"
      PYSEPAL_DEV_AUTH: "${PYSEPAL_DEV_AUTH:-0}"
      PYSEPAL_LOCAL_EE: "${PYSEPAL_LOCAL_EE:-0}"
      LOCAL_SEPAL_USER: "${LOCAL_SEPAL_USER}"
      LOCAL_SEPAL_PASSWORD: "${LOCAL_SEPAL_PASSWORD}"
    ports:
      - "8765:8765"
    healthcheck:
      test: ["CMD", "nc", "-z", "localhost", "8765"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: always
    networks:
      - sepal

networks:
  sepal:
    external: true
```

## 8. Multi-User Session Flow

```
Browser Tab Opens
    ↓
Solara creates new kernel
    ↓
@solara.lab.on_kernel_start → setup_sessions() → SessionManager initialized
    ↓
Page() renders → @with_sepal_sessions establishes the session
    ↓
SessionManager.create_session():
    - Extracts username from SepalHeaders
    - Creates EESession with user's credentials
    - Creates GEEInterface(gee_session)
    - Creates SepalClient.create(session_id=..., module_name=...)
    - Creates GDriveInterface(sepal_headers)
    - Stores all in the session registry, keyed by scope id
    ↓
Page() re-renders → get_current_gee_interface() returns user's GEEInterface
    ↓
Components use authenticated interfaces for GEE/SEPAL/Drive operations
    ↓
Tab closes → kernel cleanup → SessionManager.cleanup_session(scope_id)
```

Each browser tab = separate kernel = isolated session with its own credentials.

## 9. Local Development vs SEPAL Deployment

| Aspect               | Local Dev                                   | SEPAL Platform                                |
| -------------------- | ------------------------------------------- | --------------------------------------------- |
| Auth headers         | `prime_dev_auth()` via `PYSEPAL_DEV_AUTH=1` | Real HTTP headers from SEPAL proxy            |
| User files           | `SepalClient` against `SEPAL_HOST`          | `SepalClient` from session headers            |
| Container filesystem | Code and static assets only                 | Code and static assets only                   |
| GEE credentials      | `~/.config/earthengine/credentials`         | SEPAL-provided per user                       |
| URL                  | `http://localhost:8900`                     | `https://sepal.io/api/app-launcher/my_module` |
| Run command          | `./run_solara.sh`                           | `supervisord` in Docker                       |

### Handling user files

```python
sepal_client = get_current_sepal_client()
folder = sepal_client.files.mkdir(
    f"{sepal_client.results_path}/exports",
    parents=True,
)
sepal_client.files.write(f"{folder}/result.json", json_text, overwrite=True)
payload = sepal_client.files.read_json(f"{folder}/result.json")
```

## 10. Reference Apps

| App                   | Location                   | Key patterns                                                    |
| --------------------- | -------------------------- | --------------------------------------------------------------- |
| **sbae-design**       | `~/1_modules/sbae-design/` | AppState singleton, MapApp layout, use_thread, strategy pattern |
| **sepal_mgci**        | `~/1_modules/sepal_mgci/`  | traitlets Model, GEE async tasks, deferred calculations, Docker |
| **se.plan**           | `~/1_modules/se.plan/`     | Recipe model, GEE interface injection, multi-panel layout       |
| **pysepal demo apps** | `demo_apps/`               | Worked map-app example: AOI, notifications, legend, export      |
