# File Matrix

These are the default file sets the skill should generate unless the user asks for a different structure.

## Shared Defaults

Generate these for both app families:

- `pyproject.toml`
- `sepal_environment.yml`
- `.pre-commit-config.yaml`
- `.gitignore`
- `component/__init__.py`
- `component/model/__init__.py` and `component/model/state_manager.py`
- `component/message/__init__.py` and `component/message/en/app.json`
- `component/tile/__init__.py`
- `component/widget/__init__.py`
- `component/scripts/__init__.py`
- `component/parameter/__init__.py`

The `__init__.py` files are empty, except the message one. They make
`component` a regular package, which setuptools' flat-layout discovery finds
for `pip install -e .`.

## GEE / Container Apps

Base files:

- `solara_app.py`
- `run_solara.sh`
- `Dockerfile`
- `.dockerignore`
- `docker-compose.yml`
- `supervisord.conf`
- `.env.example` or `.env` bootstrap file when appropriate

Use templates from:

- `assets/shared/`
- `assets/gee-container/`

## Local / Voila Apps

Base files:

- `app.py` or equivalent local entrypoint
- `run_solara.sh`
- notebook or Voila entrypoint if the user explicitly wants one

Use templates from:

- `assets/shared/`
- `assets/local-voila/`

Do not add an `ipyvuetify<3` pin: pysepal 5 needs ipyvuetify 3.

If a notebook entrypoint is needed, synthesize it from `local-voila-notebook-outline.md`.

## Template Targets

A template's output path is its name without `.template`, at the project root,
except these:

| Template                                        | Output                             |
| ----------------------------------------------- | ---------------------------------- |
| `assets/shared/pre-commit-config.yaml.template` | `.pre-commit-config.yaml`          |
| `assets/shared/gitignore.template`              | `.gitignore`                       |
| `assets/gee-container/dockerignore.template`    | `.dockerignore`                    |
| `assets/shared/state_manager.py.template`       | `component/model/state_manager.py` |
| `assets/shared/message/__init__.py.template`    | `component/message/__init__.py`    |
| `assets/shared/message/en/app.json.template`    | `component/message/en/app.json`    |
