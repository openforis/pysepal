# Scaffold Workflow

Use this flow every time the skill creates or restructures an app.

## 1. Confirm the Generation Mode

Ask for these decisions explicitly:

1. app type: GEE/container or local/Voila
2. existing repo or new project
3. project name if new
4. analysis inputs: notebook, repo, instructions, or combination

Do not skip the app-type question.

## 2. Inspect Before Generating

Read the current pysepal docs and run the live discovery script before writing code.

For existing repos:

- inspect the current file tree
- inspect git status if available
- identify files that already implement app entrypoints, state, and environment setup
- find `pysepal.sepalwidgets` imports and `MapApp.element` calls (removed in
  5.0); they move to the Solara components

## 3. Generate the Base Scaffold

Pick the default file set from `file-matrix.md`.

Use the templates in `assets/` as the base layer, written to the paths in
"Template Targets" of `file-matrix.md`. Replace placeholders immediately. The
scaffold must be runnable before any notebook-specific logic is added.

| Placeholder               | Meaning                                                          | Example                            |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------------- |
| `{{project_slug}}`        | Python distribution name; install folder in the image            | `forest_monitor`                   |
| `{{project_name}}`        | Human name in the AppState docstring                             | `Forest Monitor`                   |
| `{{project_description}}` | `pyproject.toml` description                                     | `Monitor forest cover change`      |
| `{{app_title}}`           | Title: `en/app.json`, the route label, the log line              | `Forest Monitor`                   |
| `{{app_icon}}`            | MDI icon beside the title                                        | `mdi-forest`                       |
| `{{module_name}}`         | `with_sepal_sessions(module_name=...)`: results folder           | `forest_monitor`                   |
| `{{module_slug}}`         | Logger name                                                      | `forest_monitor`                   |
| `{{repo_url}}`            | Source Code and Report Bug links; empty hides them               | `https://github.com/org/repo`      |
| `{{conda_env_name}}`      | micromamba environment, in the image and `sepal_environment.yml` | `forest_monitor`                   |
| `{{port}}`                | Local `solara run` port in `run_solara.sh`                       | `8900`                             |
| `{{container_port}}`      | Port Solara serves in the container, and its healthcheck         | `8765`                             |
| `{{root_path}}`           | The app-launcher path Solara is served under                     | `/api/app-launcher/forest_monitor` |
| `{{service_name}}`        | docker-compose service and container name                        | `forest_monitor`                   |
| `{{image_name}}`          | docker-compose image                                             | `forest_monitor:latest`            |

## 4. Adapt the User Inputs

Map the user material into the scaffold:

- notebook cell logic becomes `component/scripts/` functions and AppState fields
- UI sections become `component/tile/` or `component/widget/`, built from
  Solara components (never `pysepal.sepalwidgets`)
- constants and paths become `component/parameter/`
- user file access becomes `SepalClient` operations for GEE/container apps,
  never container-local `Path`/`os` filesystem reads or writes
- strings become `component/message/`

## 5. Validate

Run through `validation-checklist.md` before presenting the result.

## 6. Handoff

Tell the user:

- what was created
- what was adapted from their source material
- what is stubbed
- what needs their next decision
