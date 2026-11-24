"""A drag-sortable list of already-built widgets."""

from typing import Callable, Optional, Sequence

import solara


@solara.component_vue("SortableList.vue")
def _SortableListView(
    ids: list = [],
    locked: list = [],
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
    locked: Sequence[str] = (),
):
    """Render ``children`` as rows that can be reordered by dragging a handle.

    The handle also moves its row with Alt+Up and Alt+Down.

    Args:
        ids: One identifier per child, in display order.
        children: The row contents, one per id.
        on_move: Called with ``(id, to)`` when a row is dropped at index ``to``.
        handle_label: The accessible name and tooltip of each handle.
        locked: The ids of rows that keep their place, which lead the list: their
            handle is dimmed and moves nothing, and no row is dropped above them.
    """

    def handle(payload: dict) -> None:
        on_move(payload["id"], int(payload["to"]))

    return _SortableListView(
        ids=list(ids),
        locked=list(locked),
        handle_label=handle_label,
        event_move=handle,
        children=children,
    )
