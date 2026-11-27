# Validation Checklist

Run this checklist before presenting the finished scaffold.

## Required Checks

- The user explicitly chose the app type.
- The generated structure matches the chosen app family.
- New app state uses `solara.reactive()`.
- No new traitlets observer architecture was scaffolded.
- Every referenced pysepal name exists in the installed pysepal: components in
  the discovery script's output, which covers `pysepal/solara/components`;
  entry-point helpers, hooks and notifications in `pysepal.solara.__all__`; the
  map in `pysepal.mapping`; layers in `pysepal.layers`.
- Nothing imports `pysepal.sepalwidgets`.
- Map apps use `MapApp(...)` from `pysepal.solara.components.map_app`, with no
  `.element`, `model=`, `theme_toggle=` or `language_selector=`.
- Each map is built with `use_sepal_map` in the component that owns it, and the
  map code follows `docs/guides/solara-map-apps.md`.
- The app's own `rv.*`, `solara.v` and `.vue` code is Vuetify 3, with no
  `IPYVUETIFY_V3` branch.
- The app requires `pysepal>=5` (before the 5.0 release,
  `"pysepal @ git+https://github.com/openforis/pysepal@feat/layer-system"`) and
  does not pin `ipyvuetify<3`.
- GEE flows inside Solara components avoid blocking sync calls.
- GEE/container user-file operations use `SepalClient`, not `Path`, `os`,
  `shutil`, `glob`, `open()`, or container-local filesystem writes.
- `pyproject.toml` is the source of truth for Python dependencies.
- `requirements.txt` was not generated.
- `sepal_environment.yml` installs the project with `-e .`.
- `component/message/` binds `catalog()` and has `en/*.json`, and a map app
  passes `locales=messages.available_locales()` to `MapApp`.
- `.env` is listed in `.gitignore`, and in `.dockerignore` for a container app.
- `ruff check` and `black --check` pass on the generated files.
- Existing repo edits, if any, do not silently replace user-owned architecture.

## GEE-Specific Checks

- `with_sepal_sessions` is used where session-bound behavior is required.
- `get_current_gee_interface()` is called inside components, not at module level.
- `solara.lab.use_task` is used for non-blocking GEE flows.
- direct UI-sized results use async getters
- long-running work uses export submission methods

## Handoff Checks

- The user summary clearly distinguishes ready code from stubs.
- Missing mappings to pysepal components are stated explicitly.
