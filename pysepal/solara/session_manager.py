"""Session Manager for gee, drive and sepal interfaces for Solara applications.

This module provides centralized session management for gee, gdrive and sepal interfaces,
handling initialization, cleanup, and session tracking across different
Solara applications.
"""

import logging
import os
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from eeclient.client import EESession
from eeclient.models import SepalHeaders
from pydantic import ValidationError
from pysepal_api import SepalClient
from pysepal_api.errors import PysepalError
from solara.lab.utils.headers import headers

from pysepal.scripts.drive_interface import GDriveInterface
from pysepal.scripts.gee_interface import GEEInterface
from pysepal.solara._topology import (
    SessionPlan,
    SessionSource,
    current_session_plan,
    is_sepal_sandbox,
    is_serving_connections,
    plan_reads_sepal_headers,
)
from pysepal.solara.dev_auth import prime_dev_auth

# Imported only to raise below; not re-exported in __all__ -- see pysepal.solara.errors.
from pysepal.solara.errors import (
    MissingSepalHeadersError,
    SepalSessionError,
    SessionScopeClosedError,
)
from pysepal.solara.runtime_context import (
    PROCESS_SCOPE,
    UnsupportedSolaraRuntimeError,
    resolve_scope_id,
)
from pysepal.solara.scope_registry import ScopeRegistry
from pysepal.solara.session_info import SessionInfo, SessionsOverview
from pysepal.solara.ui_state import clear_scoped_state

logger = logging.getLogger("sepalui.session_manager")

__all__ = [
    "SessionManager",
    "resolve_sepal_headers",
    "setup_sessions",
]

CLOSED_SCOPE_MEMORY = 256
"How many cleaned-up scope ids to remember, to refuse late resurrection."

_RESULTS_DIR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pysepal-results-dir")
"""Off-render-path worker for module results directory creation.

``SepalClient.create()`` is pure, so the ``createFolder`` POST that used to run
inside it now runs here instead of on the render thread while a scope lock is
held. Two workers: the call is idempotent and rare, and a stuck SEPAL API must
not be able to starve anything.
"""


def resolve_sepal_headers(raw_headers: dict) -> SepalHeaders:
    """Validate a connection's raw headers into SEPAL headers.

    Args:
        raw_headers: The request headers Solara exposes for this connection.

    Returns:
        The validated SEPAL headers.

    Raises:
        MissingSepalHeadersError: The headers are not SEPAL headers. A
            per-connection runtime has no second credential source to try:
            degrading here would hand the caller the container's platform
            service account instead of the user's own identity.
    """
    try:
        sepal_headers = SepalHeaders.model_validate(raw_headers)
    except ValidationError as exc:
        raise MissingSepalHeadersError(
            "The connection carries no SEPAL authentication headers "
            f"({exc.error_count()} validation errors). This app runs "
            "per-connection, where credentials come from the SEPAL proxy only."
        ) from exc
    return _require_session_id(sepal_headers)


def _require_session_id(sepal_headers: SepalHeaders) -> SepalHeaders:
    """Validate that SEPAL headers carry a SEPAL-SESSIONID cookie.

    ``SepalHeaders.parse_cookies`` silently drops unparsable cookies, so a
    structurally valid header set can validate with an empty cookie jar. Left
    unchecked, that surfaces downstream as a bare ``KeyError:
    'SEPAL-SESSIONID'`` -- exactly the failure mode this release's safety
    rule exists to eliminate.

    Args:
        sepal_headers: Headers already validated by ``SepalHeaders.model_validate``.

    Returns:
        The same headers, unchanged.

    Raises:
        MissingSepalHeadersError: No ``SEPAL-SESSIONID`` cookie is present.
    """
    if sepal_headers.session_id is None:
        raise MissingSepalHeadersError(
            "The SEPAL headers carry no SEPAL-SESSIONID cookie; a SEPAL "
            "session cannot be created without one."
        )
    return sepal_headers


def _carries_sepal_headers() -> bool:
    """Whether this connection's headers validate as SEPAL headers.

    Read only by the arming interlocks in
    :func:`pysepal.solara._topology.resolve_session_plan` -- ``PYSEPAL_DEV_AUTH``
    and ``PYSEPAL_LOCAL_EE``. The PROCESS versus PER_CONNECTION decision never
    consults it.
    """
    raw_headers = headers.value
    if raw_headers is None:
        return False
    try:
        SepalHeaders.model_validate(raw_headers)
    except ValidationError:
        return False
    return True


