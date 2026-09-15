"""The demo map and the lifecycle of the layers drawn on it."""

import solara
from component.parameter import AOI_LAYER_IDS

from pysepal import mapping as sm


def use_sepal_map(gee_interface, theme_state) -> sm.SepalMap:
    """Return the map, rebuilt only when the session's GEE interface changes."""

    def build_map():
        return sm.SepalMap(
            zoom=3,
            center=[0, 0],
            gee=True,
            gee_interface=gee_interface,
            fullscreen=True,
            theme_state=theme_state,
        )

    return solara.use_memo(build_map, [id(gee_interface)])


def _aoi_key(aoi_value) -> str:
    """Return a stable key for the current AOI selection."""
    if aoi_value is None:
        return ""

    return f"{aoi_value.method}:{aoi_value.name}"


def use_aoi_scoped_layers(aoi_data, sepal_map, outputs, layer_legends) -> None:
    """Drop the processed layers, outputs and legends when the AOI changes."""
    aoi_key = _aoi_key(aoi_data.value)
    previous_aoi_key = solara.use_ref(aoi_key)

    def drop_stale_outputs():
        """Processed layers belong to one AOI; retire them when it changes."""
        if previous_aoi_key.current == aoi_key:
            return

        for layer_id in AOI_LAYER_IDS:
            sepal_map.remove_layer(layer_id, none_ok=True)

        outputs.set(None)
        layer_legends.set(
            tuple(entry for entry in layer_legends.value if entry.layer_id not in AOI_LAYER_IDS)
        )
        previous_aoi_key.current = aoi_key

    solara.use_effect(drop_stale_outputs, [aoi_key])
