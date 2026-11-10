"""FileInputComponent with multiple=True syncs a list of paths both ways."""

import asyncio
from pathlib import Path

import pytest
import reacton
import solara

from pysepal.scripts.filesystem import LocalFileSystem
from pysepal.solara.components.inputs.file_input import FileInputComponent

from ._harness import of_type, wait_until


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
            await interact(of_type(root, "FileInput")[0])
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
