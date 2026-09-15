---
name: pysepal-app
description: Scaffold or update pysepal Solara and Voila apps using current pysepal architecture. Use when creating a new pysepal app, restructuring an existing app to follow pysepal patterns, mapping notebook logic into a pysepal app, choosing between local/Voila and GEE/container app layouts, wiring session-backed GEE flows, integrating MapApp, or adding user-facing notifications with NotificationProvider and use_notifications.
---

# Pysepal App

Use this skill when building or restructuring pysepal applications.

## Read These Sources First

Always inspect the live repository before writing code.

For app architecture:

- `docs/guides/solara-app-builder.md`
- `docs/guides/solara-gee-patterns.md` for async GEE work
- `docs/guides/solara-notifications.md` when the app has async work, task progress, toasts, or `MapApp`
- `docs/guides/solara-export.md` when the app produces `ee.Image` or `ee.FeatureCollection` layers users can export
- `docs/guides/ipyvuetify-widgets.md` when creating or extending `VuetifyTemplate`/Vue-backed widgets

For repo-specific defaults and scaffold workflow:

- `references/defaults.md`
- `references/file-matrix.md`
- `references/scaffold-workflow.md`
- `references/existing-repo-rules.md`
- `references/validation-checklist.md`

## Core Rules

- New Solara apps use `solara.reactive()` AppState.
- New GEE flows use `solara.lab.use_task(..., prefer_threaded=False)`.
- Retrieve session-bound interfaces inside components with `get_current_gee_interface()` and related getters.
- An app needing neither GEE, `SepalClient` nor Drive omits `@with_sepal_sessions` and keeps `setup_sessions()`; see "Apps that don't use Earth Engine" in `docs/guides/solara-app-builder.md`.
- Never construct a bare `GEEInterface()` in a container app: it raises `SepalSessionError` in a per-connection runtime. Pass `gee_interface=get_current_gee_interface()` to `SepalMap`, `AoiModel`, asset inputs and `process_admin`, or `SepalMap(gee=False)` when the map has no Earth Engine layers.
- GEE/container apps use the session `SepalClient` for all runtime user-file reads, writes, listing, and directory creation.
- Do not write user data to the container filesystem, and do not use `Path`, `os`, `shutil`, `glob`, or `open()` to walk/read/write user workspace files in Solara container apps.
- Do not scaffold new traitlets `.observe()` architectures as the primary pattern for new apps.
- Do not scaffold `gee_interface.create_task()` as the default for new Solara GEE apps.
- Use the live pysepal source tree to confirm component names and APIs before writing imports.

## User File Rules

For GEE/container apps, the SEPAL user workspace is remote from the container
process. Always pass `get_current_sepal_client()` into models, widgets, and
scripts that handle user files, and use:

- `sepal_client.files.list(folder, extensions=...)` to browse user folders
- `sepal_client.files.read_bytes(...)`, `.read_text(...)`, or `.read_json(...)`
  to read user files
- `sepal_client.files.write(path, content, overwrite=...)` to write generated
  user files
- `sepal_client.files.mkdir(path, parents=True)` to create user folders
- `sepal_client.results_path` as the base for module-owned outputs under
  `module_results/<module_name>`

Do not branch on `DEPLOY_ENV` or local/dev mode to write user data with
`Path.mkdir`, `Path.open`, `Path.write_text`, `os.listdir`, `os.walk`, `glob`,
or similar filesystem APIs. Those APIs target the container filesystem, not the
authenticated user's SEPAL files. Container-local access is only acceptable for
read-only packaged assets, templates, and application source files.

## Notification Rules

When a new pysepal Solara app has async work or user-visible state transitions:

- mount `NotificationProvider()` once in the app shell or shared layout
- call `use_notifications()` inside pages, tiles, or widgets that own user-facing work
- use `notifications.track(...)` for long-running tasks
- use final success/error/cancel toasts for task completion state
- a component that may render without a provider passes `use_notifications(required=False)` and provides inline fallback UX; without that flag the hook raises `NotificationProviderError`

Scope model:

- notifications are scoped to the current pysepal app runtime session (the Solara server kernel under `solara run`, or the active notebook kernel under Voila or plain Jupyter), not the route
- routes inside one live page share notification history
- separate browser page loads usually create separate kernels and therefore separate histories

Do not design route-local notification isolation unless the user explicitly wants a different bus model.

## Export Rules

When a new pysepal Solara app produces GEE-backed layers users may want to take out of the app:

- declare one `ExportSource` per exportable layer with a lazy `resolve` callable that returns a `ResolvedExport`
- drop `ExportLauncher(sources=sources, button_text=True)` into the right panel or toolbar
- let the dialog publish toasts through the mounted `NotificationProvider`; do not add inline success/error widgets alongside it
- do not build a second custom export UX unless the dialog genuinely cannot cover the requirements; if customization is needed, prefer `use_export_dialog(...)` + `ExportDialog(controller=...)` over re-implementing submission logic
- use canonical file-format values (`"GEO_TIFF"`, `"GEO_JSON"`, `"SHP"`, `"CSV"`, `"KML"`, `"KMZ"`) at the pysepal to ee-client boundary
- match pysepal's own `ee-client>=3.2.1,<4` floor in the app's pyproject rather
  than pinning an older ee-client

## App Shell Guidance

If the app uses `MapApp`, notification UI should live in the same page or shared shell so it can consume the layout CSS variables published by `MapApp`.

Default placement:

- single-page app: provider inside the main `Page()` shell
- multipage app with shared layout: provider in the common layout
- avoid mounting duplicate providers in multiple simultaneously mounted pages

## Working Mode

1. Determine app type and whether the repo is new or existing.
2. Inspect the current file tree and entrypoints.
3. Read the guides above before scaffolding.
4. Choose the default file set from `references/file-matrix.md`.
5. Build a runnable base scaffold first.
6. Map notebook or legacy logic into `component/model`, `component/tile`, `component/widget`, `component/scripts`, `component/parameter`, and `component/message`.
7. Add notifications using the default rules when the app has async work.
8. Run through `references/validation-checklist.md` before handoff.

## Existing Repo Safety

When editing an existing repo:

- patch in place when the current architecture already matches pysepal conventions
- do not silently replace user-owned entrypoints or environment files
- if the repo already has a different notification or task pattern, inspect it before replacing it
- stop and explain conflicts before deleting or rewriting meaningful user code
