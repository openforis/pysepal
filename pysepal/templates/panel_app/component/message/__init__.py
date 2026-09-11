"""Application messages: ``from component.message import messages``."""

from pathlib import Path

from pysepal.i18n import catalog

messages = catalog(Path(__file__).parent)
