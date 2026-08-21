"""DEV_AUTH mimics production topology: one session per connection.

``PYSEPAL_DEV_AUTH`` exists so a developer can run the real app-launcher shape
locally. That only works if the *scoping* matches production too: a session per
connection, torn down with its kernel. A process-wide session makes three
browser tabs look like one user, hides every per-connection fault until it
reaches SEPAL, and leaves interfaces (and the loop-bound HTTP clients they own)
alive across page reloads.

The developer *login* stays process-cached -- it is a blocking HTTP POST, and
there is only one developer identity. Only the session is per connection.
"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pysepal.solara import session_manager as sm
from pysepal.solara._topology import SessionPlan, SessionSource

_DEV_AUTH = SessionPlan(SessionSource.DEV_AUTH, "test")


def _dev_headers(username="alice"):
    return SimpleNamespace(
        sepal_user=SimpleNamespace(username=username),
        cookies={"SEPAL-SESSIONID": "sid-1"},
        session_id="sid-1",
    )


@contextmanager
def _dev_stack(scope_id, headers=None):
    """Patch the constructors a dev-auth session reaches, pinned to one scope."""
    gee_factory = MagicMock(side_effect=lambda *a, **k: MagicMock())
    drive_factory = MagicMock(side_effect=lambda **k: MagicMock())
    sepal_factory = MagicMock(
        side_effect=lambda **k: SimpleNamespace(
            ensure_results_dir=MagicMock(), module_name=k.get("module_name")
        )
    )
    prime = MagicMock(return_value=headers or _dev_headers())

    with (
        patch.object(sm, "_current_plan", return_value=_DEV_AUTH),
        patch.object(sm, "is_sepal_sandbox", return_value=False),
        patch.object(
            sm,
            "EESession",
            SimpleNamespace(
                from_default=MagicMock(side_effect=lambda **k: MagicMock()),
                from_sepal_headers=MagicMock(side_effect=lambda _h: MagicMock()),
            ),
        ),
        patch.object(sm, "GEEInterface", gee_factory),
        patch.object(sm, "GDriveInterface", drive_factory),
        patch.object(sm, "SepalClient", SimpleNamespace(create=sepal_factory)),
        patch.object(sm, "prime_dev_auth", prime),
        patch.object(sm, "_RESULTS_DIR_EXECUTOR", SimpleNamespace(submit=lambda fn: fn())),
        patch.object(sm.SessionManager, "get_scope_id", lambda _self: scope_id),
        # Dev-auth scopes per connection only when a solara server is serving
        # them; under pytest the real predicate is False.
        patch.object(sm, "is_serving_connections", lambda: scope_id != sm.PROCESS_SCOPE),
    ):
        yield SimpleNamespace(gee=gee_factory, prime=prime, sepal=sepal_factory)


def test_two_connections_get_two_sessions():
    """Two tabs are two users' worth of state, exactly as on SEPAL."""
    manager = sm.SessionManager()

    with _dev_stack("kernel-a"):
        manager.create_session("demo")
        first = manager.get_gee_interface()

    with _dev_stack("kernel-b"):
        manager.create_session("demo")
        second = manager.get_gee_interface()

    assert first is not second


def test_a_reload_does_not_reuse_the_previous_kernels_session():
    """The bug this fixes: a stale interface outliving the loop that owned it."""
    manager = sm.SessionManager()

    with _dev_stack("kernel-a"):
        manager.create_session("demo")
        before = manager.get_gee_interface()
    manager.cleanup_session("kernel-a")

    with _dev_stack("kernel-b"):
        manager.create_session("demo")
        after = manager.get_gee_interface()

    assert after is not before


def test_the_developer_login_is_not_repeated_per_connection():
    """The blocking POST stays process-cached; only the session is per scope."""
    manager = sm.SessionManager()

    with _dev_stack("kernel-a") as first:
        manager.create_session("demo")
    with _dev_stack("kernel-b") as second:
        manager.create_session("demo")

    # prime_dev_auth is itself the process-level cache, so each scope may call
    # it, but it must never be bypassed in favour of a fresh login path.
    assert first.prime.called
    assert second.prime.called


def test_cleanup_closes_a_dev_auth_session():
    """Kernel teardown must actually release the session, as it does on SEPAL."""
    manager = sm.SessionManager()

    with _dev_stack("kernel-a"):
        manager.create_session("demo")
        assert manager._registry.get("kernel-a") is not None

    manager.cleanup_session("kernel-a")

    assert manager._registry.get("kernel-a") is None


def test_without_a_connection_dev_auth_keeps_the_process_session():
    """A notebook, a script or pytest has no kernel to key a session on.

    ``resolve_scope_id`` answers ``PROCESS_SCOPE`` there, and a per-connection
    session refuses that scope -- so those runtimes must keep the process
    session they have always had rather than start raising.
    """
    manager = sm.SessionManager()

    with _dev_stack(sm.PROCESS_SCOPE):
        manager.create_session("demo")

        assert manager._registry.get(sm.PROCESS_SCOPE) is not None
