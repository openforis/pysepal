"""Bind a message directory, and resolve one message from it.

Two cache layers with different identities. Parsed locale data is keyed by
resolved path and matched directory code; the bound facade is keyed by resolved
path and strictness. Strictness is therefore never inherited from whichever
caller happened to bind a path first, while both facades still share one copy
of the parsed data.

Editing a JSON file needs a kernel restart, which Solara's reload already
performs. That is deliberate: mtime polling would put hidden I/O on the render
path.
"""

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Mapping, Set, Tuple, Union

from pysepal._locale import match_offered_locale
from pysepal.i18n.errors import CatalogError, MessageFormatError, MissingMessageError
from pysepal.i18n.loading import (
    ENGLISH,
    LocaleData,
    discover_locale_codes,
    load_locale,
    overlay,
)
from pysepal.i18n.locale_store import current_locale
from pysepal.i18n.plurals import select_plural_category
from pysepal.i18n.problems import CatalogProblem, compare_locale

logger = logging.getLogger("sepalui.i18n")

_LOCK = threading.Lock()
_PARSED: Dict[Tuple[Path, str], LocaleData] = {}
_COMPOSITE: Dict[Tuple[Path, str], Mapping[str, str]] = {}
_FACADES: Dict[Tuple[Path, bool], "BoundCatalog"] = {}

MISSING_MARKER = "⟦{key}⟧"
"What a non-strict catalogue renders in place of a key it does not have."


def catalog(folder: Union[str, Path], *, strict: bool = True) -> "BoundCatalog":
    """Bind a ``messages/<locale>/*.json`` directory.

    English is loaded and validated now, so a structural mistake fails when the
    application's message module is imported rather than at the first render.

    Args:
        folder: The message directory, usually ``Path(__file__).parent``.
        strict: Whether a key English does not define raises. When False, the
            lookup logs once and renders :data:`MISSING_MARKER` instead.

    Returns:
        The one catalogue bound to that path at that strictness.

    Raises:
        CatalogError: The directory or the English catalogue is malformed.
    """
    resolved = Path(folder).resolve()
    with _LOCK:
        cached = _FACADES.get((resolved, strict))
    if cached is not None:
        return cached

    bound = BoundCatalog(resolved, strict=strict)
    with _LOCK:
        return _FACADES.setdefault((resolved, strict), bound)


