"""Tests for the layer store hook and the sortable list."""

from pathlib import Path

import solara

from pysepal.layers.store import LayerStore
from pysepal.solara.components.layer_panel.hooks import use_layer_store
from pysepal.solara.components.layer_panel.sortable import SortableList
from tests.test_solara._harness import walk
from tests.test_solara.test_notifications.test_notification_ui_template import (
    needs_node,
    run_vue_script,
)

_VUE = (
    Path(__file__).resolve().parents[2] / "pysepal/solara/components/layer_panel/SortableList.vue"
)


def test_hook_rerenders_on_event(raster_spec):
    store, renders = LayerStore(), []

    @solara.component
    def Probe():
        use_layer_store(store)
        renders.append(len(store))
        return solara.Text(str(len(store)))

    _, rc = solara.render(Probe(), handle_error=False)
    store.add(raster_spec)
    assert renders[-1] == 1
    rc.close()
    store.add(raster_spec.model_copy(update={"id": "z"}))
    assert renders[-1] == 1


def test_move_event_calls_on_move():
    moves = []
    box, _ = solara.render(
        SortableList(
            ids=["a", "b"],
            children=[solara.Text("a"), solara.Text("b")],
            on_move=lambda i, t: moves.append((i, t)),
        ),
        handle_error=False,
    )
    next(w for w in walk(box) if hasattr(w, "vue_move")).vue_move({"id": "b", "to": 0})
    assert moves == [("b", 0)]


@needs_node
def test_drop_on_first_row_emits_move():
    emitted = run_vue_script(
        _VUE,
        """
        const emitted = [];
        const vm = makeVm({ ids: ["a", "b"], move: (p) => emitted.push(p) });
        vm.onDragStart(1, null);
        vm.onDrop(0);
        return emitted;
        """,
    )
    assert emitted == [{"id": "b", "to": 0}]
