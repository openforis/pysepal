"""pysepal's own message catalogue.

Two accessors read the same JSON files during the migration:

.. code-block::

    from pysepal.message import ms    # legacy Translator, frozen at import
    from pysepal.message import msg   # follows the connection's locale

``msg`` is the one to use. ``ms`` stays until every internal site has moved,
because consumer modules and the remaining widgets still read it.
"""

from pathlib import Path

from pysepal.i18n import catalog
from pysepal.translator import Translator

_HERE = Path(__file__).parent

ms = Translator(_HERE)

messages = catalog(_HERE)
msg = messages.msg
