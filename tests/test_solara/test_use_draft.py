"""Input drafts preserve incomplete edits and follow external value changes."""

import pytest
import reacton
import solara

from pysepal.solara.hooks import _use_draft


def test_publishing_none_preserves_the_incomplete_draft():
    value = solara.reactive({"pathname": "old.csv"})
    state = {}

    @solara.component
    def Probe():
        draft, publish = _use_draft(value)
        state.update(draft=draft, publish=publish)
        solara.Text(str(draft.value))

    _, rc = reacton.render(Probe(), handle_error=False)
    try:
        state["draft"].set({"pathname": "new.csv", "id_column": None})
        state["publish"](None)
        rc.force_update()
        assert value.value is None
        assert state["draft"].value == {"pathname": "new.csv", "id_column": None}
    finally:
        rc.close()


@pytest.mark.parametrize("external", [None, {}, [], "", 0, False])
def test_external_empty_values_replace_the_draft(external):
    value = solara.reactive("initial")
    state = {}

    @solara.component
    def Probe():
        draft, publish = _use_draft(value)
        state.update(draft=draft, publish=publish)
        solara.Text(str(draft.value))

    _, rc = reacton.render(Probe(), handle_error=False)
    try:
        state["draft"].set("edited")
        state["publish"]("edited")
        value.set(external)
        assert state["draft"].value == external
    finally:
        rc.close()


def test_a_previous_publication_can_be_supplied_again_after_an_external_change():
    value = solara.reactive("initial")
    state = {}

    @solara.component
    def Probe():
        draft, publish = _use_draft(value)
        state.update(draft=draft, publish=publish)
        solara.Text(str(draft.value))

    _, rc = reacton.render(Probe(), handle_error=False)
    try:
        state["draft"].set("A")
        state["publish"]("A")
        value.set("B")
        value.set("A")
        assert state["draft"].value == "A"
    finally:
        rc.close()
