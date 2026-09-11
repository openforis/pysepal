"""Runtime scope identity for pysepal Solara, Voila and notebook state.

A *scope id* names the runtime that owns a session, a UI state or a
notification bus: a Solara-server virtual kernel, a Voila or Jupyter kernel,
or the process itself when there is no per-connection runtime at all. One
name, one resolver -- ``kernel_id`` and ``runtime_id`` were the same value
under two other names.
"""

import solara.scope

if not hasattr(solara.scope, "get_kernel_id"):
    raise ImportError(
        "solara.scope.get_kernel_id is missing. pysepal resolves every "
        "per-connection scope through it, and its absence is indistinguishable "
        "from 'this runtime has no kernel': UI state, theme and the "
        "notification bus would silently collapse onto one shared process "
        "scope for every connection. Install a solara that provides it "
        "(pysepal pins solara>=1.60,<2)."
    )

PROCESS_SCOPE = "process"
"Scope id used when no per-connection runtime can be resolved."


class UnsupportedSolaraRuntimeError(RuntimeError):
    """Raised when pysepal cannot resolve a per-connection app runtime."""


def resolve_scope_id() -> str:
    """Return the current per-connection runtime's scope id.

    Thin adapter over Solara's own ``solara.scope.get_kernel_id`` resolver: it
    returns the Solara-server virtual-kernel id and otherwise falls back to the
    active IPython/ipykernel -- covering ``solara run``, Voila (including
    preheated kernels, which start before ``SERVER_SOFTWARE`` is set), and plain
    Jupyter Notebook/Lab. We deliberately do not reimplement that resolution; we
    only translate its failure modes into a typed error.

    Those failure modes are every way an unusual host can shape a kernel, and
    all five are reachable -- the ipython fallback ends in
    ``re.search(regex, kernel.config["IPKernelApp"]["connection_file"]).group(1)``:

    - ``RuntimeError`` -- no kernel at all;
    - ``AttributeError`` -- a connection filename the regex cannot parse, so
      ``re.search`` returns None;
    - ``TypeError`` -- no ``connection_file`` key, which a traitlets ``Config``
      auto-vivifies into a ``LazyConfigValue`` rather than raising;
    - ``KeyError`` -- the same absence in a mapping that does not auto-vivify;
    - ``ImportError`` -- solara imports ``solara.server.kernel_context`` and
      ``IPython`` inside the call, and pysepal declares neither.

    An ``ImportError`` from the *symbol itself* being gone cannot reach here:
    the module-level check above turns that into a startup failure, so a solara
    API change never masquerades as a runtime that has no kernel.

    Deliberately not ``Exception``: this resolver is total about *runtime
    shape*, which is not a licence to hide bugs behind a fallback scope.

    Returns:
        The runtime's scope id.

    Raises:
        UnsupportedSolaraRuntimeError: No per-connection runtime is available.
    """
    try:
        return solara.scope.get_kernel_id(ipython_fallback=True)
    except (RuntimeError, AttributeError, TypeError, KeyError, ImportError) as exc:
        raise UnsupportedSolaraRuntimeError(
            "No supported pysepal runtime context is available"
        ) from exc


def current_scope_id() -> str:
    """Return a scope id for the current runtime, always.

    Returns:
        The per-connection runtime's scope id, or :data:`PROCESS_SCOPE` when
        there is none (script, pytest, unsupported kernel).
    """
    try:
        return resolve_scope_id()
    except UnsupportedSolaraRuntimeError:
        return PROCESS_SCOPE
