"""Tests for the layer store hook and the sortable list."""

import re
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

# Stand-ins for the browser globals and for a drag already under way, so the drop
# logic runs in node. The rows are 32px high with a 2px gap.
_DROP_JS = """
globalThis.window = { removeEventListener() {} };
globalThis.document = { documentElement: { classList: { add() {}, remove() {} } } };
globalThis.setTimeout = () => 0;
function dropAt(from, to, commit, started = true) {
  const emitted = [];
  const vm = makeVm({
    ids: ["a", "b", "c"],
    move: (p) => emitted.push(p),
    $options: options,
    $el: { getBoundingClientRect: () => ({ top: 0 }) },
  });
  vm.drag = {
    index: from, to, started, pointerId: 1, listeners: {}, onKey() {},
    handle: { removeEventListener() {}, hasPointerCapture: () => false },
    tops: [0, 34, 68], heights: [32, 32, 32],
    ghost: { style: { top: "0px" }, remove() {} },
  };
  vm.endDrag(commit);
  return { emitted, shifts: vm.shifts, drag: vm.drag };
}
"""


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


def _view(box):
    return next(w for w in walk(box) if hasattr(w, "vue_move"))


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
    _view(box).vue_move({"id": "b", "to": 0})
    assert moves == [("b", 0)]


def test_handle_label_reaches_the_template():
    box, _ = solara.render(
        SortableList(
            ids=["a"], children=[solara.Text("a")], on_move=lambda i, t: None, handle_label="Drag"
        ),
        handle_error=False,
    )
    assert _view(box).handle_label == "Drag"


@needs_node
def test_drop_emits_move_with_the_slot_it_lands_in():
    result = run_vue_script(_VUE, _DROP_JS + "return dropAt(0, 2, true);")
    assert result["emitted"] == [{"id": "a", "to": 2}]
    # the dragged row shows in the last slot, the others moved up one, until the new ids land
    assert result["shifts"] == [68, -34, -34]
    assert result["drag"] is None


@needs_node
def test_a_drop_in_place_a_cancel_or_a_click_emits_nothing():
    result = run_vue_script(
        _VUE,
        _DROP_JS
        + "return [dropAt(1, 1, true), dropAt(0, 2, false), dropAt(0, 2, true, false)]"
        + ".map((r) => r.emitted);",
    )
    assert result == [[], [], []]


@needs_node
def test_the_target_is_the_number_of_rows_above_the_dragged_one():
    result = run_vue_script(
        _VUE,
        """
        const vm = makeVm({});
        const mids = [16, 50, 84];
        return [
          vm.targetIndex(mids, 0, 40), vm.targetIndex(mids, 0, 60), vm.targetIndex(mids, 0, 90),
          vm.targetIndex(mids, 2, 10), vm.targetIndex(mids, 2, 70),
        ];
        """,
    )
    assert result == [0, 1, 2, 0, 2]


@needs_node
def test_shifts_open_a_gap_where_the_row_will_land():
    result = run_vue_script(
        _VUE,
        """
        const vm = makeVm({});
        const tops = [0, 34, 68], heights = [32, 32, 32];
        return [vm.shiftsFor(tops, heights, 2, 0), vm.shiftsFor(tops, heights, 1, 1)];
        """,
    )
    assert result == [[34, 34, -68], [0, 0, 0]]


@needs_node
def test_alt_arrows_move_the_row_by_one():
    result = run_vue_script(
        _VUE,
        """
        const emitted = [];
        const vm = makeVm({ ids: ["a", "b", "c"], move: (p) => emitted.push(p) });
        vm.drag = null;
        const key = (index, key, altKey) =>
          vm.onHandleKey(index, { key, altKey, preventDefault() {} });
        key(1, "ArrowUp", true);
        key(1, "ArrowDown", true);
        key(0, "ArrowUp", true);
        key(2, "ArrowDown", true);
        key(1, "ArrowUp", false);
        return { emitted, refocus: vm.refocus };
        """,
    )
    assert result["emitted"] == [{"id": "b", "to": 0}, {"id": "b", "to": 2}]
    assert result["refocus"] == "b"


@needs_node
def test_the_held_cursor_covers_the_whole_page():
    grabbing = run_vue_script(_VUE, "return options.sortable.grabbing;")
    source = _VUE.read_text()
    # the rule must not be scoped, or it would only reach the list's own elements
    unscoped = re.search(r"<style>(.*?)</style>", source, re.DOTALL).group(1)
    assert f"html.{grabbing} *" in unscoped and "cursor: grabbing !important" in unscoped
    handle = re.search(
        r"> \.pysepal-sortable__handle \{(.*?)\}", source.split("<style scoped>")[1], re.DOTALL
    ).group(1)
    assert "cursor: grab;" in handle and "touch-action: none;" in handle
