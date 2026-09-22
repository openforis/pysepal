"""Guards for watchers on synced traits in VuetifyTemplate widgets.

ipyvue installs its own watcher on every synced trait, which pushes a change
made in the browser back to Python. That watcher replaces a template watcher of
the same name and calls it as ``watch[name].bind(this)(value)``, so a template
watcher on a synced trait must be a plain function. The object form
(``{ immediate: true, handler() {...} }``) raises ``TypeError: n[i].bind is not
a function`` on every change, its handler never runs, and ``immediate`` is
dropped. Do the first run from ``mounted()`` instead.
"""

import importlib
import pkgutil
import re
from pathlib import Path

import ipyvuetify as v
import pytest

import pysepal

WATCH_START = re.compile(r"^  watch: \{$")
BLOCK_END = re.compile(r"^  \},?$")
OBJECT_WATCHER = re.compile(r"^    ['\"]?([\w.]+)['\"]?: \{")


def _template_widgets():
    """Every pysepal VuetifyTemplate subclass with its template file."""
    for module in pkgutil.walk_packages(pysepal.__path__, "pysepal."):
        if module.name.startswith("pysepal.templates"):
            continue
        importlib.import_module(module.name)

    seen, stack = [], list(v.VuetifyTemplate.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if not cls.__module__.startswith("pysepal.") or cls in seen:
            continue
        trait = cls.class_traits().get("template_file")
        template = getattr(trait, "default_value", None)
        if isinstance(template, str) and template.endswith(".vue"):
            seen.append(cls)
            yield pytest.param(cls, Path(template), id=cls.__name__)


def _object_watchers(vue_file: Path) -> set:
    """Names watched in the object form, read from the prettier-formatted block."""
    names, inside = set(), False
    for line in vue_file.read_text().splitlines():
        if WATCH_START.match(line):
            inside = True
        elif inside and BLOCK_END.match(line):
            break
        elif inside and (match := OBJECT_WATCHER.match(line)):
            names.add(match.group(1))
    return names


@pytest.mark.parametrize("cls, vue_file", list(_template_widgets()))
def test_synced_traits_are_watched_with_plain_functions(cls, vue_file):
    synced = set(cls.class_trait_names(sync=True))

    assert _object_watchers(vue_file) & synced == set()


def test_the_scan_finds_the_map_app_watchers():
    """The parser reads the object form it is meant to reject."""
    mapapp = next(p for p in _template_widgets() if p.id == "MapApp")
    assert {"open_dialog", "isNarrow"} <= _object_watchers(mapapp.values[1])
