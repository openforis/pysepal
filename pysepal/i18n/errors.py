"""The three ways a message lookup can fail."""


class CatalogError(Exception):
    """A catalogue cannot be loaded: the module author's own structure is wrong.

    Always raised, in strict and non-strict catalogues alike. Strictness
    governs missing keys only.
    """


class MissingMessageError(LookupError):
    """A strict catalogue was asked for a key English does not define.

    ``LookupError`` rather than ``KeyError``: ``KeyError.__str__`` quotes its
    argument, which would turn a written sentence into a quoted fragment.
    """


class MessageFormatError(Exception):
    """A message was resolved but a placeholder value was not supplied."""
