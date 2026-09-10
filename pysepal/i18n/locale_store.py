"""The locale as a Solara reactive, isolated by Solara's kernel context.

Outside a Solara context, reads and writes use the process default. Workers
should return results or message keys to the UI context for translation.
Keeping the value here avoids importing pysepal session management.
"""

import solara

from pysepal._locale import normalize_locale
from pysepal.i18n.loading import ENGLISH

_locale = solara.reactive(ENGLISH)


def current_locale() -> str:
    """Return the current kernel's locale, subscribing during a render.

    Returns:
        A normalised IETF BCP 47 code; ``"en"`` until something sets one.
        Outside a Solara context, return the process default.
    """
    return _locale.value


def set_locale(code: str) -> None:
    """Set the locale for the current Solara kernel, or the process default.

    A selector's first browser mount resolves localStorage, navigator.language,
    then English. That resolution replaces any earlier Python value. Later
    calls update the mounted selector and survive its remounts.

    Args:
        code: A locale code in any casing or separator style. Empty means English.
    """
    _locale.value = normalize_locale(code) or ENGLISH
