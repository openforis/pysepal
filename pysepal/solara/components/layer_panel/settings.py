"""The settings pop-up of a layer row."""

from typing import Callable, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.layers import GeeSource, LayerSpec, LayerStore
from pysepal.message import msg

from .download import download_filename, download_payload, download_size, is_too_large
from .restyle import RestyleForm


def _download(spec: LayerSpec, layer_id: str, size: int):
    too_large = is_too_large(size)
    if too_large:
        # A FileDownload starts the download on any click inside it, a disabled button too.
        control = solara.Button(
            msg("layer_panel.download"),
            icon_name="mdi-cloud-download-outline",
            disabled=True,
            attributes={"data-role": "download", "data-layer-id": layer_id},
        )
    else:
        control = solara.FileDownload(
            data=lambda: download_payload(spec)[0],
            filename=download_filename(spec),
            label=msg("layer_panel.download"),
        )
    activator = rv.Html(tag="span", v_bind="tooltip.props", children=[control])
    return rv.Tooltip(
        location="bottom",
        disabled=not too_large,
        attributes={"data-role": "download-tip", "data-layer-id": layer_id},
        v_slots=[{"name": "activator", "variable": "tooltip", "children": [activator]}],
        children=[msg("layer_panel.too_large")],
    )


@solara.component
def LayerSettings(
    store: LayerStore,
    layer_id: str,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
    is_dark: bool = False,
    version: int = 0,
):
    """Opacity, style, download and export of one layer.

    Args:
        store: The layer store.
        layer_id: Id of the layer edited.
        on_export: Called with the spec when Export is clicked; no button without it.
        is_dark: Whether the theme is dark.
        version: The panel's store version, so the pop-up follows every store event.
    """
    if layer_id not in store:
        return solara.Column(children=[])
    spec, view = store.get(layer_id), store.view(layer_id)

    body = [
        rv.Slider(
            label=msg("layer_panel.opacity"),
            min=0,
            max=1,
            step=0.05,
            hide_details=True,
            v_model=view.opacity,
            on_v_model=lambda value: store.set_opacity(layer_id, float(value)),
            attributes={"data-role": "opacity", "data-layer-id": layer_id},
        )
    ]
    # Pre-rendered tiles cannot be restyled here.
    if spec.source.type != "tile":
        body.append(
            RestyleForm(spec=spec, on_apply=lambda changes: store.restyle(layer_id, **changes))
        )

    actions = []
    size = download_size(spec)
    if size is not None:
        actions.append(_download(spec, layer_id, size))
    if isinstance(spec.source, GeeSource) and on_export is not None:
        actions.append(
            solara.Button(
                msg("layer_panel.export"),
                text=True,
                on_click=lambda: on_export(store.get(layer_id)),
                attributes={"data-role": "export", "data-layer-id": layer_id},
            )
        )
    if actions:
        body.append(solara.Row(style={"gap": "4px", "flex-wrap": "wrap"}, children=actions))
    return rv.Card(
        min_width=280,
        max_width=360,
        class_="pa-3",
        children=[solara.Column(gap="8px", children=body)],
    )
