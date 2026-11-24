"""Hooks for pysepal's Solara components."""

from typing import TYPE_CHECKING, Callable, Optional, Tuple, TypeVar

import solara

if TYPE_CHECKING:
    from pysepal.mapping import SepalMap

T = TypeVar("T")
M = TypeVar("M", bound="SepalMap")


def use_sepal_map(factory: Callable[[], M], dependencies: Optional[list] = None) -> M:
    """Build a map in the component that owns it, and close it there.

    The component that builds a map closes it; the components it passes the
    map to never do. Solara closes only the widgets it built from elements, so
    a map built in ``solara.use_memo`` alone stays alive, with its layer
    engine, its store subscription, its theme observer and its link group,
    until the kernel closes. This hook closes it in an effect cleanup, which
    runs when the component unmounts, when ``dependencies`` change (the old
    map; the new one is built in the same render) and on a hot reload, which
    keeps the kernel. A closed map leaves its link group, so the map a reload
    builds opens at its own ``center`` instead of the old map's camera.

    Args:
        factory: Builds the map, and may add its first layers.
        dependencies: Rebuild the map when one of these changes, as in
            ``solara.use_memo``; None means the variables ``factory`` reads
            from the enclosing function.

    Returns:
        The map, the same object on every render until a dependency changes.
    """
    sepal_map = solara.use_memo(factory, dependencies)
    solara.use_effect(lambda: sepal_map.close, [sepal_map])
    return sepal_map


def _use_draft(value: solara.Reactive[T]) -> Tuple[solara.Reactive[T], Callable[[T], None]]:
    """Keep an editable draft when the published value may be incomplete.

    External changes, including clears, replace the draft. Publishing an output
    leaves the draft intact, so a selector can emit None while the user is still
    filling its required fields. Ordinary inputs should use use_reactive directly.
    """
    initial = solara.use_memo(value.peek, [])
    draft = solara.use_reactive(initial)
    last_value = solara.use_ref(initial)

    def sync_value():
        incoming = value.value
        if not solara.util.equals_extra(incoming, last_value.current):
            last_value.current = incoming
            draft.set(incoming)

    solara.use_effect(sync_value, [value, value.value])

    def publish(output: T) -> None:
        last_value.current = output
        value.set(output)

    return draft, publish
