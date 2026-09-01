# Migrating to pysepal 4.0

Everything listed here is **removed**, not deprecated: there is no shim, no
`DeprecationWarning`, and no fallback path. Work through the sections in order —
the first two change behaviour without changing any import you would grep for.

## 1. Where a session's credentials come from

This is the release's central change and it decides whether an app runs at all.

A session's credential source is now decided by **runtime topology** — what kind
of process pysepal is in — and never by probing credentials or testing whether a
request happens to carry headers. In order:

| Condition                                  | Source           | Meaning                                             |
| ------------------------------------------ | ---------------- | --------------------------------------------------- |
| `PYSEPAL_DEV_AUTH` armed, no SEPAL headers | `DEV_AUTH`       | one developer login for the whole process           |
| `SEPAL=true` (a SEPAL sandbox)             | `PROCESS`        | app-manager app; the machine credentials are yours  |
| `PYSEPAL_LOCAL_EE` armed, no SEPAL headers | `PROCESS`        | your own Earth Engine credentials, for local dev    |
| running under a Solara server              | `PER_CONNECTION` | app-launcher container; one identity per connection |
| anything else (Voila, Jupyter, a script)   | `PROCESS`        | machine credentials                                 |

A sandbox is now identified by the `SEPAL=true` environment variable that SEPAL
exports, not by a `sepal-user` home directory. If you build an app container from
`openforis/sandbox-base` you inherit that home but not that variable — which is
the point: such a container is multi-user and must resolve `PER_CONNECTION`, and
under the old check it did not. App containers were never meant to resolve
`PROCESS`. If a deployment genuinely must, export `SEPAL=true` in it explicitly.

**`PER_CONNECTION` never falls back.** Missing or invalid SEPAL headers there
raise `MissingSepalHeadersError` where 3.x silently built a session from the
machine's own Earth Engine credentials. That fallback had to go: SEPAL's
app-launcher mounts the _platform_ GEE service-account key at
`~/.config/earthengine/credentials` in every multi-user container, so a
headerless fallback served every user one shared identity.

The practical takeaway: in a multi-user container you must let the SEPAL proxy
supply the headers. There is no local-credential fallback any more. For the same
reason a `PROCESS` session refuses a service-account key file — machine
credentials are only trusted where topology has established they belong to one
user.

Real SEPAL headers always beat `PYSEPAL_DEV_AUTH`, so arming it in a deployed
container cannot displace a live user's identity.

### `GEEInterface` always goes through ee-client

`GEEInterface` used to carry two implementations of itself: 12 of its 30 methods
were written `if self.session: ... else: <global ee>`. The `else` half answered
from `~/.config/earthengine/credentials`, which in a container is the platform
service-account key — so an interface built with no session answered for the
platform while the session layer was busy refusing exactly that.

**Those 12 branches are gone.** Every call now goes through the session, and an
interface built without one resolves its own from the machine's credentials
rather than falling back to the global `ee`. One credential path, not one per
runtime.

Read that claim narrowly: it covers _pysepal's_ Earth Engine calls. Building a
graph still needs the global `ee` — `ee.Image(...)` raises
`EEException: client library not initialized` without `ee.Initialize()` — so
`su.init_ee()` stays, and a module that calls `ee.Image(x).getInfo()` itself
still bypasses all of this. The library can only guarantee its own calls.

pysepal reached the old fallback from seven places, each a quiet
`gee_interface or GEEInterface()` — or a `gee_session` allowed to be None. Two
of them were `get_viz_params` / `get_viz_params_async`, where `gee_interface`
is **now a required argument**: building one on a miss read the wrong identity
_and_ leaked an event-loop thread per call, because it was never closed. Five
remain, all covered by the constructor guard: `SepalMap`,
`solara.components.aoi.admin`, `AoiModel`, and the `sepalwidgets` asset inputs
(twice).

Four export parameters are **removed**, having only ever been forwarded on the
deleted branch: `pyramid_policy` on `export_image_to_asset`, and `dimensions`,
`skip_empty_tiles` and `format_options` on `export_image_to_drive`. None had a
caller in pysepal or in any downstream module.

