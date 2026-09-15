"""Read a ``messages/<locale>/*.json`` directory into immutable locale data."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, FrozenSet, Mapping, Optional, Set, Tuple

from pysepal._locale import normalize_locale
from pysepal.i18n.errors import CatalogError
from pysepal.i18n.flatten import flatten_document
from pysepal.i18n.formatting import target_leaf_problem
from pysepal.i18n.plurals import plural_categories

ENGLISH = "en"
"The authoritative locale. It defines every public key and its shape."


@dataclass(frozen=True)
class LocaleData:
    """One locale's flattened catalogue.

    Args:
        code: The directory name this data was read from.
        messages: Dotted key to message. Read-only.
        plural_keys: Base keys of this locale's plural nodes.
    """

    code: str
    messages: Mapping[str, str]
    plural_keys: FrozenSet[str]


def _ships_messages(path: Path) -> bool:
    """A locale is a directory that contains at least one top-level ``*.json``.

    Not recursive: a ``*.json`` sitting in a nested subdirectory does not
    count, matching :func:`load_locale`'s own non-recursive glob. This is
    also what keeps a gitignored ``__pycache__`` out of the language picker,
    with no name-based special case -- the rule is "ships messages", not
    "does not start with an underscore".
    """
    return path.is_dir() and any(path.glob("*.json"))


def discover_locale_codes(folder: Path) -> Tuple[str, ...]:
    """Return the locale codes ``folder`` ships, English first.

    Args:
        folder: The message directory holding one subdirectory per locale.

    Returns:
        ``("en", ...)`` with the remaining codes sorted, so the order does not
        depend on the filesystem.

    Raises:
        CatalogError: There is no readable ``en`` directory that ships at
            least one message file, or two directories normalise to the same
            locale code.
    """
    if not _ships_messages(folder / ENGLISH):
        raise CatalogError(f"{folder}: no readable '{ENGLISH}' directory")

    seen: Dict[str, str] = {}
    for child in sorted(path for path in folder.iterdir() if _ships_messages(path)):
        canonical = normalize_locale(child.name)
        if canonical in seen:
            raise CatalogError(
                f"{folder}: '{seen[canonical]}' and '{child.name}' both normalise to "
                f"'{canonical}'"
            )
        seen[canonical] = child.name

    codes = sorted(seen.values())
    codes.remove(ENGLISH)
    return (ENGLISH, *codes)


def load_locale(folder: Path, code: str) -> LocaleData:
    """Read and merge every JSON file of one locale.

    Args:
        folder: The message directory.
        code: The locale subdirectory name.

    Returns:
        The locale's flattened, read-only data.

    Raises:
        CatalogError: A file cannot be read, is not valid UTF-8, is not valid
            JSON, two files produce the same flat key, or a key is both a
            message and the prefix of another.
    """
    messages: Dict[str, str] = {}
    plural_keys: Set[str] = set()
    origin: Dict[str, str] = {}

    for path in sorted((folder / code).glob("*.json")):
        try:
            # JSON is UTF-8 by specification (RFC 8259): read_text()'s platform
            # default would take cp1252 on Windows, silently breaking every
            # non-ASCII catalogue there even when the file is perfectly correct.
            document = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CatalogError(f"{code}/{path.name}: {exc}") from exc
        except (OSError, UnicodeDecodeError) as exc:
            raise CatalogError(f"{code}/{path.name}: {exc}") from exc

        found, plurals = flatten_document(
            document, locale=code, source=path.name, authoritative=code == ENGLISH
        )
        for key, message in found.items():
            if key in messages:
                raise CatalogError(
                    f"{code}: '{key}' is defined by both {origin[key]} and {path.name}; "
                    "file order would decide the winner"
                )
            messages[key] = message
            origin[key] = path.name
        plural_keys |= plurals

    _refuse_leaf_and_prefix(messages, origin, code)

    if code != ENGLISH:
        # Pontoon exports an untranslated string as "". Dropping it lets English
        # show through, which is what Translator.merge_dict did via
        # delete_empty(); keeping it blanks the widget instead. Applied after the
        # collision checks so a duplicate or leaf/prefix clash still reports.
        messages = {key: text for key, text in messages.items() if text != ""}

    return LocaleData(code, MappingProxyType(messages), frozenset(plural_keys))


def overlay(english: LocaleData, target: LocaleData) -> Mapping[str, str]:
    """Overlay valid translations, leaving missing plural forms unresolved.

    Plural fallback needs the actual count and English rules. Copying English
    forms here would make French zero inherit English's literal "1 model".
    """
    if target.code == ENGLISH:
        return english.messages
    composite = {
        key: message
        for key, message in english.messages.items()
        if key.rpartition(".")[0] not in english.plural_keys
    }
    categories = plural_categories(target.code)
    for key, message in target.messages.items():
        base, _, category = key.rpartition(".")
        if base in english.plural_keys:
            if base not in target.plural_keys or category not in categories:
                continue
        elif key not in composite or key in target.plural_keys:
            continue
        if translation_problem(english, key, message) is None:
            composite[key] = message
    return MappingProxyType(composite)


def translation_problem(english: LocaleData, key: str, message: str) -> Optional[str]:
    """Validate a target leaf against its English message's argument contract."""
    base = key.rpartition(".")[0]
    plural = base in english.plural_keys
    reference = english.messages[f"{base}.other"] if plural else english.messages[key]
    return target_leaf_problem(reference, message, plural=plural)


def _refuse_leaf_and_prefix(
    messages: Mapping[str, str], origin: Mapping[str, str], code: str
) -> None:
    """Raise when one key is both a message and an ancestor of another.

    Names the file behind each side of the collision, so a real multi-file
    catalogue points the editor at where to fix it, not just what collides.
    """
    for key in messages:
        segments = key.split(".")
        for cut in range(1, len(segments)):
            ancestor = ".".join(segments[:cut])
            if ancestor in messages:
                raise CatalogError(
                    f"{code}: '{ancestor}' ({origin[ancestor]}) is both a message and "
                    f"a prefix of '{key}' ({origin[key]})"
                )