class BoundCatalog:
    """One message directory, resolved per locale.

    Build it through :func:`catalog`, which caches one instance per path and
    strictness. Constructing it directly bypasses that cache.
    """

    def __init__(self, folder: Path, *, strict: bool) -> None:
        """Load and validate English, and record what the directory ships."""
        self._folder = folder
        self._strict = strict
        self._codes = discover_locale_codes(folder)
        self._english = _parsed(folder, ENGLISH)
        self._warned: Set[Tuple[str, str]] = set()
        self._unreadable: Set[str] = set()

    def msg(self, key: str, /, **values: Any) -> str:
        """Return one message, rendered in this runtime scope's locale.

        This is the only lookup. Reading the locale subscribes when a render is
        in progress, so a component that calls this -- directly, or through an
        ordinary helper on the same call stack -- re-renders when the language
        changes. Event handlers in the same Solara context read that locale
        too. A worker without the context reads the process default; return
        results or message keys to the UI context for translation instead.

        ``key`` is positional-only, so a message may carry a ``{key}``
        placeholder passed as ``key=...``.

        Args:
            key: The dotted message key. May be computed, e.g. from a registry
                table that holds keys as data.
            **values: Placeholder values. ``count`` also selects a plural form
                when ``key`` names a plural node in English.

        Returns:
            The formatted message.

        Raises:
            MissingMessageError: A strict catalogue does not define ``key``.
            MessageFormatError: A placeholder value was not supplied, ``count``
                was omitted for a plural key, or the template cannot render.
        """
        return self._resolve(current_locale(), key, **values)

    def available_locales(self) -> Tuple[str, ...]:
        """Return the codes this directory ships, English first.

        Returns:
            The directory names, for ``MapApp(locales=...)``.
        """
        return self._codes

    def check(self) -> Tuple[CatalogProblem, ...]:
        """Return every translator problem in every shipped locale.

        Returns:
            A deterministically sorted tuple, empty when the catalogue is
            clean. This method never raises: English is validated once at
            bind time, but a target locale is read lazily, so a load failure
            -- bad JSON, a duplicate key, a leaf that is also a prefix, and
            the rest of :func:`~pysepal.i18n.loading.load_locale`'s hard
            errors -- surfaces here as one ``unreadable_locale`` problem
            instead of aborting the loop, so one broken locale cannot hide
            every other locale's problems too.
        """
        problems = []
        for code in self._codes:
            if code == ENGLISH:
                continue
            try:
                target = _parsed(self._folder, code)
            except CatalogError as exc:
                problems.append(CatalogProblem("unreadable_locale", code, "", str(exc)))
                continue
            problems.extend(compare_locale(self._english, target))
        return tuple(
            sorted(
                problems,
                key=lambda problem: (problem.code, problem.locale, problem.key),
            )
        )

    def _resolve(self, locale: str, key: str, /, **values: Any) -> str:
        """Render a message, selecting plural fallback with English rules."""
        if key not in self._english.messages and key not in self._english.plural_keys:
            return self._missing(locale, key)

        matched = match_offered_locale(locale, self._codes) or ENGLISH
        lookup = english_lookup = key
        if key in self._english.plural_keys:
            if "count" not in values:
                raise MessageFormatError(
                    f"{self._folder}: '{key}' is a plural message and needs a count"
                )
            try:
                lookup = f"{key}.{select_plural_category(matched, values['count'])}"
                english_lookup = f"{key}.{select_plural_category(ENGLISH, values['count'])}"
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise MessageFormatError(f"{self._folder}: '{key}': invalid count: {exc}") from exc

        english = self._english.messages[english_lookup]
        template = self._messages_for(matched).get(lookup, english)
        try:
            if template != english:
                try:
                    return template.format(**values)
                except (KeyError, IndexError, ValueError, TypeError, AttributeError):
                    pass
            return english.format(**values)
        except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
            raise MessageFormatError(
                f"{self._folder}: cannot render '{key}' in {locale}: {exc}"
            ) from exc

    def _messages_for(self, locale: str) -> Mapping[str, str]:
        """Return the composite mapping for the locale matching ``locale``."""
        matched = match_offered_locale(locale, self._codes) or ENGLISH
        if matched == ENGLISH:
            # English laid over itself is always English; skip the merge and
            # the cache entry, neither of which do anything useful here.
            return self._english.messages

        with _LOCK:
            cached = _COMPOSITE.get((self._folder, matched))
        if cached is not None:
            return cached

        try:
            target = _parsed(self._folder, matched)
        except CatalogError as exc:
            # A translator's broken file must not break that locale's UI --
            # the same rule overlay() already enforces for a placeholder
            # mismatch. This is that rule arriving through a different door:
            # the locale fails to load at all, rather than one of its leaves
            # misbehaving, so fall back to English wholesale instead of leaf
            # by leaf.
            self._warn_unreadable(matched, exc)
            target = LocaleData(matched, {}, frozenset())

        composite = overlay(self._english, target)
        with _LOCK:
            return _COMPOSITE.setdefault((self._folder, matched), composite)

    def _missing(self, locale: str, key: str) -> str:
        """Raise, or log once and render the marker."""
        if self._strict:
            raise MissingMessageError(f"{self._folder}: no message named '{key}'")

        once = (locale, key)
        if once not in self._warned:
            self._warned.add(once)
            logger.warning("no message named '%s' for locale '%s' in %s", key, locale, self._folder)
        return MISSING_MARKER.format(key=key)

    def _warn_unreadable(self, locale: str, exc: CatalogError) -> None:
        """Log once that ``locale`` could not be loaded and English is standing in for it."""
        if locale in self._unreadable:
            return
        self._unreadable.add(locale)
        logger.warning(
            "locale '%s' in %s could not be loaded, falling back to English: %s",
            locale,
            self._folder,
            exc,
        )


def _parsed(folder: Path, code: str) -> LocaleData:
    """Return one locale's parsed data, reading it at most once per process."""
    with _LOCK:
        cached = _PARSED.get((folder, code))
    if cached is not None:
        return cached

    data = load_locale(folder, code)
    with _LOCK:
        return _PARSED.setdefault((folder, code), data)
