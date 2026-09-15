"""Internal helpers for editable input state."""

from typing import Callable, Tuple, TypeVar

import solara

T = TypeVar("T")


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