**A task is now an ee-client model, not an `ee.batch.Task`.** `get_task` and
`get_task_async` return `Optional[eeclient.tasks.Task]` — a pydantic model — and
give you `None` for an unknown id. The deleted branch returned an `ee.batch.Task`
and _raised_ on a miss, so a caller that never passed a session has two things to
change: read the state as `task.metadata.state` rather than `task["state"]` or
`task.status()["state"]`, and test for `None` instead of catching. `is_running`
is genuinely a `bool` now; the deleted branch returned the task object itself,
despite the annotation always having said otherwise.

Worth doing carefully — pysepal shipped this exact bug against itself. Its own
`is_running_async` read `task["state"]` on a model, and no test caught it,
because every caller in the test suite took the deleted branch instead.

**`GEEInterface()` with no session now raises `SepalSessionError` in a
per-connection runtime.** The guard is in the constructor, so all five remaining
sites are covered at once — including `SepalMap(gee=True)`, the most visible of
them because `gee=True` is the default.

In a container app, build the interface once from the connection and pass it
down:

```python
gee_interface = get_current_gee_interface()

SepalMap(gee_interface=gee_interface)      # or SepalMap(gee=False)
AoiModel(gee_interface=gee_interface)
process_admin(..., gee_interface=gee_interface)
```

Nothing changes anywhere else. A notebook, a script, pytest or a SEPAL sandbox
owns its machine credentials, so resolving them there is correct and
`SepalMap()` keeps working untouched. Construction never reads the credential
store — that happens on the first Earth Engine call — so building a map on a
machine with no Earth Engine set up still works, and only using it fails.

`GEEInterface(use_sepal_headers=True)` is **removed** with it. It logged in from
`LOCAL_SEPAL_USER` / `LOCAL_SEPAL_PASSWORD` and returned a session, so it slipped
past the guard above — one process-wide developer identity, in any runtime. It
had no callers anywhere. `PYSEPAL_DEV_AUTH` is the supported way to run on a
developer login, and it goes through topology.

**`pysepal.scripts.gee` keeps only `init_ee` and `need_ee`.** Everything else in
that module is **removed**. It ran against the global `ee`, which in an
app-launcher container is the platform service account, so it answered for the
wrong identity and raised nothing to say so.

| removed                                                             | replacement                                                                                         |
| ------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `get_task`                                                          | `GEEInterface.get_task` — returns `None` on a miss, where this raised                               |
| `is_running`                                                        | `GEEInterface.is_running` — a real `bool`, where this returned the task                             |
| `is_task`                                                           | `interface.session.tasks.get_task_by_name_async(name)`                                              |
| `wait_for_completion`                                               | poll `GEEInterface.get_task(...).metadata.state` yourself                                           |
| `get_assets`, `_get_assets`                                         | `GEEInterface.get_assets` / `get_assets_async`                                                      |
| `get_ee_project`                                                    | `GEEInterface.get_folder()`, or `interface.session.project_id`                                      |
| `delete_assets`                                                     | none. It had no caller outside this repo's own test teardown, and it is the one that deleted.       |
| `is_asset`, `get_assets_async_concurrent`, `list_assets_concurrent` | `GEEInterface.get_asset(..., not_exists_ok=True)` and `get_assets_async()` — deprecated since 3.2.0 |

Two of them were already broken, so port rather than transcribe.
`wait_for_completion` left its loop on `COMPLETED` alone and waited forever on a
cancelled task. `delete_assets` gated on `if dry_run is True`, and `1 is True` is
`False` — every truthy value that was not the singleton armed a real recursive
delete.

`get_assets` also took the project root when called with no argument. Its
replacement does not: pass `interface.get_folder()` explicitly.

### Running a GEE-only app on your laptop

`PYSEPAL_DEV_AUTH` logs in to a real SEPAL instance, so it needs a host, an
account and a password. If your app only touches Earth Engine that is a lot of
setup for nothing. Arm `PYSEPAL_LOCAL_EE` instead and `solara run` uses the
credentials `earthengine authenticate` already wrote:

```bash
PYSEPAL_LOCAL_EE=1
```

You get a GEE interface built from `~/.config/earthengine/credentials` and **no
`SepalClient`** — there is no SEPAL identity, so exports fall back to the local
filesystem exactly as they do in a notebook. The file must hold a user OAuth
credential; a service-account key is refused.

