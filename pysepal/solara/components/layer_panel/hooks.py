"""Hooks that connect Solara components to a layer store."""

import solara

from pysepal.layers.store import LayerStore


def use_layer_store(store: LayerStore) -> int:
    """Re-render the calling component on every store event.

    The counter also grows once when the subscription starts, so a write made between
    the first render and the subscription is not missed.

    Args:
        store: The store to follow. Pass the same object on every render: a new store
            starts a new subscription.

    Returns:
        A counter that grows with each event, usable as a dependency.
    """
    version, set_version = solara.use_state(0)

    def subscribe():
        unsubscribe = store.subscribe(lambda _event: set_version(lambda v: v + 1))
        set_version(lambda v: v + 1)
        return unsubscribe

    solara.use_effect(subscribe, [store])
    return version
