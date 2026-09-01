"""The demo app's message catalogue.

Bound once at import. ``msg`` follows the connection's locale wherever it is
called -- in a component, in a helper, in an event handler -- because it reads
the scope's locale rather than taking one.

Accessed via ``from component.message import messages, msg``.
"""

from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent)
msg = messages.msg
