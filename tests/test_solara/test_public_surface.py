"""pysepal.solara has one public surface, and it is complete."""

import ast
from pathlib import Path

import pysepal.solara as ps

INIT_PATH = Path(ps.__file__)

#: The surface pysepal 4.0 ships. Kept as a literal so that changing ``__all__``
#: cannot pass unnoticed: a diff here is the record that the decision was taken.
SEALED_SURFACE = frozenset(
    {
        "MissingSepalHeadersError",
        "NotificationProvider",
        "PROCESS_SCOPE",
        "SepalSessionError",
        "SessionInfo",
        "SessionManager",
        "SessionScopeClosedError",
        "SessionsOverview",
        "ThemeState",
        "UnsupportedSolaraRuntimeError",
        "clear_scoped_state",
        "current_scope_id",
        "get_current_drive_interface",
        "get_current_gee_interface",
        "get_current_sepal_client",
        "get_current_session_info",
        "get_current_theme_state",
        "get_scoped_state",
        "get_sessions_overview",
        "has_scoped_state",
        "notify",
        "prime_dev_auth",
        "resolve_scope_id",
        "resolve_theme_state",
        "setup_sessions",
        "setup_solara_server",
        "setup_theme_colors",
        "track_task",
        "use_notifications",
        "use_theme_dark",
        "with_sepal_sessions",
    }
)


def test_the_surface_is_exactly_the_sealed_set():
    """Both directions matter: an addition and a removal must each turn this red.

    The sibling checks compare ``__all__`` against the imports in the same
    file, so a name added to both sides slips through them together. Only a
    literal pins the surface itself.
    """
    assert set(ps.__all__) == SEALED_SURFACE


def test_no_name_defined_in_the_package_escapes_the_declaration():
    """``__all__`` governs names bound in ``__init__`` too, not just re-exports.

    The AST check below reads ``ImportFrom`` nodes; a helper *defined* in
    ``__init__.py``, or aliased in by plain ``import``, would never appear
    there.
    """
    leaked = {
        name
        for name, value in vars(ps).items()
        if not name.startswith("_")
        and name not in SEALED_SURFACE
        and getattr(value, "__module__", "").startswith("pysepal.solara")
    }
    assert leaked == set()


def test_errors_are_reachable_from_the_package_root():
    for name in (
        "SepalSessionError",
        "MissingSepalHeadersError",
        "SessionScopeClosedError",
        "UnsupportedSolaraRuntimeError",
    ):
        assert name in ps.__all__
        assert getattr(ps, name) is not None


def test_scope_helpers_are_reachable_from_the_package_root():
    for name in ("PROCESS_SCOPE", "current_scope_id", "resolve_scope_id"):
        assert name in ps.__all__


def test_the_topology_types_stay_private():
    """Exporting the enum in a major freezes its members; no app touches it."""
    for name in ("SessionSource", "SessionPlan", "resolve_session_plan"):
        assert name not in ps.__all__


def test_the_scope_registry_stays_private():
    """Shared storage for three internal consumers, not an app-facing type."""
    assert "ScopeRegistry" not in ps.__all__


def test_all_is_sorted_and_every_entry_resolves():
    assert ps.__all__ == sorted(ps.__all__)
    for name in ps.__all__:
        assert hasattr(ps, name), name


def test_every_name_imported_into_the_package_is_declared_public():
    """Catch the other half of a surface bug.

    A name reachable off ``ps`` but missing from ``__all__`` -- e.g. via
    ``from .x import a, b`` where only ``a`` was added to ``__all__`` --
    would slip past ``hasattr``, which only checks that declared names
    resolve, not that resolvable names are declared.
    """
    tree = ast.parse(INIT_PATH.read_text())
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if not (alias.asname or alias.name).startswith("_")
    }
    assert imported_names == set(ps.__all__)


def test_docstring_does_not_say_sepal_ui():
    assert "sepal_ui" not in ps.__doc__
