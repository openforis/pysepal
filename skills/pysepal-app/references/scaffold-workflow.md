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
- find `pysepal.sepalwidgets` imports and `MapApp.element` calls; they move to the
  Solara components

## 3. Generate the Base Scaffold

Pick the default file set from `file-matrix.md`.

Use the templates in `assets/` as the base layer. Replace placeholders immediately. The scaffold must be runnable before any notebook-specific logic is added.

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
