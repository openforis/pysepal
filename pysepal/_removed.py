"""What an old import gets for a name or module pysepal 5 removed: a message saying what replaces it."""

import sys
from importlib.abc import MetaPathFinder
from typing import Callable, Dict, NoReturn

GUIDE = "https://github.com/openforis/pysepal/blob/main/docs/guides/migrating-to-pysepal-5.md"


def message(path: str, cause: str, replacement: str) -> str:
    """The message for a removed name or module."""
    return (
        f"{path} was removed in pysepal 5.0 with {cause}; "
        f'use {replacement} or pin "pysepal<5". See {GUIDE}'
    )


class _RemovedFinder(MetaPathFinder):
    """Raise the message for ``import package.name`` and ``from package import name``.

    A package's ``__getattr__`` is not enough: ``import`` never calls it, and
    ``from package import name`` catches its ``AttributeError``, tries
    ``package.name`` as a submodule and reports a bare "cannot import name".
    Last on ``sys.meta_path``, this finder only sees imports nothing else found.
    """

    def __init__(self) -> None:
        self.messages: Dict[str, str] = {}

    def find_spec(self, fullname, path=None, target=None):
        text = self.messages.get(fullname)
        if text is not None:
            raise ImportError(text, name=fullname)
        return None


_FINDER = _RemovedFinder()
sys.meta_path.append(_FINDER)


def removed(package: str, causes: Dict[str, Dict[str, str]]) -> Callable[[str], NoReturn]:
    """Register what ``package`` removed and return the package's ``__getattr__``.

    Args:
        package: the package name, ``__name__`` of its ``__init__``.
        causes: for each change that removed names, the removed names (attributes
            or modules) and what replaces each one.
    """
    messages = {
        name: message(f"{package}.{name}", cause, replacement)
        for cause, replacements in causes.items()
        for name, replacement in replacements.items()
    }
    _FINDER.messages.update({f"{package}.{name}": text for name, text in messages.items()})

    def __getattr__(name: str) -> NoReturn:
        if name in messages:
            raise AttributeError(messages[name])
        raise AttributeError(f"module {package!r} has no attribute {name!r}")

    return __getattr__
