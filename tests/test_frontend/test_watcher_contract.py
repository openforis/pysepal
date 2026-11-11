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
import os
import re
from pathlib import Path
from typing import Optional

import ipyvuetify as v
import pytest

import pysepal

PACKAGE = Path(pysepal.__file__).parent

# Not walked: project scaffolding, and a stub that raises on import.
SKIPPED = ("pysepal.templates", "pysepal.sepalwidgets")

WATCH_START = re.compile(r"^  watch: \{$")
BLOCK_END = re.compile(r"^  \},?$")
OBJECT_WATCHER = re.compile(r"^    ['\"]?([\w.]+)['\"]?: \{")


def _template_path(cls) -> Optional[Path]:
    """The ``.vue`` file of a template class, or None.

    A pysepal widget sets it as a ``template_file`` trait; ``solara.component_vue``
    as a ``(module file, file name)`` class attribute.
    """
    trait = cls.class_traits().get("template_file")
    template = trait.default_value if trait is not None else getattr(cls, "template_file", None)
    if isinstance(template, tuple):
        template = os.path.join(os.path.dirname(template[0]), template[1])
    if isinstance(template, str) and template.endswith(".vue"):
        return Path(template)
    return None


def _template_widgets():
    """Every VuetifyTemplate class with a pysepal template, and that template."""
    for name in _module_names(SKIPPED):
        importlib.import_module(name)

    found, stack = {}, list(v.VuetifyTemplate.__subclasses__())
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        path = _template_path(cls)
        if path is None or not path.resolve().is_relative_to(PACKAGE.resolve()):
            continue
        # component_vue subclasses its base to add the traits: keep the subclass
        if path not in found or issubclass(cls, found[path]):
            found[path] = cls
    for path, cls in sorted(found.items()):
        yield pytest.param(cls, path, id=path.stem)


def _module_names(skipped: tuple):
    """Every module of the package, namespace packages (``solara.components``) included."""
    for path in sorted(PACKAGE.rglob("*.py")):
        parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
        name = ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
        if "__pycache__" not in parts and not name.startswith(skipped):
            yield name


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


def test_the_scan_finds_the_templates():
    """Guard the guard: an empty scan would make the parametrised test vacuous."""
    found = {param.id: param.values for param in _template_widgets()}
    expected = {"FileInput", "LocaleSelect", "Legend", "NotificationUI", "ColorSchemeBridge"}
    assert expected <= set(found)
    assert "mode" in found["ColorSchemeBridge"][0].class_trait_names(sync=True)


def test_the_parser_reads_the_object_form(tmp_path):
    """The parser reads the object form it is meant to reject."""
    vue = tmp_path / "Widget.vue"
    vue.write_text(
        "<script>\nmodule.exports = {\n  watch: {\n    plain(value) {},\n"
        "    open_dialog: {\n      immediate: true,\n      handler() {},\n    },\n"
        '    "isNarrow": {\n      handler() {},\n    },\n  },\n};\n</script>\n'
    )
    assert _object_watchers(vue) == {"open_dialog", "isNarrow"}