This is the one switch that lets a `PROCESS` session resolve under a Solara
server, so it carries the same interlock as `PYSEPAL_DEV_AUTH`: real SEPAL
headers demote it, and it sits below the sandbox rule. Leaving it set in a
deployed container cannot displace a live user, and cannot serve the platform
service account either — `ee-client` refuses a service-account key at that path.

#### Which of the two switches

They are **mutually exclusive, and `PYSEPAL_DEV_AUTH` wins**: it is rule 1, this
is rule 3. Arming both leaves `PYSEPAL_LOCAL_EE` inert with no warning, so
disarm `PYSEPAL_DEV_AUTH` to switch.

|                     | `PYSEPAL_DEV_AUTH`                      | `PYSEPAL_LOCAL_EE`                      |
| ------------------- | --------------------------------------- | --------------------------------------- |
| Identity            | your SEPAL account, via a real login    | your `~/.config/earthengine` credential |
| Also needs          | `SEPAL_HOST`, user, password            | nothing                                 |
| Earth Engine        | yes                                     | yes                                     |
| `SepalClient`       | yes                                     | **no** — exports go to local disk       |
| Network at startup  | a blocking login POST                   | none                                    |
| Runtimes it changes | every runtime; it adds a SEPAL identity | `solara run` only                       |

That last row is the one people trip on. `PYSEPAL_LOCAL_EE` does nothing in
Voila, Jupyter or a script — those already resolve `PROCESS` and already read
the same credentials file. It exists for `solara run`, the one runtime that
otherwise refuses to start without SEPAL headers.

Use `PYSEPAL_DEV_AUTH` when you need the SEPAL side — file storage, exports to
your workspace, anything reading `get_current_sepal_client()`. Use
`PYSEPAL_LOCAL_EE` when the app only talks to Earth Engine.

## 2. Admin access is now `PYSEPAL_ADMIN_USERS`

`AdminButton` used to render for a hardcoded `["admin", "dguerrero"]`. It now
reads a comma-separated, case-insensitive environment variable, defaulting to
`admin`:

```bash
PYSEPAL_ADMIN_USERS=admin,dguerrero
```

**Any deployment that relied on the maintainer username loses the admin UI with
no error** — the button just stops rendering. This is the most likely silent
breakage in the release.

It remains a display gate, not an authorization boundary: it decides whether a
debug panel renders, and nothing downstream may key a permission off it.

## 3. Version floors

```text
ee-client>=3.1.0,<4
pysepal-api>=0.3.0,<0.4
solara>=1.60,<2
localtileserver>=1.0.0
ipyvuetify<3
```

Both floors are published. The provider-agnostic auth pysepal 4.0 needs from
`ee-client` -- the `EESession.from_*()` factories and `close()` on every
credential holder -- shipped as a minor, so that floor stays inside 3.x.

`pysepal-api` 0.3.0 is what moves the `createFolder` POST off the
session-creation path: `SepalClient.create()` no longer touches the network, and
`ensure_results_dir()` creates the directory instead. If your module wrote into
`results_path` and relied on `create()` to have made it, create it yourself --
no import breaks, so the failure appears at write time.

`ipyvuetify` is capped because 3.0 removes widgets that `sepalwidgets`
subclasses at import time — `CalendarDaily` among them — so an unpinned resolve
produced a pysepal that could not be imported at all. If your module pins
`ipyvuetify>=3`, that pin and pysepal 4.0 cannot be installed together; drop it.

`solara` is now pinned because two of its private APIs are load-bearing:
`solara.scope.get_kernel_id` (every per-connection scope id) and
`solara._using_solara_server` (rule 4 of the table above). pysepal asserts both
at import and raises `ImportError` if either is missing, rather than silently
collapsing every connection onto one shared scope. Do not unpin solara.

`localtileserver` 1.0 is the first version pysepal has required, so 3.8.1 apps
meet it here. It brings a `jupyter-loopback` dependency and, with it, prefix
autodetection: with no prefix configured it invents `localtileserver-proxy/{port}`
on the grounds that it is running in a Jupyter kernel. 0.10.x handed the browser
the loopback URL instead. On SEPAL nothing changes -- the platform sets
`LOCALTILESERVER_CLIENT_PREFIX`, so autodetection never fires. Where nothing
serves that route -- a plain `voila notebook.ipynb` -- every tile 404s, with no
error and no traceback, just an empty map. Define `LOCALTILESERVER_CLIENT_PREFIX`
**empty** to get the old URL back. See `local-tile-servers.md` for the rest.

