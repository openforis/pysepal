"""Hooks that connect Solara components to a layer store."""

import solara

from pysepal.layers.store import LayerStore


def use_layer_store(store: LayerStore) -> int:
    """Re-render the calling component on every store event.

    Args:
        store: The store to follow.

    Returns:
        A counter that grows with each event, usable as a dependency.
    """
    version, set_version = solara.use_state(0)

    def subscribe():
        return store.subscribe(lambda _event: set_version(lambda v: v + 1))

    solara.use_effect(subscribe, [store])
    return version
