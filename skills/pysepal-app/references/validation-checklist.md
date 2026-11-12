# Validation Checklist

Run this checklist before presenting the finished scaffold.

## Required Checks

- The user explicitly chose the app type.
- The generated structure matches the chosen app family.
- New app state uses `solara.reactive()`.
- No new traitlets observer architecture was scaffolded.
- Every referenced pysepal component exists in the live discovery output.
- Map apps use `MapApp(...)` from `pysepal.solara.components.map_app`, with no
  `.element`, `model=`, `theme_toggle=` or `language_selector=`.
- GEE flows inside Solara components avoid blocking sync calls.
- GEE/container user-file operations use `SepalClient`, not `Path`, `os`,
  `shutil`, `glob`, `open()`, or container-local filesystem writes.
- `pyproject.toml` is the source of truth for Python dependencies.
- `requirements.txt` was not generated.
- `sepal_environment.yml` installs the project with `-e .`.
- `component/message/` exists.
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
