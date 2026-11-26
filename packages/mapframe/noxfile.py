"""The development sessions: lint, type checks, unit and browser tests, release check.

Each session that installs the package builds the JS bundle first, with the
locked dependencies, so a stale local build never gets tested or shipped.
"""

import os
from pathlib import Path

import nox

PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]

nox.options.sessions = ["lint", "typecheck", "js", "tests"]


def _build_js(session):
    """Install the locked JS dependencies and bundle the widget."""
    session.run("npm", "ci", external=True)
    session.run("npm", "run", "build", external=True)


def _playwright_install():
    """The browser install command; CI runners also need the system libraries."""
    flags = ["--with-deps"] if os.environ.get("CI") else []
    return ["playwright", "install", *flags, "chromium"]


@nox.session(reuse_venv=True)
def lint(session):
    """Run the pre-commit hooks on every file."""
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files", *session.posargs)


@nox.session(reuse_venv=True)
def typecheck(session):
    """Type-check the TypeScript with tsc and the Python with mypy."""
    _build_js(session)
    session.run("npm", "run", "typecheck", external=True)
    # ipykernel: the widget imports it when it is there
    session.install("-e", ".", "mypy", "ipykernel")
    session.run("mypy", *session.posargs)


@nox.session(reuse_venv=True)
def js(session):
    """Run the TypeScript unit tests with Vitest."""
    session.run("npm", "ci", external=True)
    session.run("npm", "test", *session.posargs, external=True)


@nox.session(python=PYTHON_VERSIONS)
def tests(session):
    """Run the Python unit tests."""
    _build_js(session)
    session.install("-e", ".[test]")
    session.run("pytest", *(session.posargs or ["tests", "--ignore=tests/browser"]))


@nox.session(reuse_venv=True)
def browser(session):
    """Run the Playwright browser tests under the Solara, Voila and JupyterLab runners."""
    # JupyterLab writes workspaces, kernel runtime files and the notebook
    # signature database under the user's Jupyter dirs. Venv-installed
    # extensions live in sys.prefix and are still found.
    jupyter_data = Path(session.create_tmp()).resolve() / "jupyter-data"
    workspaces = jupyter_data / "workspaces"
    workspaces.mkdir(parents=True, exist_ok=True)
    _build_js(session)
    session.run("npm", "run", "build:harness", external=True)
    session.install("-e", ".[test]")
    session.run(*_playwright_install())
    session.run(
        "pytest",
        *(session.posargs or ["tests/browser"]),
        env={
            "JUPYTER_DATA_DIR": str(jupyter_data),
            "JUPYTERLAB_WORKSPACES_DIR": str(workspaces),
            "SOLARA_TEST_RUNNERS": "solara,voila,jupyter_lab",
            "SOLARA_TEST_VUETIFY_WARMUP": "false",
        },
    )


@nox.session(name="release-check", reuse_venv=True)
def release_check(session):
    """Build the sdist and a wheel without Node, and smoke-test the installed wheel."""
    session.run("npm", "ci", external=True)
    session.run("npm", "run", "build:harness", external=True)
    session.run("python", "scripts/release_check.py")
