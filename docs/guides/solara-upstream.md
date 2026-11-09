# Upstream Solara changes

A running log of what each upstream Solara release means for pysepal: what we
adopted, what we only documented, what we deliberately skipped, and what stays
blocked. Add an entry whenever the pin moves or a release touches something we
rely on.

The pin lives in `pyproject.toml`. Three private APIs are
load-bearing — `solara.scope.get_kernel_id`, `solara._using_solara_server` and
`solara.toestand.KernelStoreFactory` — so upstream releases get read rather than
trusted, and the major is capped.

Upstream changelog: `solara/website/pages/changelog/changelog.md` in the Solara
repository.

---

## 1.66.0 – 1.66.2 (reviewed 2026-11-09)

1.66.1 was tagged but never published. 1.66.2 contains its fix.

The diff from v1.65.2 to v1.66.2 is small. In `solara/server/` it touches only
`app.py`, `kernel_context.py`, `patch.py` and `sync_ws_write.py`. The close
route, the close beacon in `main-vuetify.js`, the reconnect and cull code,
`settings.py`, the assets proxy and the frontend files are unchanged. The
dependencies of `solara-ui` and `solara-server` are unchanged too.

### Adopted — kernel cull timeout `"5m"` instead of `"0s"`

`setup_solara_server()` set `kernel.cull_timeout = "0s"`. It now sets `"5m"`
(`DEFAULT_CULL_TIMEOUT` in `pysepal/solara/setup.py`). The `"0s"` value assumed
that the cull frees a closed tab. It does not. With `"0s"`, every dropped
connection shut the kernel down at the disconnect, so the page could not
reconnect to it.

We tested a hot patch on a dev SEPAL on 2026-11-09:

- **Close the app tab inside SEPAL.** The websocket disconnect arrives first.
  The close beacon of the page (`/_solara/api/close`, which calls `page_close`)
  arrives a few milliseconds later, through the SEPAL proxy. `page_close`
  closes the kernel at once when no other page uses it. The cull timeout does
  not free a closed tab. We saw this with `"0s"` and again with `"5m"`: the
  disconnect scheduled a 300-second cull, and the beacon shut the kernel down
  in the same second.
