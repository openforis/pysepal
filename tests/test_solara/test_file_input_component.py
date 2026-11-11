"""FileInputComponent with multiple=True syncs a list of paths both ways."""

import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import reacton
import solara

from pysepal.scripts.filesystem import LocalFileSystem
from pysepal.solara.components.inputs._file_input_widget import VUE_DIR, FileInputWidget
from pysepal.solara.components.inputs.file_input import FileInputComponent

from ._harness import of_type, wait_until

# `python -c` imports pysepal from its cwd; a test elsewhere chdirs and never restores.
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def batch(tmp_path: Path) -> Path:
    (tmp_path / "a.csv").write_text("")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.csv").write_text("")
    return tmp_path


def _run(component, interact):
    async def run():
        root, rc = reacton.render(component, handle_error=False)
        try:
            await interact(of_type(root, "FileInputWidget")[0])
        finally:
            rc.close()

    asyncio.run(run())


def test_a_list_syncs_both_ways(batch: Path) -> None:
    held = solara.reactive([])
    a, b = str(batch / "a.csv"), str(batch / "sub" / "b.csv")

    @solara.component
    def Harness():
        FileInputComponent(filesystem=LocalFileSystem(batch), multiple=True, value=held)

    async def interact(widget):
        assert widget.multiple is True
        assert widget.v_model == []

        widget.set_state({"value": [a, b]})
        await wait_until(lambda: held.value == [a, b])

        held.set([b])
        await wait_until(lambda: widget.v_model == [b])
        assert widget.value == [b]

    _run(Harness(), interact)


def test_a_browser_list_outside_the_root_does_not_reach_the_app(batch: Path) -> None:
    held = solara.reactive([])
    a = str(batch / "a.csv")

    @solara.component
    def Harness():
        FileInputComponent(root=str(batch / "sub"), multiple=True, value=held)

    async def interact(widget):
        widget.set_state({"value": [a, str(batch / "sub" / "b.csv")]})
        await wait_until(lambda: held.value == [str(batch / "sub" / "b.csv")])

    _run(Harness(), interact)


def test_on_value_receives_a_list(batch: Path) -> None:
    seen = []
    a = str(batch / "a.csv")

    @solara.component
    def Harness():
        FileInputComponent(
            filesystem=LocalFileSystem(batch), multiple=True, value=[], on_value=seen.append
        )

    async def interact(widget):
        widget.set_state({"value": [a]})
        await wait_until(lambda: seen == [[a]])

    _run(Harness(), interact)


def test_a_multiple_input_starts_empty_from_the_default_value(batch: Path) -> None:
    """The default value "" is the single-mode empty value; a multiple input reads it as []."""
    held = solara.reactive("")

    @solara.component
    def Harness():
        FileInputComponent(filesystem=LocalFileSystem(batch), multiple=True, value=held)

    async def interact(widget):
        assert widget.v_model == []
        assert widget.value == []

    _run(Harness(), interact)


def test_single_mode_still_syncs_a_str(batch: Path) -> None:
    held = solara.reactive("")
    a = str(batch / "a.csv")

    @solara.component
    def Harness():
        FileInputComponent(filesystem=LocalFileSystem(batch), value=held)

    async def interact(widget):
        assert widget.multiple is False
        widget.set_state({"value": a})
        await wait_until(lambda: held.value == a)

    _run(Harness(), interact)


def test_the_app_can_switch_the_mode(batch: Path) -> None:
    """Turning multiple off with a list held clears the selection instead of failing."""
    mode = solara.reactive(False)
    a = str(batch / "a.csv")
    held = solara.reactive(a)

    @solara.component
    def Harness():
        FileInputComponent(filesystem=LocalFileSystem(batch), multiple=mode.value, value=held)

    async def interact(widget):
        mode.set(True)
        await wait_until(lambda: widget.multiple and widget.v_model == [a])

        widget.set_state({"value": [a]})
        mode.set(False)
        await wait_until(lambda: widget.multiple is False and held.value == "")
        assert widget.v_model == ""

    _run(Harness(), interact)


def test_select_folders_reaches_the_widget(batch: Path) -> None:
    held = solara.reactive([])
    sub = str(batch / "sub")

    @solara.component
    def Harness():
        FileInputComponent(
            filesystem=LocalFileSystem(batch), multiple=True, select_folders=True, value=held
        )

    async def interact(widget):
        assert widget.select_folders is True

        widget.set_state({"value": [sub]})
        await wait_until(lambda: held.value == [sub])

    _run(Harness(), interact)


@pytest.mark.parametrize(
    "spelling",
    [
        r"<v-list-item-(content|action|group)\b",
        r'v-on="on"',
        r"\s(dense|small|x-small|outlined|depressed|text|left|right)(\s|/?>)",
    ],
)
def test_markup_has_no_vuetify2_spellings(spelling: str) -> None:
    """Vuetify 3 drops unknown props and only warns about removed components."""
    markup = FileInputWidget().template.template.split("<script>")[0]
    assert not re.search(spelling, markup)


def test_template_holds_markup_script_and_style() -> None:
    template = FileInputWidget().template.template

    assert re.search(r'v-slot:activator="\{ props \}"', template)
    assert "module.exports = {" in template
    assert "<style>" in template


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_browser_selection_logic() -> None:
    """The Vue side toggles files, keeps them across folders and clears them all."""
    harness = Path(__file__).parents[1] / "js" / "file_input_selection.mjs"
    traits = {
        name: trait.default()
        for name, trait in FileInputWidget.class_own_traits(sync=True).items()
        if name not in ("template", "template_file")
    }
    subprocess.run(
        ["node", str(harness), str(VUE_DIR / "FileInput.vue"), json.dumps(traits)],
        check=True,
        capture_output=True,
        text=True,
    )


def test_the_inputs_do_not_import_sepalwidgets() -> None:
    """pysepal.sepalwidgets does not import on ipyvuetify 3, so the inputs must not need it."""
    code = (
        "import sys, pysepal.solara.components.inputs\n"
        "print('LEGACY', [m for m in sys.modules if m.startswith('pysepal.sepalwidgets')])"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], check=True, capture_output=True, text=True, cwd=REPO_ROOT
    )

    assert "LEGACY []" in result.stdout.splitlines()
