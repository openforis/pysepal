# File Matrix

These are the default file sets the skill should generate unless the user asks for a different structure.

## Shared Defaults

Generate these for both app families:

- `pyproject.toml`
- `sepal_environment.yml`
- `.pre-commit-config.yaml`
- `component/model/state_manager.py`
- `component/message/`
- `component/tile/`
- `component/widget/`
- `component/scripts/`
- `component/parameter/`

## GEE / Container Apps

Base files:

- `solara_app.py`
- `run_solara.sh`
- `Dockerfile`
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

Do not add an `ipyvuetify<3` pin: pysepal 5 needs ipyvuetify 3. On SEPAL, a
Voila app renders only once the Jupyter server runs ipyvuetify 3.

If a notebook entrypoint is needed, synthesize it from `local-voila-notebook-outline.md`.