- **Restart the Caddy proxy.** This drops all websockets. With `"5m"`, se.plan
  (Solara 1.61.0) and sepal_mgci 2.2.0 (Solara 1.66.2) reconnected 4 to 19
  seconds later and reused their kernel. The logs show "reusing virtual kernel"
  and "Cancelling previous kernel cull task". With `"0s"`, the kernel would
  have shut down at the disconnect. sepal_mgci kept its UI state. se.plan kept
  its kernel but lost UI layers. That is an issue in the app or in its old
  Solara release (sepal-contrib/se.plan#278), not in pysepal.

Why 5 minutes: the reconnects took less than 20 seconds, so 5 minutes leaves a
large margin, for example for a longer proxy restart or a short network loss.
The cost is a kernel whose page goes away without a close beacon, for example
after a browser crash. That kernel keeps its memory and its session for 5
minutes at most. Solara's own default is `"24h"`. Its default for
`state.orphan_cull_timeout` is also `"5m"`.

With `"5m"`, every dropped connection now goes through the reconnect path. The
reconnect fixes of 1.63.0 to 1.64.1 therefore matter more than before; see the
floor below.

### Documented — less garbage under load (1.66.2)

- `get_ipython()` reuses one `FakeIPython` per kernel context, and its `events`
  is no longer a `MagicMock` ([#1279]). Every widget message calls
  `get_ipython()`, so a server with many sessions makes far less garbage. Side
  effect: `get_ipython().user_ns` stays the same within a session. pysepal does
  not call `get_ipython()`. On the Solara server,
  `solara.scope.get_kernel_id(ipython_fallback=True)` reads the kernel context
  and does not reach the IPython fallback.
- `Singleton`, `Computed` and threaded tasks hold `self` through a weak
  reference in their closures, so reference counting frees them ([#1280]).
  pysepal uses neither `Singleton` nor `Computed`. Its `use_task` hooks keep
  their task while the component is mounted, and pysepal calls `cancel()` only
  on a live task, so the weak reference changes nothing for it.
- A context-aware thread no longer enters its kernel context in the bootstrap
  ([#1280]). That step ran before `threading` registered the thread, so it only
  left a stale `Dummy-N` entry in `current_context`.
  `set_context_for_thread()` still maps the thread to its kernel. A pysepal
  thread that starts inside a kernel therefore still sees that kernel, for
  example the GEE event loop thread (`pysepal/scripts/gee_interface.py`) or the
  `ThreadController` thread (`pysepal/scripts/thread_controller.py`).

[#1279]: https://github.com/widgetti/solara/pull/1279
[#1280]: https://github.com/widgetti/solara/pull/1280

### Documented — private APIs

The diff from v1.65.2 to v1.66.2 does not change any of the three:
`solara/scope/` is unchanged, `solara._using_solara_server` has the same body,
and `KernelStoreFactory` has the same constructor. The changes in
`kernel_context.py` only add and clear `VirtualKernelContext._fake_ipython`.
`solara.lab.utils.headers`, `solara.server.settings` (`kernel.cull_timeout`,
`assets.extra_locations`, `assets.fontawesome_path`) and `solara.util` are
unchanged.

### Documented — `solara.lab.app_mounted` (1.66.0)

`solara.lab.app_mounted` is a reactive per kernel. It turns True when the
server has told the browser that the first render is done ([#1275]). Solara
keeps its "Loading app" screen until that first render ends, including every
pass that state set in an effect causes. A component can render a skeleton
while the value is False and start its `use_task` when it is True. A reconnect
keeps the kernel, and the value stays True.

pysepal does not read it, so it adds no render. A possible use is in a
component that loads GEE data on its first render, such as `AoiView`, so that
the user sees the app before the data is there. In a test with `solara.render`
nothing sets the value; the test must set it.

[#1275]: https://github.com/widgetti/solara/pull/1275

### Skipped — changes pysepal does not use

- **1.66.0** — `SOLARA_SERVER_SYNC_WS_WRITE` no longer lets a slow client stall
  the server, and a write after a disconnect can no longer reach another socket
  ([#1262]). SEPAL deployments leave the setting off. If you measure it (see
  1.60.0 below), use 1.66.0 or later.
- **1.66.0** — solara.dev publishes an intersphinx inventory ([#1274]). The
  pysepal Sphinx configuration (`docs/source/conf.py`) has no intersphinx
  mapping today. Add one for Solara if the API docs start to link to it.

[#1262]: https://github.com/widgetti/solara/pull/1262
[#1274]: https://github.com/widgetti/solara/pull/1274

### Floor — keep the proposed `solara>=1.64.1`

1.66.x does not change the proposal of the 1.62.1 – 1.65.2 entry:

- 1.65.1 to 1.66.2 add no fix that pysepal needs to work correctly. They fix
  edge cases ([#1247], [#1258], [#1260], [#1261], [#1264]), log noise and the
  load on the garbage collector ([#1279], [#1280]).
- 1.64.1 is still the lowest release with all the reconnect and close fixes.
  The `"5m"` cull makes them more important. With `"0s"`, a dropped connection
  ended the kernel, so no reconnect happened. With `"5m"`, every dropped
  connection reconnects to its kernel. Below 1.63.0, the late disconnect of
  [#1210] still closes the kernel under an open page, only 5 minutes later.
- A fresh install gets the newest release, 1.66.2 today, and a dev SEPAL ran
  1.66.2 with the `"5m"` cull. The floor only limits how old an app can stay.

Move the floor to `1.65.1` when one of these becomes true:

- An app needs `solara[assets]` (`solara-assets2` requires a solara newer than
  1.64.1).
- SEPAL logs show a reconnect loop after a lost session cookie ([#1264]), or a
  `KeyError` from a close beacon for an unknown page ([#1247]). With the `"5m"`
  cull, the close beacon is the fast path that frees a closed tab, so check the
  logs for this error first.

[#1247]: https://github.com/widgetti/solara/pull/1247

### Ceiling — keep `<2`, add no minor cap

- Upstream released ten versions between 1.62.0 (2026-09-17) and 1.66.2
  (2026-11-07). Fixes that pysepal needs come in minor releases; the 1.63.0
  revert is an example. A cap on the minor blocks those fixes, and each new
  minor would then need a pysepal release.
- If upstream removes one of the three private APIs, pysepal fails at import
  with a clear `ImportError` (`pysepal/_runtime_context.py`,
  `pysepal/solara/_topology.py`, `pysepal/solara/theme.py`).
- The known break, Vuetify 3, is already blocked by `ipyvuetify>=1.8,<3`.
- A minor cap only delays a behaviour change such as [#1192]. This review is
  what finds it. If a release breaks pysepal, exclude it with `!=X.Y.Z` in a
  pysepal patch release. An app that needs a fixed environment pins exact
  versions in its own requirements, not through pysepal.

---

## 1.62.1 – 1.65.2 (reviewed 2026-11-06)

1.65.0 was never published: its build failed, and 1.65.1 contains its changes.

### Adopted — the 1.63.0 to 1.64.1 reconnect and lifecycle fixes

These are the reason to move the floor from `1.60.3` to `1.64.1`. This entry
does not change `pyproject.toml`; the pin moves in its own change.

- **1.63.0** — the [#1192] change from 1.60.3 is reverted ([#1211]). Upstream
  measured hangs from its three new locks, and its production runs the 1.60.2
  code. 1.60.3 to 1.62.1 therefore carry code that upstream itself removed. The
  other 1.60.x fixes stay: [#1186] and [#1188] live in `solara/tasks.py`, which
  the diff from v1.62.0 to v1.65.2 does not touch, and the [#1189] purge and the
  [#1191] filter are still in v1.65.2. See "Documented — what the revert
  changes" below.
- **1.63.0** — a reused kernel moves to the event loop of its new connection
  ([#1208]). In threaded mode, the default, each websocket has its own loop.
  Before 1.63.0, a reconnect kept the old, closed loop, and work scheduled onto
  the kernel was lost, task results included. Every pysepal `use_task` hook
  depends on this.
- **1.63.0** — a page stays connected while any of its websockets is open
  ([#1210]). When a proxy drops only the browser side, the browser reconnects
  at once, and the server sees the old websocket close 20 to 40 seconds later.
  Before 1.63.0, that late disconnect marked the page disconnected and started a
  kernel cull. With the old `kernel.cull_timeout = "0s"` of
  `setup_solara_server()`, that cull closed the kernel under the open page at
  once. With the new `"5m"`, it closes it 5 minutes later, so the fix is still
  needed. On a dev SEPAL (2026-11-09), a Caddy restart dropped all websockets,
  and the apps reconnected 4 to 19 seconds later and reused their kernel. That
  test drops both sides at once, so it does not reproduce the late disconnect
  of this PR; that part of the reasoning still comes from the PR. See "Adopted
  — kernel cull timeout" in the 1.66.0 – 1.66.2 entry.
- **1.63.0** — the assets proxy never serves a half-written cdn cache file
  ([#1214]). On a fresh server, several first visitors could get a truncated
  `require.js`, and the page stayed on "Loading resources". A SEPAL app
  container starts with an empty cache.
- **1.63.1** — a reconnect cancels a pending kernel cull at once and from any
  thread, also when the cull has not started yet ([#1220]).
- **1.64.0** — browsers with more than 8 kB of cookies connect again with
  uvicorn 0.54 ([#1231]). pysepal does not pin uvicorn, and 0.54.0 is the newest
  release on PyPI. Below 1.64.0, such a user gets the page but no app.
- **1.64.1** — the kernel closes on `pagehide` instead of `beforeunload`, so a
  download or `mailto:` link no longer kills the app ([#1253]). A page that the
  Back button restores from the browser cache reloads instead of showing a dead
  kernel ([#1255]). Both keep the behaviour that the cull timeout relies on:
  the page closes its kernel when it goes away. That is what frees a closed
  tab, not the cull (see the 1.66.0 – 1.66.2 entry).

Why `1.64.1` and not `1.65.2`: 1.64.1 is the newest release that a maintainer
environment runs (with reacton 1.11.1). 1.65.x adds no fix that pysepal needs;
take it when an environment has run it. The 1.66.0 – 1.66.2 review keeps this
floor. If `1.64.1` is too high for an app,
`1.63.1` is the lowest release with the revert and all the reconnect fixes.

[#1208]: https://github.com/widgetti/solara/pull/1208
[#1210]: https://github.com/widgetti/solara/pull/1210
[#1211]: https://github.com/widgetti/solara/pull/1211
[#1214]: https://github.com/widgetti/solara/pull/1214
[#1220]: https://github.com/widgetti/solara/pull/1220
[#1231]: https://github.com/widgetti/solara/pull/1231
[#1253]: https://github.com/widgetti/solara/pull/1253
[#1255]: https://github.com/widgetti/solara/pull/1255

### Documented — what the revert changes

From 1.63.0 the kernel lifecycle is the 1.60.2 code again. Three points touch
pysepal:

- A close callback that raises stops `VirtualKernelContext.close()`: the next
  callbacks, the render context and the widgets do not close. 1.60.3 to 1.62.1
  caught and logged each failure. The `setup_sessions()` cleanup
  (`pysepal/solara/session_manager.py`) must therefore never raise.
  `cleanup_session` catches `Exception` around each interface close today; keep
  it that way.
- `Reactive.subscribe()` and `fire()` no longer hold a listener lock. The bus
  serializes its own publishers (`NotificationBus._publish` in
  `pysepal/solara/notifications/bus.py`). The subscribe in
  `NotificationUIBridge` (`notification_ui.py`) runs in an effect and can
  overlap a publish from a worker thread. That is the 1.60.2 behaviour, which
  upstream runs in production. We think the risk is low, but we did not measure
  it.
- A hot reload still runs the close callbacks and then `on_kernel_start` again
  for the same kernel id. `SessionManager._reopen_scope` still matches that
  order.

### Documented — private APIs

The diff from v1.62.0 to v1.65.2 does not change any of the three:

- `solara.scope.get_kernel_id` — `solara/scope/` is unchanged. The function
  calls `kernel_context.get_current_context()`, which is also unchanged.
- `solara._using_solara_server` — same body.
- `solara.toestand.KernelStoreFactory` (`pysepal/solara/theme.py`) — same
  constructor signature.

`solara.lab.utils.headers` (`session_manager.py`) is also unchanged.

### Documented — reacton 1.11

Solara still requires `reacton>=1.9`, but a fresh install gets reacton 1.11.x.
CI tests it from 1.63.0 ([#1213]). In reacton 1.11, a state change from another
thread never waits for the render lock, and a concurrent-writer deadlock goes
away (widgetti/reacton#74). pysepal writes reactive state from GEE threads, so
this can change how such a write re-renders. We did not measure the effect on
pysepal.

[#1213]: https://github.com/widgetti/solara/pull/1213

### Documented — server and development behaviour

- **1.63.0** — content-hashed static files get
  `Cache-Control: public, max-age=31536000, immutable` ([#1212]). A wrong hash
  gets `no-store`. A proxy in front of the server must include the query string
  in its cache key.
- **1.64.0** — `solara.server.reload.watch_file(path, on_change=None)` is a
  public hook for development-mode hot reload of non-Python files ([#1232]). A
  `.vue` file reached through a symlink now hot reloads too, which helps an
  editable pysepal install. pysepal does not use the hook. A possible use is to
  merge the pysepal CSS and JS assets again when a source file changes.
- **1.64.0** — `SOLARA_SERVER_SYNC_WS_WRITE` (see 1.60.0 below) needs the
  legacy websockets implementation. Under uvicorn 0.54 it falls back and logs a
  warning ([#1231]).
- **1.64.1** — the starlette server compresses each static file once and caches
  the result ([#1243]). `solara[brotli]` adds Brotli; gzip stays the default.
- **1.64.1** — hook validation flags hooks inside comprehensions and generator
  expressions as `SH103` ([#1257]). No pysepal component has one today.
- **1.65.1** — a reconnect with a lost session cookie stops with close code
  `4001` and offers a reload, instead of a reconnect loop ([#1264]). Widget
  messages after `pagehide` are dropped, not raised ([#1258]). A stopped
  websocket portal counts as a closed websocket ([#1260]). A binary send from
  the event loop no longer drops the websocket ([#1261]). These are fixes for
  edge cases and log noise; pysepal gets them with the next floor move after
  1.64.1.

[#1212]: https://github.com/widgetti/solara/pull/1212
[#1232]: https://github.com/widgetti/solara/pull/1232
[#1243]: https://github.com/widgetti/solara/pull/1243
[#1257]: https://github.com/widgetti/solara/pull/1257
[#1258]: https://github.com/widgetti/solara/pull/1258
[#1260]: https://github.com/widgetti/solara/pull/1260
[#1261]: https://github.com/widgetti/solara/pull/1261
[#1264]: https://github.com/widgetti/solara/pull/1264

### Skipped — changes pysepal does not use

- **1.63.0** — injectable Redis client for state persistence ([#1209]).
  pysepal does not configure Solara state persistence.
- **1.63.1** — the ES module deadlock with ipyreact ([#1227]). pysepal does not
  use ipyreact or `define_module`. An app that adds ipyreact needs 1.63.1; the
  proposed floor covers it.
- **1.64.1** — `define_module(dependencies=...)` on the Solara server
  ([#1244]): same reason.
- **1.62.1, 1.64.1, 1.65.2** — Vuetify 3 fixes for the file browser, `AppLayout`
  and `GridDraggable` ([#1203], [#1239], [#1270]). pysepal runs on Vuetify 2;
  see Blocked below.
- **1.65.1** — Shift-click range selection in the file browser ([#1205]). The
  admin panel uses `solara.FileBrowser()` (`pysepal/solara/components/admin.py`)
  and gets it for free.

[#1203]: https://github.com/widgetti/solara/pull/1203
[#1205]: https://github.com/widgetti/solara/pull/1205
[#1209]: https://github.com/widgetti/solara/pull/1209
[#1227]: https://github.com/widgetti/solara/pull/1227
[#1239]: https://github.com/widgetti/solara/pull/1239
[#1244]: https://github.com/widgetti/solara/pull/1244
[#1270]: https://github.com/widgetti/solara/pull/1270

### Blocked — ipyvuetify 3 is now the default install

The 1.61 entry below says that ipyvuetify 3 is a prerelease. That is no longer
true: ipyvuetify 3.0.0 reached PyPI on 2026-08-12, and 3.1.0 is the newest
release. A fresh `pip install solara` now installs ipyvue 3.1.1 and ipyvuetify
3.1.0 ([#1270]). Upstream decided not to cap them (widgetti/solara#1268).

pysepal still pins `ipyvuetify>=1.8,<3`. ipyvuetify 1.12.0, the newest 1.x,
requires `ipyvue>=1.7,<2`, so a pysepal environment stays on Vue 2. That cap is
now the only thing that keeps pysepal off Vuetify 3. Do not drop it before the
migration.

### Ceiling lifted — `solara-assets2` (1.65.1)

`solara[assets]` installs again from 1.65.1 ([#1269]). The assets moved to a new
package, `solara-assets2`, because `solara-assets` hit the PyPI storage limit.
`solara-assets2` has its own version (1.1.0 today) and requires a solara newer
than 1.64.1. It installs into `share/solara-assets2/cdn`, not
`share/solara/cdn`. A deployment that serves that directory directly, for
example with nginx, must use the new path.

For an air-gapped or proxied SEPAL deployment this needs solara 1.65.1 or later,
above the proposed floor. The "Ceiling to remember" section below and
`docs/guides/ipecharts.md` still describe the 1.58.2 cap.

[#1269]: https://github.com/widgetti/solara/pull/1269

---

## 1.60.0 – 1.62.0 (reviewed 2026-09-18)

### Adopted — the 1.60.1 to 1.60.3 lifecycle fixes

These moved the floor from `1.60` to `1.60.3`:

- **1.60.1** — `task.cancel()` and `task.retry()` during kernel close no longer
  raise ([#1188]), and `use_task` keeps results in a component-scoped store
  instead of cleanup code ([#1186]).
- **1.60.2** — per-kernel subscription residue is purged at kernel close
  ([#1189]).
- **1.60.3** — reactive subscriptions and kernel-scoped state are released
  without restart/close races or deadlocks ([#1192], reverted in 1.63.0: see
  the 1.62.1 – 1.65.2 entry); `comm_info_request`
  replies are filtered by `target_name`, so control comms stop leaking to the
  widget manager ([#1191]).

This is the ground pysepal's notification bus stands on: it is kernel-scoped,
holds a refcounted subscriber registry, and drives its UI through
`Reactive.subscribe()`. Every GEE `use_task` hook sits there too. Below 1.60.3 a
kernel that closes while a task is in flight can leave subscription residue
behind.

[#1186]: https://github.com/widgetti/solara/pull/1186
[#1188]: https://github.com/widgetti/solara/pull/1188
[#1189]: https://github.com/widgetti/solara/pull/1189
[#1191]: https://github.com/widgetti/solara/pull/1191
[#1192]: https://github.com/widgetti/solara/pull/1192

### Skipped — `solara.FigureEcharts` (1.62 guarded its option watcher, #1201)

pysepal charts stay on `ipecharts`. The reasoning, and why the upstream fix does
not apply to us, is recorded in `docs/guides/ipecharts.md` §
"Why not `solara.FigureEcharts`?".

### Blocked — ipyvuetify 3 (1.61)

Solara 1.61 supports ipyvuetify 1 and 3 side by side, selected by the installed
version and exposed as `solara.util.IPYVUETIFY_V3`. ipyvuetify 3 is a
prerelease, so `pip install solara` still resolves to ipyvuetify 1 and that code
path is unchanged.

pysepal pins `ipyvuetify>=1.8,<3`, and every `.vue` template in the package is
Vuetify 2 syntax. Migrating is its own project, not a side effect of a Solara
bump; `IPYVUETIFY_V3` is the switch to write against when it starts. Do not
relax the pin one widget at a time.

### Knobs worth knowing — server behaviour (1.60.0)

- `SOLARA_SERVER_SYNC_WS_WRITE=true` writes websocket frames on the calling
  thread and skips the event-loop hop, at the cost of blocking that thread on
  the socket. Worth measuring for an app that pushes many widget updates from
  threads; it is off by default and SEPAL deployments leave it off.
- `gc.freeze()` runs on startup with no setting to turn: garbage-collection cost
  now tracks the number of sessions rather than the size of the process.

### Ceiling to remember — `solara-assets`

`solara-assets` 1.62.0 never reached PyPI; the project hit its storage cap and
1.58.2 is the newest available. This only matters when assets are served
locally instead of from the CDN (`solara.settings.assets.proxy`) — which is
exactly the setup an air-gapped or proxied SEPAL deployment needs. One more
reason to prefer widgets that bundle their JavaScript over widgets that fetch it
at render time.

---

## Adding an entry

One section per reviewed range, dated, with each item labelled **Adopted**,
**Documented**, **Skipped**, or **Blocked** — the label is the part a reader
comes back for. Record the reasoning for a decision not taken too; it stops the
next reader (or agent) re-opening a settled question when the same feature
reappears in a later changelog.
