"""Turn one nested message document into flat dotted keys.

Lookup is then an ordinary dict access, which retires the whole protected-key
problem: a message named ``get``, ``items`` or ``keys`` is just a string.
"""

from typing import Any, Dict, FrozenSet, Mapping, Sequence, Set, Tuple

from pysepal.i18n.errors import CatalogError
from pysepal.i18n.formatting import placeholders
from pysepal.i18n.plurals import PLURAL_CATEGORIES


def flatten_document(
    document: Any, *, locale: str, source: str, authoritative: bool
) -> Tuple[Dict[str, str], FrozenSet[str]]:
    """Return the flat messages and plural base keys of one JSON document.

    Args:
        document: The parsed JSON value; it must be an object.
        locale: The locale the document belongs to, used in error messages.
        source: The file name, used in error messages.
        authoritative: True for English, which defines message identities and
            named arguments. Translations may use their own plural categories.

    Returns:
        A ``(messages, plural_keys)`` pair. ``messages`` maps a dotted key to a
        message; a plural node contributes one key per category, for example
        ``chips.models.one``. ``plural_keys`` holds those nodes' base keys, for
        example ``chips.models``.

    Raises:
        CatalogError: The document is not an object, a key segment contains a
            dot, or a leaf is not a string. In English only: a plural node
            does not hold exactly the string leaves named in
            ``one`` and ``other``, a leaf uses unsupported template syntax,
            or a leaf uses a positional placeholder
            (``{}`` or ``{0}``).
    """
    if not isinstance(document, dict):
        raise CatalogError(f"{locale}/{source}: the document must be a JSON object")

    messages: Dict[str, str] = {}
    plural_keys: Set[str] = set()
    _walk(
        document,
        (),
        messages,
        plural_keys,
        locale=locale,
        source=source,
        authoritative=authoritative,
    )
    if authoritative:
        for key, message in messages.items():
            _refuse_malformed_template(key, message, locale=locale, source=source)
            _refuse_positional_placeholder(key, message, locale=locale, source=source)
    return messages, frozenset(plural_keys)


def _refuse_malformed_template(key: str, message: str, *, locale: str, source: str) -> None:
    """Require a valid English fallback before any message can render."""
    if placeholders(message) is None:
        raise CatalogError(
            f"{locale}/{source}: '{key}' uses unsupported message template syntax; "
            "use named placeholders and escape literal braces"
        )


def _refuse_positional_placeholder(key: str, message: str, *, locale: str, source: str) -> None:
    """Raise when ``message`` uses a positional placeholder (``{}`` or ``{0}``).

    English is rendered with ``**values`` only (see ``BoundCatalog._resolve``),
    so a positional placeholder can never receive a value and always raises at
    render. That makes it a structural error in the author's own catalogue,
    caught here rather than on a user's screen. A translator cannot reorder a
    positional placeholder safely for a language whose word order differs, so
    this is refused rather than supported: named placeholders are the only
    sanctioned form. A malformed template cannot reach here:
    :func:`_refuse_malformed_template` runs first.
    """
    names = placeholders(message)
    if names is not None and any(name.isdigit() for name in names):
        raise CatalogError(
            f"{locale}/{source}: '{key}' uses a positional placeholder "
            "('{}' or '{0}'); give it a name instead, e.g. '{count}'"
        )


def _walk(
    node: Mapping[str, Any],
    path: Sequence[str],
    messages: Dict[str, str],
    plural_keys: Set[str],
    *,
    locale: str,
    source: str,
    authoritative: bool,
) -> None:
    """Add one object's leaves to ``messages``, recursing into its children."""
    where = f"{locale}/{source}"
    if any(category in node for category in PLURAL_CATEGORIES):
        if not path:
            raise CatalogError(f"{where}: a plural node cannot sit at the root")
        base = ".".join(path)
        if authoritative and (
            set(node) != {"one", "other"}
            or not all(isinstance(node[category], str) for category in ("one", "other"))
        ):
            raise CatalogError(
                f"{where}: the plural node {base} must hold exactly the string leaves " "one, other"
            )
        if authoritative:
            one = placeholders(node["one"])
            other = placeholders(node["other"])
            if one is not None and other is not None and one - {"count"} != other - {"count"}:
                raise CatalogError(
                    f"{where}: plural forms of {base} must use the same named arguments apart from count"
                )
        plural_keys.add(base)
        for category, leaf in node.items():
            if "." in category:
                raise CatalogError(
                    f"{where}: the key segment {category!r} contains a dot, which would "
                    "make the flat key ambiguous"
                )
            if not isinstance(leaf, str):
                raise CatalogError(
                    f"{where}: {base}.{category} is a {type(leaf).__name__}; "
                    "every leaf must be a string"
                )
            messages[f"{base}.{category}"] = leaf
        return

    for segment, value in node.items():
        if "." in segment:
            raise CatalogError(
                f"{where}: the key segment {segment!r} contains a dot, which would "
                "make the flat key ambiguous"
            )
        child = (*path, segment)
        if isinstance(value, dict):
            _walk(
                value,
                child,
                messages,
                plural_keys,
                locale=locale,
                source=source,
                authoritative=authoritative,
            )
        elif isinstance(value, str):
            messages[".".join(child)] = value
        else:
            raise CatalogError(
                f"{where}: {'.'.join(child)} is a {type(value).__name__}; "
                "every leaf must be a string"
            )
