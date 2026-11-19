"""One layer of the layer panel."""

from typing import Callable, Optional

import reacton.ipyvuetify as rv
import solara

from pysepal.frontend.styles import THEMES
from pysepal.layers import GeeSource, LayerSpec, LayerStore, derive_legend
from pysepal.message import msg
from pysepal.solara.components.legend import LegendComponent

from .download import download_filename, download_payload, is_downloadable


def _legend_data(spec: LayerSpec, view, is_dark: bool) -> Optional[dict]:
    legend = spec.legend or view.legend
    if legend is None:
        legend = derive_legend(
            spec.style, title=spec.name, default_color=THEMES[is_dark]["primary"]
        )
    return legend.model_dump() if legend is not None else None


def _icon_button(icon: str, role: str, layer_id: str, on_click):
    return solara.Button(
        icon=True,
        text=True,
        on_click=on_click,
        attributes={"data-role": role, "data-layer-id": layer_id},
        children=[rv.Icon(small=True, children=[icon])],
    )


@solara.component
def LayerRow(
    store: LayerStore,
    layer_id: str,
    on_export: Optional[Callable[[LayerSpec], None]] = None,
    is_dark: bool = False,
):
    """A layer's visibility, name, status and, when expanded, its controls.

    Args:
        store: The layer store.
        layer_id: Id of the layer shown.
        on_export: Called with the spec when Export is clicked; no button without it.
        is_dark: Whether the theme is dark, for the derived legend's default color.
    """
    expanded, set_expanded = solara.use_state(False)
    spec, view = store.get(layer_id), store.view(layer_id)

    status = view.status
    if status == "pending":
        status_icon = rv.ProgressCircular(indeterminate=True, size=16, width=2)
        tip = msg("layer_panel.preparing")
    elif status == "error":
        status_icon = rv.Icon(color="error", small=True, children=["mdi-alert"])
        tip = view.error or msg("layer_panel.error")
    else:
        status_icon = rv.Icon(
            small=True, style_="visibility: hidden", children=["mdi-circle-small"]
        )
        tip = ""

    header = solara.Row(
        classes=["pysepal-layer-row__header"],
        style={"align-items": "center", "gap": "4px", "flex-wrap": "nowrap"},
        children=[
            _icon_button(
                "mdi-eye" if view.visible else "mdi-eye-off",
                "visibility",
                layer_id,
                lambda: store.set_visible(layer_id, not view.visible),
            ),
            solara.Text(spec.name, style={"flex": "1 1 auto", "min-width": "0"}),
            # Always rendered, so the element tree keeps its shape across statuses.
            solara.Tooltip(tip, children=[rv.Html(tag="span", children=[status_icon])]),
            _icon_button(
                "mdi-chevron-up" if expanded else "mdi-chevron-down",
                "expand",
                layer_id,
                lambda: set_expanded(not expanded),
            ),
        ],
    )
    if not expanded:
        return solara.Column(classes=["pysepal-layer-row"], gap="0px", children=[header])

    body = []
    if view.kind != "pmtiles":
        body.append(
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
        )
    legend = _legend_data(spec, view, is_dark)
    if legend is not None:
        body.append(LegendComponent(legend_data=legend, inline=True))

    actions = []
    if is_downloadable(spec):
        actions.append(
            solara.FileDownload(
                data=lambda: download_payload(spec)[0],
                filename=download_filename(spec),
                label=msg("layer_panel.download"),
            )
        )
    if isinstance(spec.source, GeeSource) and on_export is not None:
        actions.append(
            solara.Button(
                msg("layer_panel.export"),
                text=True,
                on_click=lambda: on_export(store.get(layer_id)),
                attributes={"data-role": "export", "data-layer-id": layer_id},
            )
        )
    actions.append(
        solara.Button(
            msg("layer_panel.remove"),
            text=True,
            color="error",
            on_click=lambda: store.remove(layer_id),
            attributes={"data-role": "remove", "data-layer-id": layer_id},
        )
    )
    body.append(solara.Row(style={"gap": "4px", "flex-wrap": "wrap"}, children=actions))
    return solara.Column(classes=["pysepal-layer-row"], gap="0px", children=[header, *body])
