"""A session-less ``GEEInterface`` is refused where the process serves many users.

Since 4.0 every method goes through the session; there is no global-``ee``
branch left. An interface built with no session resolves one from
``~/.config/earthengine/credentials`` instead -- the platform service-account
key in an app-launcher container -- so the refusal moved to the constructor,
which is also the only place that knows the runtime topology. It lives there
rather than in each caller because ``gee_interface or GEEInterface()`` appears
in five places across four subpackages, and that list only grows.

Resolution itself is lazy; the guard is not. See
``test_construction_does_not_resolve_credentials`` for why.
"""

import inspect
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from eeclient.tasks import Task

from pysepal.scripts import gee_interface as gee_interface_module
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara import session_manager as session_manager_module
from pysepal.solara._topology import SessionPlan, SessionSource
from pysepal.solara.errors import SepalSessionError

PER_CONNECTION = SessionPlan(SessionSource.PER_CONNECTION, "test")
PROCESS = SessionPlan(SessionSource.PROCESS, "test")
DEV_AUTH = SessionPlan(SessionSource.DEV_AUTH, "test")


@contextmanager
def _topology(plan):
    """Stage a runtime and count event loops, which is how the leak is asserted."""
    new_event_loop = MagicMock(side_effect=lambda: MagicMock())

    with (
        patch.object(session_manager_module, "_current_plan", return_value=plan),
        patch.object(gee_interface_module.asyncio, "new_event_loop", new_event_loop),
        patch.object(gee_interface_module.threading, "Thread", MagicMock()),
    ):
        yield SimpleNamespace(new_event_loop=new_event_loop)


def test_a_per_connection_runtime_refuses_a_session_less_interface():
    with _topology(PER_CONNECTION) as stubs:
        with pytest.raises(SepalSessionError, match="platform service account"):
            GEEInterface()

    # Refused before the loop exists. A guard that raised afterwards would leak
    # one event loop and one daemon thread per attempt, forever.
    assert stubs.new_event_loop.call_count == 0


def test_a_session_bound_interface_is_always_allowed():
    """The correct construction in a container: built from this connection's session."""
    session = MagicMock()

    with _topology(PER_CONNECTION):
        interface = GEEInterface(session=session)

    assert interface.session is session


@pytest.mark.parametrize("plan", [PROCESS, DEV_AUTH], ids=["process", "dev_auth"])
def test_a_single_identity_runtime_resolves_the_machine_credentials(plan):
    """A notebook, a script, pytest and a sandbox own their machine credentials.

    Reading them is the normal path there, and narrowing the guard past
    PER_CONNECTION would break every one of them for no safety gain.
    """
    resolved = MagicMock()

    with _topology(plan) as stubs:
        with patch.object(gee_interface_module.EESession, "from_default", return_value=resolved):
            interface = GEEInterface()
            assert interface.session is resolved

    assert stubs.new_event_loop.call_count == 1


def test_construction_does_not_resolve_credentials():
    """Building an interface must not require Earth Engine to be set up.

    Resolution is deferred to first use because eager resolution breaks three
    real cases at once: ``SepalMap()`` in a notebook with no Earth Engine
    configured, the 84 test sites that build a map and never call Earth Engine,
    and the unit lane on fork PRs, where ``EARTHENGINE_TOKEN`` is empty by
    design and ``from_default`` therefore raises ``CredentialsResolutionError``.
    """
    from_default = MagicMock()

    with _topology(PROCESS):
        with patch.object(gee_interface_module.EESession, "from_default", from_default):
            interface = GEEInterface()
            assert from_default.call_count == 0, "credentials resolved at construction"

            interface.session
            assert from_default.call_count == 1

            interface.session
            assert from_default.call_count == 1, "resolved more than once"


def test_closing_an_unused_interface_never_resolves_credentials():
    """``close()`` reads the raw slot, not the property.

    Culling a kernel must not reach for a credential store to tear down an
    interface that never used one -- on a machine with none, that would turn
    cleanup into an exception.
    """
    from_default = MagicMock()

    with _topology(PROCESS):
        with patch.object(gee_interface_module.EESession, "from_default", from_default):
            GEEInterface().close()

    assert from_default.call_count == 0


