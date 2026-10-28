"""All the process that can be run using nox.

The nox run are build in isolated environment that will be stored in .nox. to force the venv update, remove the .nox/xxx folder.
"""

import nox

nox.options.sessions = ["lint", "test", "docs"]


@nox.session(reuse_venv=True)
def lint(session):
    """Apply the pre-commits."""
    session.install("pre-commit")
    session.run("pre-commit", "run", "--all-files", *session.posargs)


@nox.session(reuse_venv=False)
def test(session):
    """Run all the test using the environment variable of the running machine."""
    session.install(".[test]")
    session.run("pip", "list")

    # if we are in the sepal-venv, force earthengine api fork
    if "sepal-user" in session.virtualenv.location:
        session.run(
            "pip",
            "install",
            "git+https://github.com/openforis/earthengine-api.git@v0.1.384#egg=earthengine-api&subdirectory=python",
        )

    test_files = session.posargs or ["tests"]
    session.run("pytest", "--color=yes", "--cov", "--cov-report=xml", *test_files)


@nox.session(reuse_venv=False)
def test_gee(session):
    """Run GEE smoke tests. Requires EARTHENGINE_* credentials."""
    session.install(".[test]")
    session.run("pip", "list")

    if "sepal-user" in session.virtualenv.location:
        session.run(
            "pip",
            "install",
            "git+https://github.com/openforis/earthengine-api.git@v0.1.384#egg=earthengine-api&subdirectory=python",
        )

    test_files = session.posargs or ["tests"]
    session.run("pytest", "-m", "gee", "--color=yes", "-vv", *test_files)


@nox.session(name="clean_gee_assets", reuse_venv=True)
def clean_gee_assets(session):
    """Delete stale pysepal test assets from GEE. Dry-run by default; pass -- --yes to delete."""
    session.install(".[test]")
    session.run("python", "-m", "tests._janitor", *session.posargs)


@nox.session(name="dead-fixtures", reuse_venv=True)
def dead_fixtures(session):
    """Check for dead fixtures items."""
    # pytest-deadfixtures 3.1.0 reads FixtureManager._arg2fixturedefs, which
    # pytest 9.2 renamed; drop the cap once upstream PR #61 is released.
    session.install(".[test]", "pytest<9.2")
    test_files = session.posargs or ["tests"]
    # Clear addopts ("-m 'not gee'") so the scan covers both test lanes;
    # otherwise every GEE fixture reports as unused.
    session.run("pytest", "-o", "addopts=", "--dead-fixtures", *test_files)


@nox.session(reuse_venv=True)
def bin(session):
    """Run all the bin methods to validate the conda recipe."""
    session.install(".")
    session.run("module_deploy", "--help")
    session.run("module_factory", "--help")
    session.run("module_venv", "--help")
    session.run("activate_venv", "--help")
    session.run("sepal_ipyvuetify", "--help")


@nox.session(reuse_venv=True)
def docs(session):
    """Build the documentation."""
    session.install(".[doc]")
    # patch version in nox instead of pyproject to avoid blocking conda releases
    session.run("rm", "-rf", "docs/source/modules", external=True)
    session.run("rm", "-rf", "docs/build/html", external=True)

    # build the api doc files
    templates = "docs/source/_templates/apidoc"
    modules = "docs/source/modules"
    session.run("sphinx-apidoc", f"--templatedir={templates}", "-o", modules, "pysepal")

    # build the documentation
    source = "docs/source"
    html = "docs/build/html"
    session.run("sphinx-build", "-b", "html", source, html, "-w", "warnings.txt")

    # check for untracked documentation warnings
    session.run("python", "tests/check_warnings.py")


@nox.session(reuse_venv=True)
def mypy(session):
    """Run a mypy check of the lib."""
    session.install(".[dev]")
    test_files = session.posargs or ["pysepal"]
    session.run(
        "mypy",
        "--scripts-are-modules",
        "--ignore-missing-imports",
        "--install-types",
        "--non-interactive",
        "--disable-error-code",
        "func-returns-value",
        "--warn-redundant-casts",
        *test_files,
    )