## 4. `import sepal_ui` → `import pysepal`

The `sepal_ui` compatibility package is **deleted**. `import sepal_ui` raises
`ModuleNotFoundError`.

```python
# 3.x
from sepal_ui import sepalwidgets as sw
from sepal_ui.aoi import AoiModel

# 4.0
from pysepal import sepalwidgets as sw
from pysepal.aoi import AoiModel
```

**What to do**: `grep -rn "sepal_ui" your_app/` and rename every hit, including
`sepal-ui` in requirements files (the distribution is `pysepal`). Review before
running a blind `sed` — the string also appears in unrelated places such as
crowdin project names.

## 5. `SepalClient` comes from `pysepal_api`

`pysepal.scripts.sepal_client` is deleted with its four legacy file verbs.

```python
# 3.x
from pysepal.scripts.sepal_client import SepalClient

client.get_remote_dir(folder, parents=True)
client.set_file(path, content, overwrite=True)
client.list_files(folder, extensions=[".tif"])
client.get_file(path, parse_json=True)

# 4.0
from pysepal_api import SepalClient

client.files.mkdir(str(folder), parents=True)
client.files.write(path, content, overwrite=True)
client.files.list(folder, extensions=[".tif"])
client.files.read_json(path)  # read_bytes(path) when parse_json was False
```

`set_file` and `list_files` returned `.model_dump()` dicts; the `files.*`
methods return pydantic models — call `.model_dump()` yourself where you relied
on the dict.

`get_current_sepal_client()` already returned this client, so callers that only
use the `.files.*` API need no change.

## 6. `~/.sepal-ui-config` and its CLI tools are gone

The file is deleted along with every reader and writer. Theme and locale are
per-runtime state now, resolved and persisted in the browser, because a
machine-global file is shared by every connection in a multi-user container.

Removed: `pysepal.conf`, `pysepal.config`, `pysepal.config_file`,
`pysepal.frontend.styles.get_theme`, and `set_config`, `set_config_locale`,
`set_config_theme`, `_write_config` from `pysepal.scripts.utils`.

**Theme**: pysepal no longer reads the config file at import, and toggling writes
nothing to disk. `ThemeState` is in-memory state keyed by the runtime scope,
starting at `mode="auto"`:

```python
from pysepal.solara import get_current_theme_state

theme_state = get_current_theme_state()
```

That is about the config file, not about persistence: `solara.lab.ThemeToggle`
still keeps the user's choice in browser `localStorage` (`:solara:theme.variant`),
so it survives a reload, per browser. The config file was process-global, which is
why in a multi-user container one user's theme became everyone's.

**Locale**: `Translator` no longer consults the config file. With no `target` it
now resolves to English, deterministically:

```python
# 3.x — target came from ~/.sepal-ui-config
ms = Translator(json_folder)

# 4.0 — pass the target you want
ms = Translator(json_folder, target=user_locale)
```

Where the locale comes from at all is the other half. `LocaleSelect` resolves
it in the browser — `localStorage[":sepalUi:locale"]`, then
`navigator.language`, then English, each candidate matched against the
catalogs the app actually ships — and writes it into the runtime scope's
locale, which `pysepal.i18n` reads and writes through `current_locale()` and
`set_locale()`:

```python
from pysepal.i18n import current_locale, set_locale

current_locale()  # "en" until something sets one
set_locale("fr")  # any IETF BCP 47 code, in any casing
```

`set_locale` cannot seed a startup default: a `LocaleSelect`'s first mount in a
browser tab always overwrites it with the browser's own resolution, so only a
call made after that first mount — from a settings dialog, say — sticks.

**The locale state that came before `current_locale()` / `set_locale()` is gone too:**

