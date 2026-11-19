"""Basemap picker of the layer panel."""

import reacton.ipyvuetify as rv
import solara

from pysepal.message import msg


@solara.component
def BasemapPicker(map_):
    """Choose which of the map's basemaps is visible.

    Args:
        map_: The ``SepalMap`` whose base layers are listed.
    """
    _, set_version = solara.use_state(0)

    def follow_layers():
        # A theme switch replaces the basemap objects in ``layers``.
        def on_change(_change):
            set_version(lambda v: v + 1)

        map_.observe(on_change, names="layers")
        return lambda: map_.unobserve(on_change, names="layers")

    solara.use_effect(follow_layers, [map_])

    bases = [layer for layer in map_.layers if layer.base]
    names = [layer.name for layer in bases]
    current = next((layer.name for layer in bases if layer.visible), None)

    def pick(name: str) -> None:
        for layer in bases:
            layer.visible = layer.name == name
        set_version(lambda v: v + 1)

    return rv.Select(
        label=msg("layer_panel.basemap"),
        items=names,
        v_model=current,
        on_v_model=pick,
        density="compact",
        hide_details=True,
        attributes={"data-role": "basemap"},
    )
