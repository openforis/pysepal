# Pysepal App Defaults

These defaults were recovered from the saved pysepal design session and should be treated as the current baseline unless the user explicitly overrides them.

## Agreed Defaults

- Ask the user to choose the app type explicitly.
- New apps always use `solara.reactive()` AppState.
- New apps never scaffold traitlets observer flows as the primary pattern.
- Always include `component/message/` and the `catalog()`/`msg()` pattern.
- Use live pysepal source discovery instead of a baked-in component list.
- Use `pyproject.toml` as the single source of truth for Python dependencies.
- Do not create `requirements.txt`.
- Create `sepal_environment.yml`.
- Skip `noxfile.py` by default.
- Use a two-pass scaffold:
  - base runnable scaffold
  - notebook/repo-specific enrichment

## Standard Project Structure

```text
project/
├── pyproject.toml
├── sepal_environment.yml
├── .pre-commit-config.yaml
├── component/
│   ├── model/
│   ├── tile/
│   ├── widget/
│   ├── scripts/
│   ├── parameter/
│   └── message/
└── ...
```

## GEE / Container App Files

Default output set:

- `solara_app.py`
- `run_solara.sh`
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.override.yml` when local overrides are useful
- `supervisord.conf`
- env bootstrap files as needed
- the standard `component/` tree

Auth expectations:

- work with SEPAL header/env auth when available
- work with local `earthengine authenticate` credentials when developing outside SEPAL

GEE execution expectations:

- follow `docs/guides/solara-gee-patterns.md`
- use `solara.lab.use_task`
- use immutable request snapshots
- keep task state mirrored into AppState

User file expectations:

- use `get_current_sepal_client()` / `SepalClient` for all user-file reads,
  writes, directory creation, and listing
- never write user data to the container filesystem
- do not scaffold `Path`, `os`, `shutil`, `glob`, `open()`, or similar
  filesystem access for user workspace data in GEE/container apps
- keep the same `SepalClient` code path in local development and SEPAL
  deployment; do not branch to local filesystem writes

## Local / Voila App Files

Default output set:

- `pyproject.toml`
- `sepal_environment.yml`
- notebook or Voila entrypoint files
- the standard `component/` tree

Local apps still use:

- pysepal Solara components
- `solara.reactive()` AppState
- pyproject-managed Python dependencies
- pre-commit tooling
- `catalog()`/`msg()` i18n structure

## Dependency Defaults

`pyproject.toml` owns Python dependencies.

`sepal_environment.yml` owns conda-level or compiled dependencies and installs the local project with:

```yaml
dependencies:
  - pip
  - pip:
      - -e .
```

## Repo-Local Draft Target

The first draft of the skill should live in:

- `skills/pysepal-app/SKILL.md`
- `skills/pysepal-app/agents/openai.yaml`

Install or copy it into a user-specific skill directory only after the repo-local version is reviewed.
