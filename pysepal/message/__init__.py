"""pysepal's own message catalogue.

Two accessors read the same JSON files during the migration:

.. code-block::

    from pysepal.message import ms    # legacy Translator, frozen at import
    from pysepal.message import msg   # follows the connection's locale

``msg`` is the one to use. ``ms`` stays until every internal site has moved,
because consumer modules and the remaining widgets still read it.
"""

from pathlib import Path
from typing import Any

from pysepal.translator import Translator

_HERE = Path(__file__).parent

ms = Translator(_HERE)

_catalogue = None


def msg(key: str, /, **values: Any) -> str:
    """Return one message, in the locale of the current runtime scope.

    Args:
        key: A dotted key into the catalogue, e.g. ``"aoi_sel.custom"``.
        values: Named placeholder values the message needs.

    Returns:
        The rendered message.
    """
    # Bound on first use, not at import: pysepal.i18n reaches solara, and
    # `import pysepal` must touch no home directory -- see
    # tests/test_meta_no_home_write.py.
    global _catalogue
    if _catalogue is None:
        from pysepal.i18n import catalog

        _catalogue = catalog(_HERE)
    return _catalogue.msg(key, **values)