def _is_scoped_per_connection(plan: SessionPlan) -> bool:
    """Whether the session of this plan belongs to one connection, not the process.

    The credential source and the session scope are two different decisions.
    ``PYSEPAL_DEV_AUTH`` gives the app-launcher shape on a local machine, thus it
    must also scope like it. A process session makes several tabs look like one
    connection and keeps interfaces alive across reloads. The developer login
    stays in the process cache in :func:`prime_dev_auth`. Only the session is
    per scope.

    ``DEV_AUTH`` is per connection only where connections exist. A notebook, a
    script and pytest have no kernel for a session key, thus they keep the
    process session.

    Args:
        plan: The resolved credential plan.

    Returns:
        True when the session is per connection.
    """
    if plan.source is SessionSource.PER_CONNECTION:
        return True
    return plan.source is SessionSource.DEV_AUTH and is_serving_connections()


def _current_plan() -> SessionPlan:
    """Resolve this runtime's credential plan.

    Validates the connection headers only when an arming flag that reads them is
    set: ``create_session`` runs on every render, where its fast path depends on
    not parsing headers at all.
    """
    has_headers = _carries_sepal_headers() if plan_reads_sepal_headers(os.environ) else False
    return current_session_plan(has_sepal_headers=has_headers)


class SessionManager:
    """A singleton session manager for solara-sepal applications.

    This class manages the lifecycle of sessions across different Solara applications,
    providing a centralized way to handle session creation, retrieval, and cleanup for
    GEE interfaces, SepalClient and GDriveInterface.

    Note: Do not instantiate this class directly. Use the @with_sepal_sessions
    decorator or the utility functions in pysepal.solara.utils instead.
    """

    _instance = None
    """Singleton instance of the SessionManager."""

    _singleton_lock = threading.Lock()
    """Serialises construction, from ``__new__`` through the ``__init__`` body.

    ``type.__call__`` runs those as two separate check-then-act steps, and
    ``_registry`` and ``_closed_scopes`` are *instance* attributes (test
    isolation depends on that), so a lost race does not merely waste an object
    -- it splits the state. The orphan's sessions are never cleaned up, its
    ``GEEInterface`` keeps a private event-loop thread alive, and the
    tombstones it writes are read by nobody, so a cleaned-up scope becomes
    resurrectable. ``setup_sessions()`` runs on concurrent kernel-start
    threads, so the window is real. Taken only here, and never while holding
    any other pysepal lock.
    """

    def __new__(cls):
        """Create or return the singleton instance of SessionManager."""
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self):
        """Initialize the SessionManager singleton instance."""
        with self._singleton_lock:
            if hasattr(self, "_initialized"):
                return
            # The raising resolver, not the registry's lenient default: a call
            # that forgot its scope_id must fail loudly rather than read and
            # write a user's credentials in the shared process bucket.
            self._registry: ScopeRegistry[Dict[str, Any]] = ScopeRegistry(
                "session", resolver=resolve_scope_id
            )
            # Tombstones are this consumer's lifetime policy, and the registry's
            # other two consumers disagree with it, so they stay here under
            # their own lock -- taken inside the scope lock, see _reopen_scope.
            self._closed_scopes: Deque[str] = deque(maxlen=CLOSED_SCOPE_MEMORY)
            self._closed_lock = threading.Lock()
            # Last: is_initialized() reads this attribute without the lock, so
            # it must not vouch for state that does not exist yet.
            self._initialized = True

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if the SessionManager has been initialized."""
        return cls._instance is not None and hasattr(cls._instance, "_initialized")

    def get_scope_id(self) -> str:
        """Get the current supported Solara/Voila runtime ID."""
        return resolve_scope_id()

    def _reopen_scope(self, scope_id: str) -> None:
        """Forget a scope's tombstone because its kernel is genuinely restarting.

        Solara's hot-reload restarts a kernel in place: it runs the on-close
        callbacks (our ``cleanup_session``, which tombstones the scope) and
        then re-runs ``on_kernel_start`` -- i.e. ``setup_sessions`` -- for the
        *same* kernel id. Without this, the tombstone would permanently brick
        that scope on the very first file save. Only ``setup_sessions`` calls
        this, so a late callback on another thread can't trigger it.

        Takes the scope lock, not just the registry lock: ``cleanup_session``
        writes the tombstone from inside its own scope-lock section, well
        after ``_close_session`` (which can block for seconds closing the GEE
        interface). Without the scope lock here, a reopen landing while that
        close is still in flight would find no tombstone to remove yet, and
        then lose the race when cleanup writes one moments later -- bricking
        the scope for good, exactly what this method exists to prevent.

        Args:
            scope_id: The scope whose kernel is (re)starting.
        """
        with self._registry.scope_lock(scope_id):
            with self._closed_lock:
                while scope_id in self._closed_scopes:
                    self._closed_scopes.remove(scope_id)

    def create_session(self, module_name: str = "default") -> None:
        """Create -- or reuse -- the session for the current runtime.

        Dispatches on runtime topology, never on credential probing: an
        app-launcher container builds one session per connection from that
        connection's SEPAL headers, and every other runtime -- a SEPAL sandbox,
        Voila, plain Jupyter, a script -- shares one session for the process,
        built from a developer login when ``PYSEPAL_DEV_AUTH`` is armed and
        from the machine's own credentials otherwise.

        Args:
            module_name: The module name for the SepalClient.

        Raises:
            MissingSepalHeadersError: A per-connection runtime carries no valid
                SEPAL headers.
            SessionScopeClosedError: The scope was already cleaned up.
            EEClientError: For authentication-related errors.
        """
        plan = _current_plan()
        if _is_scoped_per_connection(plan):
            self._create_connection_session(module_name, plan)
        else:
            self._ensure_process_session(plan, module_name)

    def _create_connection_session(self, module_name: str, plan: SessionPlan) -> None:
        """Create -- or reuse -- this connection's session from its SEPAL headers.

        The common case is the raw-header fast path: the same connection hands
        back the same headers object and nothing is parsed. Otherwise the
        session is idempotent per *identity* rather than per scope -- one whose
        username or SEPAL-SESSIONID no longer matches is torn down and rebuilt,
        because a bare scope-id check would hand a recycled scope the previous
        user's interfaces. On an already-live session, a ``SepalClient.create()``
        failure for a new ``module_name`` propagates as-is and leaves the
        session -- and its other modules' clients -- intact.

        Under ``DEV_AUTH`` the connection has no SEPAL headers, because there is
        no SEPAL proxy in front of a local ``solara run``. The identity comes
        from the process-cached developer login. The lifetime is the same either
        way, which is the point.

        Args:
            module_name: The module name for the SepalClient.
            plan: The resolved credential plan, which selects the identity source.

        Raises:
            MissingSepalHeadersError: The connection carries no valid SEPAL headers.
            SepalSessionError: The scope id collides with the reserved process scope.
            SessionScopeClosedError: The scope was already cleaned up.
            EEClientError: For authentication-related errors.
        """
        scope_id = self.get_scope_id()
        if scope_id == PROCESS_SCOPE:
            # solara's kernel id is client-supplied (the websocket's URL path segment,
            # overridable via ?kernelid=) and not allowlisted -- a connection choosing
            # this id would otherwise read and write the shared process/dev-auth session.
            raise SepalSessionError(
                f"Scope id {scope_id!r} collides with the reserved process scope; "
                "refusing to create a per-connection session there."
            )

        dev_auth = plan.source is SessionSource.DEV_AUTH
        # prime_dev_auth is the process cache: one blocking POST for the
        # process, not one for each connection.
        current_headers = _require_session_id(prime_dev_auth()) if dev_auth else headers.value
        if current_headers is None:
            raise MissingSepalHeadersError(
                f"No SEPAL authentication headers are available for scope {scope_id}; "
                "a SEPAL session cannot be created without them."
            )

        with self._registry.scope_lock(scope_id):
            with self._closed_lock:
                if scope_id in self._closed_scopes:
                    raise SessionScopeClosedError(
                        f"Scope {scope_id} was cleaned up; refusing to resurrect its session."
                    )

            existing = self._registry.get(scope_id)
            if existing is not None and existing.get("raw_headers") is current_headers:
                logger.debug(f"Reusing session for scope {scope_id}")
                self._ensure_sepal_client(existing, module_name)
                return

            # prime_dev_auth returns parsed SepalHeaders. Only a real
            # connection gives a raw dict that you must parse.
            sepal_headers = current_headers if dev_auth else resolve_sepal_headers(current_headers)
            username = sepal_headers.sepal_user.username
            sepal_session_id = sepal_headers.cookies["SEPAL-SESSIONID"]

            if existing is not None:
                if (
                    existing.get("username") == username
                    and existing.get("sepal_session_id") == sepal_session_id
                ):
                    existing["raw_headers"] = current_headers
                    logger.debug(f"Reusing session for scope {scope_id}")
                    self._ensure_sepal_client(existing, module_name)
                    return

                logger.warning(
                    f"Identity changed on scope {scope_id} "
                    f"({existing.get('username')} -> {username}); rebuilding the session"
                )
                # Unlink before closing: GEEInterface() below is unguarded, and a
                # scope must never expose a session whose interfaces are already closed.
                self._registry.pop(scope_id)
                self._close_session(scope_id, existing)

            logger.debug(f"Creating session for scope {scope_id}")
            gee_session = EESession.from_sepal_headers(sepal_headers)
            gee_interface = GEEInterface(gee_session)
            session: Dict[str, Any] = {
                "username": username,
                "sepal_session_id": sepal_session_id,
                "raw_headers": current_headers,
                "gee_interface": gee_interface,
                "sepal_clients": {},
                "active_module_name": module_name,
                "drive_interface": None,
                "results_dirs_scheduled": set(),
            }
            try:
                self._ensure_sepal_client(session, module_name)
                session["drive_interface"] = GDriveInterface(sepal_headers=sepal_headers)
            except BaseException:
                # Close whatever was actually built before re-raising -- otherwise a
                # flapping SEPAL API leaks one GEEInterface (and its event loop) per render.
                self._close_session(scope_id, session)
                raise

            self._registry.set(session, scope_id)

        logger.debug(f"Sessions created for scope {scope_id} and gee_interface {id(gee_interface)}")

    def _ensure_sepal_client(self, session: Dict[str, Any], module_name: str) -> SepalClient:
        """Return the session's client for ``module_name``, creating it on miss.

        One session per scope holds one client per module name. Keying whole
        sessions by (scope, module) would multiply ``GEEInterface``, and each of
        those owns a private event loop.

        Args:
            session: The session payload to read and mutate.
            module_name: The module whose client is required.

        Returns:
            The client for ``module_name``, which also becomes the active one.
        """
        clients = session["sepal_clients"]
        client = clients.get(module_name)
        if client is None:
            client = SepalClient.create(
                session_id=session["sepal_session_id"], module_name=module_name
            )
            clients[module_name] = client
            self._schedule_results_dir(session, module_name, client)
            logger.debug(f"Created SepalClient for module '{module_name}'")

        # Deliberately after creation succeeds: if SepalClient.create() raises above,
        # this line never runs and the active module keeps pointing at a route that
        # actually has a client, instead of one whose client failed to build.
        session["active_module_name"] = module_name
        return client

    def _schedule_results_dir(
        self, session: Dict[str, Any], module_name: str, client: SepalClient
    ) -> None:
        """Create this module's results directory off the render path, once.

        The caller holds the scope lock, which is what makes the bookkeeping set
        safe to touch. Failures are logged and swallowed: every writer in the
        deployed apps creates its own target with ``parents=True``, so a missing
        directory here costs nothing.

        Args:
            session: The session that owns the client.
            module_name: The module whose directory to create.
            client: The client to create it with.
        """
        scheduled = session.setdefault("results_dirs_scheduled", set())
        if module_name in scheduled:
            return

        def _run() -> None:
            try:
                client.ensure_results_dir()
            except Exception:
                logger.warning(
                    f"Could not create the results directory for '{module_name}'",
                    exc_info=True,
                )

        try:
            _RESULTS_DIR_EXECUTOR.submit(_run)
        except Exception:
            # A rejected submission (e.g. the executor is shutting down) must not
            # escape onto the render path -- exactly what this method exists to
            # prevent -- and must not mark the module done if it never ran.
            logger.warning(
                f"Could not schedule the results directory for '{module_name}'",
                exc_info=True,
            )
            return
        scheduled.add(module_name)

    def _ensure_process_session(
        self, plan: SessionPlan, module_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Return the process-wide session, creating its shell on first use.

        Acquires the process scope lock itself; for a caller that also needs
        to build a component under the same critical section (so a concurrent
        ``close_process_session`` can't detach the session between the two),
        use :meth:`_ensure_process_session_locked` instead.

        Args:
            plan: The resolved plan; its source selects the credential origin.
            module_name: Becomes the session's active module. None leaves the
                current one in place, for accessors that are not entering a route.

        Returns:
            The process session payload.
        """
        with self._registry.scope_lock(PROCESS_SCOPE):
            return self._ensure_process_session_locked(plan, module_name)

    def _ensure_process_session_locked(
        self, plan: SessionPlan, module_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Same as :meth:`_ensure_process_session`, but the caller already holds the lock.

        Only the shell is built here. Components are built one at a time on
        first access, because the runtimes that land on this path do not
        necessarily hold every credential: a notebook outside a sandbox can
        resolve Earth Engine credentials while having no SEPAL API credentials
        at all, and one missing source must not deny the others.

        Args:
            plan: The resolved plan; its source selects the credential origin.
            module_name: Becomes the session's active module. None leaves the
                current one in place, for accessors that are not entering a route.

        Returns:
            The process session payload.
        """
        session = self._registry.get(PROCESS_SCOPE)
        if session is None:
            sepal_headers = (
                _require_session_id(prime_dev_auth())
                if plan.source is SessionSource.DEV_AUTH
                else None
            )
            session = {
                "source": plan.source,
                "username": sepal_headers.sepal_user.username if sepal_headers else None,
                "sepal_session_id": sepal_headers.session_id if sepal_headers else None,
                "sepal_headers": sepal_headers,
                "raw_headers": None,
                "gee_interface": None,
                "sepal_clients": {},
                "active_module_name": module_name or "default",
                "drive_interface": None,
                "results_dirs_scheduled": set(),
            }
            self._registry.set(session, PROCESS_SCOPE)
            logger.debug(f"Created the process session ({plan.reason})")
        elif module_name is not None:
            session["active_module_name"] = module_name
        return session

    def _require_connection_session(self) -> Dict[str, Any]:
        """Return this connection's session.

        Returns:
            The session payload for the current scope.

        Raises:
            SepalSessionError: No session exists for this connection, or its
                scope id collides with the reserved process scope.
        """
        scope_id = self.get_scope_id()
        if scope_id == PROCESS_SCOPE:
            raise SepalSessionError(
                f"Scope id {scope_id!r} collides with the reserved process scope; "
                "refusing to serve a per-connection runtime from the process session."
            )
        session = self._registry.get(scope_id)
        if session is None:
            raise SepalSessionError(
                f"No SEPAL session exists for scope {scope_id}. Decorate the Page "
                "component with @with_sepal_sessions."
            )
        return session

    def _process_gee_interface(self, session: Dict[str, Any]) -> GEEInterface:
        """Build, once, the process session's GEE interface.

        The caller holds the process scope lock.

        Args:
            session: The process session payload.

        Returns:
            The interface: from the developer login when one is in use, and
            otherwise from the machine's own Earth Engine credentials -- which
            topology has already established belong to a single user.
        """
        if session["gee_interface"] is None:
            sepal_headers = session["sepal_headers"]
            if sepal_headers is not None:
                ee_session = EESession.from_sepal_headers(sepal_headers)
            else:
                # The one place the *session layer* reads the machine's Earth
                # Engine credentials -- not the one place in pysepal:
                # su.init_ee() reads the same file outside it and accepts a
                # service account, see _topology's module docstring. Topology
                # has established these credentials belong to a single user; a
                # service-account key there would not, so refuse it.
                ee_session = EESession.from_default(allow_service_account_file=False)
            session["gee_interface"] = GEEInterface(ee_session)
        return session["gee_interface"]

    def _process_drive_interface(self, session: Dict[str, Any]) -> GDriveInterface:
        """Build, once, the process session's Drive interface.

        The caller holds the process scope lock.

        Args:
            session: The process session payload.

        Returns:
            The interface.
        """
        if session["drive_interface"] is None:
            sepal_headers = session["sepal_headers"]
            session["drive_interface"] = (
                GDriveInterface(sepal_headers=sepal_headers)
                if sepal_headers is not None
                else GDriveInterface()
            )
        return session["drive_interface"]

    def _process_sepal_client(
        self, session: Dict[str, Any], module_name: str
    ) -> Optional[SepalClient]:
        """Build, once, a process-session SepalClient for ``module_name``.

        The caller holds the process scope lock. A client is built only when
        this process has a SEPAL identity of its own: a developer login, or a
        SEPAL sandbox whose files belong to the one user who owns it. Elsewhere
        -- a laptop notebook, a CI script -- there is no such identity, and
        callers keep the local-filesystem behaviour they have today.

        A failure is not cached: it costs an environment read to retry, and a
        sandbox key can appear after the first attempt.

        Args:
            session: The process session payload.
            module_name: The module whose client is required.

        Returns:
            The client, or None when this process has no SEPAL identity, or
            ``SepalClient.create()`` fails for any reason -- missing or
            unreadable credentials. The results directory is created
            separately, off the render path; see :meth:`_schedule_results_dir`.
        """
        if session["sepal_headers"] is None and not is_sepal_sandbox(os.environ):
            return None

        clients = session["sepal_clients"]
        client = clients.get(module_name)
        if client is None:
            try:
                client = SepalClient.create(
                    session_id=session["sepal_session_id"],
                    module_name=module_name,
                    auth_mode="auto" if session["sepal_headers"] else "sandbox_file",
                )
            except PysepalError as exc:
                # No credentials readable for the resolved auth_mode must degrade
                # the sandbox path to "no client", not crash a render: that is
                # what the sandbox exists to preserve
                # (pysepal/solara/components/export_hook.py's local-filesystem
                # fallback).
                logger.debug(f"SEPAL API unavailable; no client for '{module_name}': {exc}")
                return None
            clients[module_name] = client
            self._schedule_results_dir(session, module_name, client)
        return client

    def get_gee_interface(self) -> GEEInterface:
        """Return the GEE interface for the current runtime.

        Returns:
            An app-launcher connection reads the interface
            ``@with_sepal_sessions`` built for it. Every other runtime gets the
            process interface, built on first use.

        Raises:
            SepalSessionError: A per-connection runtime has no session yet.
        """
        plan = _current_plan()
        if _is_scoped_per_connection(plan):
            return self._require_connection_session()["gee_interface"]

        with self._registry.scope_lock(PROCESS_SCOPE):
            session = self._ensure_process_session_locked(plan)
            return self._process_gee_interface(session)

    def get_drive_interface(self) -> GDriveInterface:
        """Return the Drive interface for the current runtime.

        Returns:
            The interface, resolved exactly as :meth:`get_gee_interface`.

        Raises:
            SepalSessionError: A per-connection runtime has no session yet.
        """
        plan = _current_plan()
        if _is_scoped_per_connection(plan):
            return self._require_connection_session()["drive_interface"]

        with self._registry.scope_lock(PROCESS_SCOPE):
            session = self._ensure_process_session_locked(plan)
            return self._process_drive_interface(session)

    def close_process_session(self) -> None:
        """Close and release the process-wide session, if one exists.

        The process session's lifetime is the process, so nothing closes it
        automatically -- ``cleanup_session`` refuses the process scope. This is
        the explicit teardown for embedders and tests. No tombstone is written:
        the next accessor rebuilds.
        """
        with self._registry.scope_lock(PROCESS_SCOPE):
            session = self._registry.pop(PROCESS_SCOPE)
        if session is not None:
            self._close_session(PROCESS_SCOPE, session)

    def get_sepal_client(
        self, module_name: Optional[str] = None, scope_id: Optional[str] = None
    ) -> Optional[SepalClient]:
        """Get a SepalClient for the current runtime's session.

        One session holds one client per module name; without ``module_name``
        you get the client of the route currently rendering.

        Args:
            module_name: The module whose client to return. Defaults to the
                module of the most recently entered ``@with_sepal_sessions``
                component.
            scope_id: Read this scope instead of resolving the current one.

        Returns:
            The client, or None when there is no session for the scope, no
            client for that module, no SEPAL identity in this process, or the
            scope is the reserved process one.
        """
        if scope_id is None:
            plan = _current_plan()
            if not _is_scoped_per_connection(plan):
                with self._registry.scope_lock(PROCESS_SCOPE):
                    process_session = self._ensure_process_session_locked(plan)
                    name = module_name or process_session["active_module_name"]
                    return self._process_sepal_client(process_session, name)
            try:
                scope_id = self.get_scope_id()
            except UnsupportedSolaraRuntimeError:
                # Deliberately swallowed here but not in get_gee_interface/get_drive_interface:
                # this is get_current_sepal_client()'s documented "returns None" contract, not
                # a promise get_current_gee_interface()/_drive_interface() also make. Reachable
                # off the render thread -- a background export task, a callback on
                # GEEInterface's private loop -- where no kernel context resolves.
                return None

        # Same reserved-scope collision as _require_connection_session, but this
        # accessor never raises: a per-connection lookup landing on the process scope
        # gets "no client", not the shared process/dev-auth session's. Outside the
        # resolution branch on purpose -- guarding only the resolved scope would leave
        # the scope_id parameter as a second door into that session.
        if scope_id == PROCESS_SCOPE:
            return None

        session = self._registry.get(scope_id)
        if session is None:
            return None

        name = module_name or session.get("active_module_name")
        return session.get("sepal_clients", {}).get(name)

    def cleanup_session(self, scope_id: str) -> None:
        """Close and forget the session for a scope, then tombstone the scope.

        The tombstone is permanent until ``_reopen_scope`` lifts it -- which
        only happens when ``setup_sessions`` runs again for this same
        ``scope_id``, i.e. a genuine kernel restart, not a reconnect.

        Args:
            scope_id: The scope to clean up.
        """
        if scope_id == PROCESS_SCOPE:
            # A page close ends a connection, not the process. Popping this
            # session would tear down every notebook's interfaces, and the
            # tombstone would then refuse to rebuild them. Explicit teardown is
            # close_process_session().
            logger.debug("Ignoring cleanup for the process scope")
            return

        logger.debug(f"Cleaning up session for scope {scope_id}")

        with self._registry.scope_lock(scope_id):
            session = self._registry.pop(scope_id)
            if session is not None:
                self._close_session(scope_id, session)
            with self._closed_lock:
                if scope_id not in self._closed_scopes:
                    self._closed_scopes.append(scope_id)

        logger.debug(f"Session cleaned up for scope {scope_id}")

    def _close_session(self, scope_id: str, session: Dict[str, Any]) -> None:
        """Release a session's interfaces. Does not touch the registry.

        Args:
            scope_id: The scope the session belonged to, for logging.
            session: The session payload to close.
        """
        gee_interface = session.get("gee_interface")
        if gee_interface is not None:
            try:
                gee_interface.close()
            except Exception as e:
                logger.error(f"Error closing GEE interface for scope {scope_id}: {e}")

        for module_name, client in session.get("sepal_clients", {}).items():
            try:
                client.close()
            except Exception as e:
                logger.error(f"Error closing SepalClient '{module_name}' for scope {scope_id}: {e}")

        if session.get("drive_interface") is not None:
            try:
                session["drive_interface"].close()
            except Exception as e:
                logger.error(f"Error closing Drive interface for scope {scope_id}: {e}")

    def get_session_info(self, scope_id: Optional[str] = None) -> SessionInfo:
        """Return a scope's session status.

        Never raises: a runtime with no resolvable per-connection scope
        reports the reserved process scope id *without reading it* -- an
        unresolvable caller (a background export task, a callback on
        ``GEEInterface``'s private loop) must not see the shared
        process/dev-auth session's identity just because its own scope
        didn't resolve. The same reserved scope passed explicitly is refused
        the same way, so ``scope_id`` can't be used as a second door into
        that session -- the rule :meth:`get_sepal_client` already applies to
        its own ``scope_id`` parameter. A scope with no session reports a
        not-ready :class:`~pysepal.solara.session_info.SessionInfo` carrying
        only its scope id, so admin and debug UI render anywhere.

        Args:
            scope_id: The scope to report on. If None, uses the current one.

        Returns:
            The scope's session status.
        """
        if scope_id is None:
            try:
                scope_id = self.get_scope_id()
            except UnsupportedSolaraRuntimeError:
                return SessionInfo(scope_id=PROCESS_SCOPE)

        # Same reserved-scope collision as get_sepal_client: outside the resolution
        # branch on purpose, so an explicit scope_id=PROCESS_SCOPE doesn't become a
        # second door into the shared process/dev-auth session's identity.
        if scope_id == PROCESS_SCOPE:
            return SessionInfo(scope_id=PROCESS_SCOPE)

        return self._session_info_for(scope_id)

    def _session_info_for(self, scope_id: str) -> SessionInfo:
        """Read one scope's session status straight from the registry.

        No reserved-scope guard: callers must already know ``scope_id`` is
        safe to read. :meth:`get_session_info` is the guarded, caller-facing
        accessor and calls this after its check; :meth:`sessions_overview`
        calls it directly for every id :meth:`session_scope_ids` enumerates --
        those come from the registry's own keys, never from a caller, so the
        guard that refuses a caller-supplied ``PROCESS_SCOPE`` does not apply.

        Under the scope lock: the session dict is live, and ``_ensure_sepal_client``
        mutates ``sepal_clients`` under that same lock on another connection's
        render thread. ``sorted(clients)`` iterates it, so an unlocked read can
        raise ``RuntimeError: dictionary changed size during iteration`` -- and
        the milder outcome, a ``SessionInfo`` whose fields come from either side
        of a concurrent write, is a lying admin panel rather than a crash.
        Holding it for the whole build is what makes the snapshot coherent.

        Cheap to hold: everything below is dict reads, and the writers that take
        this lock no longer do network I/O inside it (``SepalClient.create()`` is
        pure since pysepal-api 0.3.0, and the results directory is created off
        the render path).

        Args:
            scope_id: The scope to read.

        Returns:
            The scope's session status.
        """
        with self._registry.scope_lock(scope_id):
            session = self._registry.get(scope_id)
            if session is None:
                return SessionInfo(scope_id=scope_id)

            gee_interface = session.get("gee_interface")
            clients = session.get("sepal_clients", {})
            return SessionInfo(
                scope_id=scope_id,
                username=session.get("username"),
                has_gee_interface=gee_interface is not None,
                has_sepal_client=bool(clients),
                has_drive_interface=session.get("drive_interface") is not None,
                active_module_name=session.get("active_module_name"),
                module_names=tuple(sorted(clients)),
                session_ready=gee_interface is not None,
            )

    def session_scope_ids(self) -> Tuple[str, ...]:
        """Return every scope currently holding a session.

        Returns:
            A snapshot tuple. The private session dicts are never handed out;
            use :meth:`sessions_overview` to read them all -- :meth:`get_session_info`
            refuses the reserved process scope, which this tuple can contain.
        """
        return self._registry.scope_ids()

    def sessions_overview(self) -> SessionsOverview:
        """Return every session the process holds, including the process one.

        Reads each id from :meth:`session_scope_ids` through
        :meth:`_session_info_for`, not the guarded :meth:`get_session_info`:
        an enumerated scope id was never caller-supplied, so the reserved-scope
        guard doesn't apply here. Under PROCESS/DEV_AUTH topology the process
        session is the process's only session -- hiding it from this overview
        would make it lie about how many sessions exist.

        Returns:
            Every scope's session status, unfiltered.
        """
        return SessionsOverview(
            sessions=tuple(self._session_info_for(s) for s in self.session_scope_ids())
        )


def setup_sessions() -> Callable:
    """Set up sessions management for Solara applications.

    This function should be called with the @solara.lab.on_kernel_start decorator
    to automatically manage GEE, Drive, and Sepal sessions for your application.
    Also lifts this kernel's tombstone, if any: solara's hot-reload restarts a
    kernel in place, re-running ``on_kernel_start`` for the same kernel id right
    after the close callbacks tombstoned it.

    Returns:
        Cleanup function to be called when kernel shuts down.
    """
    session_manager = SessionManager()
    scope_id = session_manager.get_scope_id()
    session_manager._reopen_scope(scope_id)

    logger.debug(f"Setting up sepal sessions for scope {scope_id}")

    # Return cleanup function
    def cleanup():
        session_manager.cleanup_session(scope_id)
        clear_scoped_state(scope_id)

    return cleanup
