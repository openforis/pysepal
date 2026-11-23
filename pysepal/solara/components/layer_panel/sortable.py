"""A drag-sortable list of already-built widgets."""

from typing import Callable, Optional

import solara


@solara.component_vue("SortableList.vue")
def _SortableListView(
    ids: list = [],
    handle_label: str = "",
    event_move: Optional[Callable[[dict], None]] = None,
    children: list = [],
):
    pass


@solara.component
def SortableList(
    ids: list[str],
    children: list,
    on_move: Callable[[str, int], None],
    handle_label: str = "",
):
    """Render ``children`` as rows that can be reordered by dragging a handle.

    The handle also moves its row with Alt+Up and Alt+Down.

    Args:
        ids: One identifier per child, in display order.
        children: The row contents, one per id.
        on_move: Called with ``(id, to)`` when a row is dropped at index ``to``.
        handle_label: The accessible name and tooltip of each handle.
    """

    def handle(payload: dict) -> None:
        on_move(payload["id"], int(payload["to"]))

    return _SortableListView(
        ids=list(ids), handle_label=handle_label, event_move=handle, children=children
    )