def test_the_use_sepal_headers_door_is_gone():
    """The one constructor path that built an identity this guard could not see.

    ``GEEInterface(use_sepal_headers=True)`` logged in from
    ``LOCAL_SEPAL_USER``/``LOCAL_SEPAL_PASSWORD`` and assigned the result to
    ``session``, so ``session is None`` was already False by the time the guard
    ran -- one process-wide developer identity, served in any runtime including
    a multi-user container. It had no callers in pysepal, in the tests, or in
    any downstream module, and 4.0 removes it; ``PYSEPAL_DEV_AUTH`` is the
    supported way to run on a developer login, and it goes through topology.
    """
    assert "use_sepal_headers" not in inspect.signature(GEEInterface.__init__).parameters

    with pytest.raises(TypeError, match="use_sepal_headers"):
        GEEInterface(use_sepal_headers=True)


def test_the_guard_is_inert_under_a_real_plain_runtime():
    """No plan patched: pytest resolves PROCESS, so ``GEEInterface()`` is unchanged.

    The compatibility half. Every other test here stages a topology; this one
    runs the real resolver, which is what the existing bare ``GEEInterface()``
    call sites in ``scripts.gee``, ``mapping.visualization`` and the test
    fixtures rely on.
    """
    interface = GEEInterface()
    interface.close()


def _task(state: str) -> Task:
    """A real ee-client ``Task``, not a stand-in.

    The bug this guards against was reading ``task["state"]`` on a pydantic
    model. A ``MagicMock`` would answer that subscript happily and the test
    would pass against the broken code, so the real model is the whole point.
    """
    return Task.model_validate(
        {
            "name": "projects/p/operations/ABC123",
            "metadata": {
                "@type": "type.googleapis.com/google.earthengine.v1alpha.OperationMetadata",
                "state": state,
                "description": "my-export",
                "priority": 100,
                "createTime": "2026-08-17T10:00:00Z",
                "type": "EXPORT_IMAGE",
            },
        }
    )


@pytest.mark.parametrize(
    ("state", "expected"),
    [("RUNNING", True), ("READY", True), ("COMPLETED", False), ("FAILED", False), (None, False)],
)
def test_is_running_reads_the_task_state_off_the_model(state, expected):
    """``is_running`` must read ``task.metadata.state``, not subscript the task.

    This path was dead until 4.0 collapsed the interface onto its session: every
    caller held a session-less interface and took the global-ee branch, so the
    session branch shipped with ``task["state"]`` in it and only ever failed in
    the GEE lane. Asserting it here keeps the check in the lane that runs on
    every push.
    """
    session = MagicMock()
    session.tasks.get_task_by_name_async = AsyncMock(return_value=_task(state) if state else None)

    interface = GEEInterface(session=session)
    try:
        assert interface.is_running("my-export") is expected
    finally:
        interface.close()


def test_dev_auth_serving_a_connection_refuses_a_session_less_interface():
    """Dev-auth mimics production, so it must refuse what production refuses.

    Armed under a real solara connection, a session-less interface would read
    the machine's Earth Engine credentials instead of the session's -- the
    exact class of bug ``PYSEPAL_DEV_AUTH`` exists to surface locally rather
    than on SEPAL. Without a connection (notebook, script, pytest) the machine
    credentials stay correct, which the parametrized test above pins.
    """
    with _topology(DEV_AUTH) as stubs:
        with patch.object(session_manager_module, "is_serving_connections", lambda: True):
            with pytest.raises(SepalSessionError, match="platform service account"):
                GEEInterface()

    assert stubs.new_event_loop.call_count == 0


def test_the_guard_creates_no_event_loop_deciding_about_dev_auth():
    """Deciding must stay free of side effects, whichever way it goes.

    The guard exists to refuse *before* the loop is built. An earlier version
    asked ``resolve_scope_id()``, which reaches into IPython and creates an
    event loop even when it fails -- so merely deciding leaked exactly what the
    guard is there to prevent.
    """
    with _topology(DEV_AUTH) as stubs:
        with patch.object(gee_interface_module.EESession, "from_default", return_value=MagicMock()):
            GEEInterface()

    # One loop, built by the interface itself -- none from the decision.
    assert stubs.new_event_loop.call_count == 1
