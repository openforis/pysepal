"""Helpers for rendering Solara components in tests and asserting on the tree."""

import asyncio
from typing import Any, Callable, Iterator, List, Optional


def walk(widget: Any) -> Iterator[Any]:
    """Yield every widget in the tree, parents before children, in document order.

    Args:
        widget: The root widget.

    Yields:
        Each widget in the tree.
    """
    yield widget
    for child in getattr(widget, "children", ()) or ():
        yield from walk(child)


def of_type(root: Any, *type_names: str) -> List[Any]:
    """Return every widget whose class name is one of ``type_names``, in document order.

    Args:
        root: The root widget.
        type_names: Class names to keep, e.g. ``"Select"``, ``"Combobox"``.

    Returns:
        The matching widgets.
    """
    return [w for w in walk(root) if type(w).__name__ in type_names]


def find_by_label(root: Any, label: str) -> Optional[Any]:
    """Return the first widget carrying ``label``, or None.

    Args:
        root: The root widget.
        label: The exact ``label`` trait to match.

    Returns:
        The matching widget, or None when nothing matches.
    """
    for widget in walk(root):
        if getattr(widget, "label", None) == label:
            return widget
    return None


def render_and_drain(
    component: Any,
    until: Callable[[Any], bool],
    *,
    timeout: float = 3.0,
) -> Any:
    """Render ``component`` and let its ``use_task`` work run until ``until`` holds.

    ``asyncio.run(component.widget())`` returns as soon as the synchronous render is
    done and then cancels every pending task, so anything a task produces is invisible
    to a plain render. Yielding to the loop until the condition holds makes those
    results observable without a fixed sleep.

    ``until`` receives the rendered root so a test can gate on **widget** state. That
    matters more than it sounds: a component republishing a value that deep-equals
    what a reactive already holds fires no callback at all (solara compares with
    ``equals_extra`` before notifying), so a restore test gated on a publish can wait
    forever while the component behaves perfectly. Gate on what the widgets show.

    Args:
        component: The Solara component to render.
        until: Called with the root widget after each yield; the drain stops when it
            returns True. Accept and ignore the argument if you do not need it.
        timeout: Seconds to keep yielding before giving up.

    Returns:
        The rendered root widget. The condition may still be unmet on timeout — assert
        on it in the test so the failure names what did not happen.
    """

    async def _runner():
        root = component.widget()
        deadline = asyncio.get_running_loop().time() + timeout
        while not until(root) and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        return root

    return asyncio.run(_runner())
