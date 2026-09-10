"""The locale code, as one reactive value per pysepal runtime scope.

This is the only state in the i18n system. A catalogue, a rendered message and
the language selector's trait are all derived from it, which is what removes the
need to keep two representations in step.

It lives here rather than in :mod:`pysepal.solara` so that a catalogue can
resolve a locale without importing session management and notifications.
"""

import solara

from pysepal._locale import normalize_locale
from pysepal._ui_state import get_scoped_state
from pysepal.i18n.loading import ENGLISH

_SCOPE_KEY = "i18n_locale"


def _locale_ref() -> solara.Reactive[str]:
    """Return this runtime scope's locale Reactive.

    Internal. Application code calls :func:`current_locale` and
    :func:`set_locale`; only the language selector's private binder needs the
    Reactive itself, to subscribe to it and to peek without subscribing.

    Returns:
        The scope's Reactive, created on first access.
    """
    return get_scoped_state(_SCOPE_KEY, lambda: solara.reactive(ENGLISH))


def _store(ref: solara.Reactive[str], code: str) -> None:
    """Normalise ``code`` and write it into ``ref``.

    The one place ``normalize_locale(code) or ENGLISH`` is spelled, so
    :func:`set_locale` and the language selector's binder -- which writes
    through this too -- can never drift apart on what an empty or malformed
    code becomes.

    Args:
        ref: The Reactive to write into.
        code: A locale code in any casing or separator style.
    """
    ref.value = normalize_locale(code) or ENGLISH


def current_locale() -> str:
    """Return the locale code this runtime scope renders in.

    Reading subscribes when a render is in progress, so a component that calls
    this -- directly or through an ordinary helper -- re-renders when the
    language changes. Outside a render it is a plain read and never raises.

    Returns:
        A normalised IETF BCP 47 code; ``"en"`` until something sets one.
    """
    return _locale_ref().value


def set_locale(code: str) -> None:
    """Set the locale code for this runtime scope.

    Cannot seed a startup default. A mounted ``LocaleSelect`` always runs its
    own browser resolution on first mount and writes the result back here,
    overwriting anything set before that. Call this after the first mount
    instead -- from a settings action, say -- where it takes effect and
    survives later remounts.

    Args:
        code: An IETF BCP 47 code in any casing or separator style. It is
            normalised before storing, and an empty code means English, so a
            failed browser resolution degrades rather than storing ``""``.
    """
    _store(_locale_ref(), code)
