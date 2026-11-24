"""Basemap picker of the layer panel."""

import reacton.ipyvuetify as rv
import solara

from pysepal.mapping.basemaps import basemap_label
from pysepal.message import msg

_TRAITS = ["basemaps", "basemap"]


@solara.component
def BasemapPicker(map_):
    """Choose which of the map's basemaps it shows; hidden while there is only one.

    Args:
        map_: The ``SepalMap`` whose ``basemaps`` are listed and whose ``basemap`` is set.
    """
    _, set_version = solara.use_state(0)

    def follow_basemaps():
        # A theme switch swaps the SEPAL choices, add_basemap adds one.
        def on_change(_change):
            set_version(lambda v: v + 1)

        map_.observe(on_change, names=_TRAITS)
        return lambda: map_.unobserve(on_change, names=_TRAITS)

    solara.use_effect(follow_basemaps, [map_])

    def pick(name: str) -> None:
        if name:
            map_.basemap = name

    if len(map_.basemaps) < 2:
        # mounted all the same, to follow the basemaps an app adds later
        return solara.Div(style="display: none")

    return rv.Select(
        label=msg("layer_panel.basemap"),
        items=[{"title": basemap_label(name), "value": name} for name in map_.basemaps],
        v_model=map_.basemap,
        on_v_model=pick,
        density="compact",
        hide_details=True,
        attributes={"data-role": "basemap"},
    )
