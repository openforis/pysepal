"""The demo's catalogue, in its own module so every context can reach it.

``gallery.py`` puts each demo directory on ``sys.path``, so these module names are
the demo's namespace: keep them prefixed and never call one ``message``.
"""

from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent / "message")
msg = messages.msg
