"""One scope-keyed registry for every per-connection object pysepal holds.

UI state, the notification bus and ``SessionManager`` all key state by scope
id. They used to disagree about what "no runtime" means -- one fell back to
the process scope, one raised, one did both depending on the method. There is
one default now, and it is the topology rule's: no per-connection runtime
*is* the process scope. A registry over a credential store configures the
strict resolver instead -- there, a wrong scope is a cross-user leak, not a
shared bucket.

Two policies, split deliberately. *Resolution* is configured per instance, via
``resolver=``. *Lifetime* is not configurable here at all -- it stays the
caller's, because the three consumers disagree and always will:

- plain drop -- ``ui_state`` removes a scope's state on the first release;
- refcount -- ``notifications.bus`` keeps a bus until the last mount releases it;
- tombstone -- ``SessionManager`` remembers a closed scope so it cannot be
  resurrected.

This registry therefore has no opinion on *when* a value goes, only on how it
is keyed and locked. A consumer layers its own policy on
:meth:`ScopeRegistry.scope_lock` and drives it with the plain accessors --
folding those three policies back in here as flags would recreate the
per-caller tangle this class exists to remove.
"""

import logging
import threading
from typing import Callable, Dict, Generic, Optional, Tuple, TypeVar

from pysepal._runtime_context import current_scope_id

logger = logging.getLogger("sepalui.solara.scope_registry")

T = TypeVar("T")


class ScopeRegistry(Generic[T]):
    """A scope-id-keyed store with one locking discipline and a configurable resolver.

    Args:
        name: Registry name; used in log lines only.
        resolver: How to resolve the current scope when a call omits
            ``scope_id``. Defaults to the lenient
            :func:`~pysepal._runtime_context.current_scope_id`, which
            falls back to :data:`~pysepal._runtime_context.PROCESS_SCOPE`.
            Pass the raising
            :func:`~pysepal._runtime_context.resolve_scope_id` for a
            registry where an unresolved scope must be an error, not a
            silent shared bucket -- e.g. a credential store.
    """

    def __init__(self, name: str, resolver: Optional[Callable[[], str]] = None) -> None:
        """Build an empty registry."""
        self._name = name
        self._resolver = resolver
        self._values: Dict[str, T] = {}
        self._scope_locks: Dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def resolve(self, scope_id: Optional[str] = None) -> str:
        """Return the scope to act on.

        With no explicit ``scope_id``, this runs the registry's resolver --
        the lenient default, or the strict one it was constructed with (see
        the class docstring). A strict resolver's exception propagates as-is.

        Args:
            scope_id: An explicit scope, or None to resolve one.

        Returns:
            The scope id, never None.
        """
        if scope_id is not None:
            return scope_id
        resolver = self._resolver if self._resolver is not None else current_scope_id
        return resolver()

    def scope_lock(self, scope_id: Optional[str] = None) -> threading.Lock:
        """Return the lock guarding one scope.

        Per scope on purpose: building a scope's value can perform blocking
        network calls, and one global lock would serialise every user's first
        render in a multi-user container.

        Never removed once handed out: a thread that fetched this lock but has
        not yet acquired it could otherwise hold an orphan while a fresh lock
        is handed out for the same scope, letting two threads into the critical
        section at once. The leaked ``Lock`` objects are negligible.

        Args:
            scope_id: Scope to lock; defaults to the current one.

        Returns:
            That scope's lock.
        """
        scope = self.resolve(scope_id)
        with self._registry_lock:
            return self._scope_locks.setdefault(scope, threading.Lock())

    def get(self, scope_id: Optional[str] = None) -> Optional[T]:
        """Return a scope's value, or None.

        Args:
            scope_id: Scope to read; defaults to the current one.

        Returns:
            The stored value, or None.
        """
        scope = self.resolve(scope_id)
        with self._registry_lock:
            return self._values.get(scope)

    def set(self, value: T, scope_id: Optional[str] = None) -> None:
        """Store a scope's value, replacing any previous one.

        Args:
            value: The value to store.
            scope_id: Scope to write; defaults to the current one.
        """
        scope = self.resolve(scope_id)
        with self._registry_lock:
            self._values[scope] = value

    def get_or_create(self, factory: Callable[[], T], scope_id: Optional[str] = None) -> T:
        """Return a scope's value, building it on miss.

        ``factory`` runs while the registry lock is held, so it must be cheap
        and must not re-enter this registry. Expensive construction belongs
        under :meth:`scope_lock` with an explicit :meth:`get` / :meth:`set`.

        Args:
            factory: Zero-argument callable building the value on first access.
            scope_id: Scope to read; defaults to the current one.

        Returns:
            The stored value.
        """
        scope = self.resolve(scope_id)
        with self._registry_lock:
            if scope not in self._values:
                self._values[scope] = factory()
                logger.debug(f"Created {self._name} for scope {scope}")
            return self._values[scope]

    def pop(self, scope_id: Optional[str] = None) -> Optional[T]:
        """Remove and return a scope's value.

        Args:
            scope_id: Scope to drop; defaults to the current one.

        Returns:
            The removed value, or None when there was none.
        """
        scope = self.resolve(scope_id)
        with self._registry_lock:
            value = self._values.pop(scope, None)
        if value is not None:
            logger.debug(f"Dropped {self._name} for scope {scope}")
        return value

    def scope_ids(self) -> Tuple[str, ...]:
        """Return every scope currently holding a value.

        Returns:
            A snapshot tuple; mutating the registry does not affect it.
        """
        with self._registry_lock:
            return tuple(self._values)

    def clear(self) -> None:
        """Drop every value. Scope locks are deliberately kept."""
        with self._registry_lock:
            self._values.clear()