| removed                                                    | replacement                                    |
| ---------------------------------------------------------- | ---------------------------------------------- |
| `use_locale()`                                             | `pysepal.i18n.current_locale()`                |
| `LocaleState`                                              | nothing — the locale is scope state            |
| `get_current_locale_state()`                               | `current_locale()` / `set_locale()`            |
| `resolve_locale_state()`                                   | `current_locale()` / `set_locale()`            |
| `locale_state=` on `MapApp` / `LocaleSelect`               | nothing — the selector writes the scope locale |
| `LocaleSelect.bind_locale_state()` / `.get_locale_state()` | nothing                                        |

Building your own app's message catalog looks different from the `Translator`
call above, though: bind it once, at import, with no target at all — this is
what both demo apps do:

```python
# component/message/__init__.py
from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent)
msg = messages.msg
```

Then call `msg("app.title")` anywhere — a component, a helper on the same call
stack, an event handler, a worker thread — with no per-render rebuild to write,
because there is nothing to rebuild: `msg` reads `current_locale()` itself on
every call, subscribing to it when a render is in progress and doing a plain
read otherwise, so a language change re-renders in place with no reload:

```python
@solara.component
def Page():
    MapApp.element(app_title=msg("app.title"), locales=messages.available_locales())
```

`count` is not always a plural selector: it only becomes one when `key` names a
plural node in English, and is an ordinary placeholder on any other key — the
raster demo's `msg("toasts.classes", count=len(classes))` just fills in a number.

`MapApp` takes locale _codes_ rather than a `Translator` because `Translator`
subclasses `dict`, which reacton flattens on the way to `.element()`.

A 3.x locale saved in `~/.sepal-ui-config` is not migrated: the file is read
nowhere in 4.0, so the first load falls to `navigator.language`.

The picker now offers every catalog the app ships. Previously the offered list
was intersected with `pysepal/data/locale.parquet`, which has `es-ES` but no
bare `es` — so pysepal's own bundled `message/es/` and `message/ru-RU/` could
never be selected. The parquet now supplies only display names and flags.

**CLI**: the `module_theme` and `module_l10n` entry points are removed — both
existed only to edit that file. The remaining console scripts are
`module_deploy`, `module_factory`, `module_venv`, `activate_venv`,
`sepal_ipyvuetify` and `entry_point`.

## 7. `SOLARA_TEST` → `PYSEPAL_DEV_AUTH`

`SOLARA_TEST` cached one login process-wide, so a multi-user container armed
with it handed every connected user the same session. `PYSEPAL_DEV_AUTH` is a
boolean arming flag (`1`, `true`, `yes`, `on`) that real SEPAL headers always
demote, so it stays safe even if it is left set in a deployed container.

It is a **development** switch: it exists so you can run an app against a real
SEPAL instance from a laptop, where no SEPAL proxy injects headers. It is a
single process-wide identity by design and must not be used to serve users.

```bash
# 3.x
SOLARA_TEST=1

# 4.0
PYSEPAL_DEV_AUTH=1
SEPAL_HOST=yourinstance.sepal.io
LOCAL_SEPAL_USER=...
LOCAL_SEPAL_PASSWORD=...
```

The login is a blocking HTTP POST. Call `prime_dev_auth()` from application
startup to keep it off the render path; the session layer otherwise calls it
lazily on the first render.

**What to do**: update `.env` files, `docker-compose.yml` and any deployment
manifest. `session_manager.reset_dev_headers_cache()` is gone with it.

## 8. Renamed and retyped session API

Everything an app should import now lives at `pysepal.solara`; the submodules
are internal.

| 3.x                                                         | 4.0                                                  |
| ----------------------------------------------------------- | ---------------------------------------------------- |
| `SessionManager().list_sessions()`                          | `session_scope_ids()` or `sessions_overview()`       |
| `SessionManager().get_session_component("gee_interface")`   | `SessionManager().get_gee_interface()`               |
| `SessionManager().get_session_component("drive_interface")` | `SessionManager().get_drive_interface()`             |
| `SessionManager().get_session_component("sepal_client")`    | `SessionManager().get_sepal_client()`                |
| `SessionManager().get_kernel_id()`                          | `SessionManager().get_scope_id()`                    |
| `cleanup_session(kernel_id=...)`                            | `cleanup_session(scope_id=...)`                      |
| `get_session_info(kernel_id=...)`                           | `get_session_info(scope_id=...)`                     |
| `runtime_context.get_current_runtime_id()`                  | `resolve_scope_id()` (raises) / `current_scope_id()` |
| `session_manager.MissingSepalHeadersError`                  | `pysepal.solara.MissingSepalHeadersError`            |
| `session_manager.empty_session_info(scope)`                 | `SessionInfo(scope_id=scope)`                        |
| `session_manager.can_create_sessions()`                     | removed, no replacement                              |

