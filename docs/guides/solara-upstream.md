# Upstream Solara changes

A running log of what each upstream Solara release means for pysepal: what we
adopted, what we only documented, what we deliberately skipped, and what stays
blocked. Add an entry whenever the pin moves or a release touches something we
rely on.

The pin lives in `pyproject.toml`: `solara>=1.60.3,<2`. Two private APIs are
load-bearing — `solara.scope.get_kernel_id` and `solara._using_solara_server` —
so upstream releases get read rather than trusted, and the major is capped.

Upstream changelog: `solara/website/pages/changelog/changelog.md` in the Solara
repository.

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
  without restart/close races or deadlocks ([#1192]); `comm_info_request`
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
