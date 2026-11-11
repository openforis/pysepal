# Existing Repo Rules

Use these rules whenever the user wants scaffolding inside an existing repository.

## Safe Edit Rules

- Never overwrite entrypoints or environment files silently.
- Prefer patching in place when the existing file already follows pysepal conventions.
- Prefer adding adjacent files when replacing the existing file would destroy user-specific behavior.
- If the repository already contains unrelated or conflicting user work, stop and explain the conflict before proceeding.

## What To Inspect First

Inspect these before editing:

- existing entrypoints such as `solara_app.py`, `app.py`, or notebooks
- current dependency files
- current environment files
- current docker files if present
- current component tree
- imports of `pysepal.sepalwidgets` and calls to `MapApp.element`: move them to
  the Solara components with `docs/guides/sepalwidgets-deprecation.md`
- the installed ipyvuetify major, and whether the app runs under Voila (then it
  keeps `ipyvuetify<3`)

## When To Stop And Ask

Stop and ask if:

- the repo mixes incompatible patterns and the migration path is ambiguous
- existing files already implement the same responsibilities with a different architecture
- the requested scaffold would require deleting meaningful user code
- a sepalwidgets widget holds app logic that has no Solara replacement yet
