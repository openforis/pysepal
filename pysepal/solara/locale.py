"""Scope-keyed locale state and Solara hooks."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import solara
from traitlets import HasTraits, Unicode

from pysepal._ui_state import get_scoped_state


def match_offered_locale(candidate: str, offered: Iterable[str]) -> str:
    """Return the code from ``offered`` that best matches ``candidate``.

    Order: exact match, bare primary subtag if offered, then the first offered
    variant sharing the primary subtag. ``navigator.language`` reports
    ``es-CL`` where an app ships ``es``, and a catalog may ship ``pt-BR``
    where the browser reports ``pt``; both must resolve rather than fall
    through to English.

    Args:
        candidate: The code to match, in IETF BCP 47.
        offered: The codes to match against, in preference order.

    Returns:
        The matching code, or ``""`` so callers can try their next source.
    """
    if not candidate:
        return ""
    offered = list(offered)
    if candidate in offered:
        return candidate
    primary = candidate.split("-")[0]
    if primary in offered:
        return primary
    return next((code for code in offered if code.split("-")[0] == primary), "")


def describe_offered_locales(
    offered: Iterable[str], catalog: Iterable[Dict[str, str]]
) -> List[Dict[str, str]]:
    """Pair each offered locale code with a display name and flag.

    ``offered`` comes from the app's message folders and is authoritative:
    every code is returned, because a catalog the app ships must be
    selectable. ``catalog`` only supplies presentation, matched through
    :func:`match_offered_locale`, so a bare ``es`` borrows the name and flag
    of ``es-ES`` while keeping ``es`` as its value -- the value is a folder
    name that :class:`~pysepal.translator.Translator` has to be able to find.

    Args:
        offered: Locale codes the app has catalogs for.
        catalog: Display records, each with ``code``, ``name`` and ``flag``.

    Returns:
        One record per offered code, sorted by display name.
    """
    by_code = {record["code"]: record for record in catalog}
    described = []
    for code in offered:
        match = by_code.get(match_offered_locale(code, by_code))
        described.append(
            {
                "code": code,
                "name": match["name"] if match else code,
                "flag": match["flag"] if match else "",
            }
        )
    return sorted(described, key=lambda record: record["name"])


class LocaleState(HasTraits):
    """Resolved locale code, keyed by runtime scope."""

    locale = Unicode("en")

    def __init__(self, locale: str = "en", **kwargs):
        """Initialize with an initial resolved locale code."""
        super().__init__(**kwargs)
        self.set_locale(locale)

    def set_locale(self, locale: str) -> None:
        """Update the resolved locale; an empty value coerces to ``"en"``."""
        self.locale = locale or "en"


def get_current_locale_state() -> LocaleState:
    """Return the locale state for the current runtime scope.

    Locale is UI state, not session state: it is keyed by the runtime scope
    and created on first access, so a Solara connection, a Voila page, plain
    Jupyter, a script and pytest all get a real ``LocaleState``. There is no
    session lookup and no credential in this path, and this function never
    raises.

    A fresh state starts at ``"en"`` and is never seeded from
    ``~/.sepal-ui-config``, which is process-global and therefore made one
    machine's language decide what every connection rendered in (issue #977).
    The real preference is resolved in the browser by ``LocaleSelect.vue``
    and pushed in from there.
    """
    return get_scoped_state("locale_state", LocaleState)


def resolve_locale_state(locale_state: Optional[LocaleState] = None) -> LocaleState:
    """Return a usable LocaleState.

    Precedence: an explicit ``locale_state``, else the current scope's, which
    :func:`get_current_locale_state` creates on demand for every runtime
    including scripts and pytest.

    Args:
        locale_state: An explicit state to use instead of the scope's.

    Returns:
        The locale state to render with.
    """
    return locale_state if locale_state is not None else get_current_locale_state()


def use_locale(locale_state: Optional[LocaleState] = None) -> str:
    """Reactively return the resolved locale code for the current scope."""
    locale_state = locale_state or get_current_locale_state()
    locale, set_locale = solara.use_state(locale_state.locale)

    def _observe():
        def handler(change):
            set_locale(change["new"])

        locale_state.observe(handler, "locale")
        return lambda: locale_state.unobserve(handler, "locale")

    solara.use_effect(_observe, [id(locale_state)])
    return locale
