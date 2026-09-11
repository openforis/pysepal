"""Scaffold catalogues and the notebook expressions consuming them."""

import ast
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

from pysepal.i18n import current_locale, set_locale

TEMPLATES = Path(__file__).parents[2] / "pysepal" / "templates"


@pytest.fixture(params=["map_app", "panel_app"])
def scaffold(request, tmp_path):
    folder = tmp_path / request.param
    shutil.copytree(TEMPLATES / request.param, folder)
    return folder


def _load_messages(scaffold):
    path = scaffold / "component" / "message" / "__init__.py"
    spec = importlib.util.spec_from_file_location("scaffold_messages", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.messages


def _assignment(notebook, name):
    for cell in json.loads(notebook.read_text())["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(line for line in cell["source"] if not line.startswith("%"))
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets
            ):
                return compile(ast.Module(body=[node], type_ignores=[]), str(notebook), "exec")
    raise AssertionError(f"{notebook} never creates {name}")


def test_scaffold_messages_follow_locale_and_fall_back_to_english(scaffold):
    french = scaffold / "component" / "message" / "fr"
    french.mkdir()
    (french / "app.json").write_text(json.dumps({"app": {"title": "Application"}}))
    messages = _load_messages(scaffold)
    original = current_locale()
    try:
        set_locale("en")
        english_title = messages.msg("app.title")
        assert english_title == (
            "Map application" if scaffold.name == "map_app" else "Panel application"
        )
        set_locale("fr")
        assert messages.msg("app.title") == "Application"
        assert messages.msg("app.footer", year=2030) == "The sky is the limit © 2030"
        set_locale("en")
        assert messages.msg("app.title") == english_title
    finally:
        set_locale(original)


def test_scaffold_notebook_builds_app_title_from_catalogue(scaffold):
    from pysepal import sepalwidgets as sw

    messages = _load_messages(scaffold)
    namespace = {"sw": sw, "messages": messages}
    exec(_assignment(scaffold / "ui.ipynb", "app_bar"), namespace)
    app_bar = namespace["app_bar"]
    try:
        assert app_bar.title.children == [messages.msg("app.title")]
    finally:
        app_bar.close()


def test_panel_notebook_formats_footer_year(tmp_path):
    from pysepal import sepalwidgets as sw

    scaffold = tmp_path / "panel_app"
    shutil.copytree(TEMPLATES / "panel_app", scaffold)
    namespace = {"sw": sw, "messages": _load_messages(scaffold)}
    exec(_assignment(scaffold / "ui.ipynb", "app_footer"), namespace)
    footer = namespace["app_footer"]
    try:
        assert "The sky is the limit © 2020" in str(footer.children)
    finally:
        footer.close()


def test_scaffold_translation_notebook_checks_catalogue(scaffold, monkeypatch):
    folder = scaffold / "component" / "message"
    monkeypatch.chdir(folder)
    monkeypatch.syspath_prepend(str(folder.parent))
    monkeypatch.delitem(sys.modules, "message", raising=False)
    namespace = {}
    try:
        for cell in json.loads((folder / "test_translation.ipynb").read_text())["cells"]:
            if cell["cell_type"] == "code":
                exec(compile("".join(cell["source"]), "test_translation.ipynb", "exec"), namespace)
        assert namespace["messages"].check() == ()
    finally:
        sys.modules.pop("message", None)
