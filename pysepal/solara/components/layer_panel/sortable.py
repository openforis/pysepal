"""A drag-sortable list of already-built widgets."""

from typing import Callable, Optional

import solara


@solara.component_vue("SortableList.vue")
def _SortableListView(
    ids: list = [],
    event_move: Optional[Callable[[dict], None]] = None,
    children: list = [],
):
    pass


@solara.component
def SortableList(ids: list[str], children: list, on_move: Callable[[str, int], None]):
    """Render ``children`` as rows that can be reordered by dragging a handle.

    Args:
        ids: One identifier per child, in display order.
        children: The row contents, one per id.
        on_move: Called with ``(id, to)`` when a row is dropped at index ``to``.
    """

    def handle(payload: dict) -> None:
        on_move(payload["id"], int(payload["to"]))

    return _SortableListView(ids=list(ids), event_move=handle, children=children)