`list_sessions()` handed out the live session payloads, credentials included.
The typed replacements never do:

```python
# 3.x
for scope, session in SessionManager().list_sessions().items():
    print(scope, session["username"])

# 4.0
from pysepal.solara import get_sessions_overview

overview = get_sessions_overview()
for info in overview.sessions:
    print(info.scope_id, info.username)
print(overview.total_sessions, overview.ready_sessions)
```

`kernel_id` and `runtime_id` were the same value under two names; both are now
`scope_id`. `PROCESS_SCOPE` is the reserved id used when no per-connection
runtime resolves.

## 9. `get_session_info()` returns a frozen `SessionInfo`

It is a frozen dataclass, not a dict — attribute access, no mutation.

```python
# 3.x
info = get_current_session_info()
if info["session_ready"]:
    print(info["username"], info["module_names"])

# 4.0
info = get_current_session_info()
if info.session_ready:
    print(info.username, info.module_names)  # module_names is a tuple
```

Two more differences:

- `scope_id` is always populated. Where 3.x reported `None` for an unresolvable
  runtime, 4.0 reports `PROCESS_SCOPE` — **without reading that session**. A
  caller-supplied `scope_id=PROCESS_SCOPE` is refused the same way and returns
  an empty `SessionInfo`, so it cannot be used as a second door into the shared
  process or dev-auth identity. Use `sessions_overview()` to see the process
  session.
- `has_theme_state` is gone: it mixed a UI-scope fact into an authentication
  payload. Ask the UI-state registry instead.

```python
# 3.x
if info["has_theme_state"]: ...

# 4.0
from pysepal.solara import current_scope_id, has_scoped_state

if has_scoped_state("theme_state", current_scope_id()): ...
```

`get_sessions_overview()` likewise returns a `SessionsOverview` with a
`.sessions` tuple and the `.total_sessions` / `.ready_sessions` properties,
replacing the dict of the same three keys.

## 10. `with_sepal_sessions` and the removed fallbacks

The decorator no longer probes `solara.lab.headers` before creating a session —
section 1 decides the credential source. `show_loading` and `waiting_message`
are removed, and they were the first two positional parameters, so
`module_name` is now first:

```python
# 3.x — an indefinite spinner while headers were absent
@with_sepal_sessions(show_loading=True, module_name="my.module")
def Page(): ...

# 4.0
@solara.component
@with_sepal_sessions(module_name="my.module")
def Page(): ...
```

A missing or invalid header set now surfaces through the decorator's normal
error boundary as a `SepalSessionError`, instead of an indefinite
"Waiting for authentication headers..." message.

`get_current_gee_interface()` and `get_current_drive_interface()` lost their
process-global `EESession.from_default()` fallbacks. A per-connection runtime
with no session now raises `SepalSessionError` naming `@with_sepal_sessions`,
where 3.x quietly returned an interface built from the machine's credentials —
in an app-launcher container, the shared platform service account. A component
that forgot the decorator fails loudly instead of serving the wrong identity.

## 11. `MapApp`'s right panel follows its traits

`right_panel_config` and `right_panel_content` are now reactive. Setting either
one after construction updates what is on screen; in 3.x the assignment landed
on the trait and nothing visible changed.

`MapApp` does not render the panel itself. It copies both values into a child
`RightPanel` widget in `__init__`, and `MapApp.vue` renders that child. The copy
ran once, so the two drifted apart the moment anything reassigned the parent
trait — which is what `MapApp.element(...)` does on every re-render, because
reacton updates an existing widget rather than rebuilding it. `MapApp` now
observes both traits and pushes them onto the child.

This is what makes a panel that depends on state work at all:

```python
# 4.0 — the heading and description follow the reactive value
MapApp.element(
    right_panel_config={"title": ms.panel.title, "width": 400},
    right_panel_content=[{"title": f"{len(layers)} layers", "content": [...]}],
)
```

