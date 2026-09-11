"""Message catalogues for pysepal applications.

A module binds its own directory of ``messages/<locale>/*.json`` and gets one
lookup back. There is no global registration, so pysepal's own strings and an
application's strings never collide.

    from pathlib import Path
    from pysepal.i18n import catalog

    messages = catalog(Path(__file__).parent)

Call ``messages.msg(...)`` for one message in the runtime scope's locale,
which :func:`current_locale` and :func:`set_locale` read and change.
"""

from pysepal.i18n.binding import catalog
from pysepal.i18n.errors import CatalogError, MessageFormatError, MissingMessageError
from pysepal.i18n.locale_store import current_locale, set_locale
from pysepal.i18n.problems import CatalogProblem

__all__ = [
    "CatalogError",
    "CatalogProblem",
    "MessageFormatError",
    "MissingMessageError",
    "catalog",
    "current_locale",
    "set_locale",
]