Nothing needs changing to adopt it. It matters if you worked around the old
behaviour by rebuilding the whole `MapApp`, or by mutating the child panel
through `app.right_panel[0]`. Both are now unnecessary, and the second is
silently overwritten the next time the parent trait changes.

**Catalog keys may not be named after `dict` methods.** `Translator` subclasses
`Box` subclasses `dict`, so a key called `clear`, `items`, `keys`, `values`,
`get`, `copy`, `update` or `pop` returns the bound method instead of your
string, and reaches the UI as `<bound method Box.clear ...>` with no error.
Rename the key. For the same reason `MapApp` takes `locales=` rather than a
`Translator`: reacton flattens a `dict` subclass on the way to `.element()`.

## Audit checklist

- [ ] Set `PYSEPAL_ADMIN_USERS` in every deployment that had a non-`admin`
      admin user.
- [ ] Confirm no multi-user deployment depends on a headerless fallback.
- [ ] Confirm any deployment that must resolve `PROCESS` exports `SEPAL=true`; a
      `sepal-user` home no longer selects it.
- [ ] Raise the `ee-client`, `pysepal-api` and `solara` floors; leave solara
      pinned.
- [ ] `grep -rn "sepal_ui"` and rename to `pysepal`, requirements included.
- [ ] Replace `pysepal.scripts.sepal_client` imports with `pysepal_api` and the
      four legacy verbs with `client.files.*`.
- [ ] Create the results directory yourself before writing into `results_path`;
      `SepalClient.create()` no longer does it, and nothing fails until the write.
- [ ] Remove every `~/.sepal-ui-config` reader/writer; bind your app's message
      directory with `catalog()`, look up strings with `msg()`, and read/write
      the runtime locale with `current_locale()` / `set_locale()`; use
      `get_current_theme_state()` for theme.
- [ ] Replace `use_locale()`, `LocaleState`, `get_current_locale_state()` and
      `resolve_locale_state()` with `current_locale()` / `set_locale()`; drop
      `locale_state=` from `MapApp` / `LocaleSelect` and any
      `bind_locale_state()` / `get_locale_state()` call.
- [ ] Replace any "refresh to apply the language" instruction in your UI;
      switching is live, and picks no longer survive as a machine-global file.
- [ ] Drop `module_theme` / `module_l10n` from scripts and CI.
- [ ] Rename `SOLARA_TEST` to `PYSEPAL_DEV_AUTH` in `.env`, compose files and
      deployment manifests — or `PYSEPAL_LOCAL_EE=1` if the app only needs Earth
      Engine locally.
- [ ] Replace `list_sessions()`, `get_session_component()`, `get_kernel_id()`
      and `get_current_runtime_id()` with their typed equivalents.
- [ ] Convert `get_session_info()` / `get_sessions_overview()` subscripting to
      attribute access.
- [ ] Drop `show_loading` / `waiting_message` from `with_sepal_sessions` calls.
- [ ] Pass `gee_interface=get_current_gee_interface()` to every `SepalMap`,
      `AoiModel`, asset input and `process_admin` in a container app — or
      `gee=False` where Earth Engine isn't needed. A session-less
      `GEEInterface()` now raises there.
- [ ] Pass `gee_interface` to `get_viz_params` / `get_viz_params_async`; it is
      no longer optional.
- [ ] Drop `pyramid_policy`, `dimensions`, `skip_empty_tiles` and
      `format_options` from any `export_image_to_asset` / `export_image_to_drive`
      call.
- [ ] Read a task's state as `task.metadata.state`, and handle `get_task`
      returning `None` instead of raising on an unknown id.
- [ ] Replace every `pysepal.scripts.gee` call except `init_ee` and `need_ee`.
      The table above names the replacement for each.
- [ ] Drop any workaround that rebuilt `MapApp`, or reached into
      `app.right_panel[0]`, to refresh the right panel; both traits are reactive.
- [ ] Grep your message catalogs for keys named after `dict` methods
      (`clear`, `items`, `keys`, `values`, `get`, `copy`, `update`, `pop`).

For the full picture of how an app is wired in 4.0, see
`docs/guides/solara-app-builder.md`.
