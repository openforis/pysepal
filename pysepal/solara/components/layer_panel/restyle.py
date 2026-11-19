"""The restyle form of an expanded layer row."""

from typing import Any, Callable

import reacton.ipyvuetify as rv
import solara
from pydantic import ValidationError

from pysepal.layers import LayerSpec, RasterStyle, VectorStyle
from pysepal.message import msg

COLORMAPS = [
    "inferno",
    "viridis",
    "magma",
    "plasma",
    "cividis",
    "gray",
    "terrain",
    "RdYlGn",
    "Spectral",
]


def _numbers(text: str) -> float | list[float]:
    values = [float(part) for part in text.split(",") if part.strip()]
    return values[0] if len(values) == 1 else values


def _show_number(value: Any) -> str:
    if value is None:
        return ""
    values = value if isinstance(value, list) else [value]
    return ",".join(f"{v:g}" for v in values)


def _field(name: str, widget, **kwargs):
    return widget(
        hide_details=True,
        dense=True,
        attributes={"data-role": "field", "data-field": name},
        **kwargs,
    )


def _error_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        first = exc.errors()[0]
        loc = ".".join(str(part) for part in first["loc"])
        return f"{loc}: {first['msg']}" if loc else first["msg"]
    return str(exc)


def _parse(name: str, raw: Any) -> Any:
    """Turn what a field holds into the value of the style field ``name``."""
    if name in ("min", "max"):
        return _numbers(raw)
    if name in ("width", "fill_opacity"):
        return float(raw)
    if name == "palette":
        return [c.strip() for c in raw.split(",") if c.strip()]
    return raw


@solara.component
def RestyleForm(spec: LayerSpec, on_apply: Callable[[dict], None]):
    """Edit the style of a layer and send the changed fields on Apply.

    Args:
        spec: The layer being edited.
        on_apply: Called with the changed style fields only. A ``ValidationError`` it raises
            is shown inline.
    """
    style = spec.style
    edits = solara.use_ref({})
    error, set_error = solara.use_state("")
    # ipyvue binds the click handler once, so it reads the latest apply through a ref.
    apply_ref = solara.use_ref(None)

    def edit(name: str):
        def handler(value):
            edits.current = {**edits.current, name: value}

        return handler

    def apply():
        try:
            changes = {}
            for name, raw in edits.current.items():
                if raw is None or raw == "":
                    continue
                value = _parse(name, raw)
                if value in ([], getattr(style, name, None)):
                    continue
                changes[name] = value
            if changes:
                on_apply(changes)
        except (ValueError, ValidationError) as exc:
            set_error(_error_text(exc))
            return
        edits.current = {}
        set_error("")

    apply_ref.current = apply

    fields = []
    if isinstance(style, RasterStyle):
        if style.class_colors:
            return solara.Column(children=[])
        fields += [
            _field(
                "min",
                rv.TextField,
                label=msg("layer_panel.min"),
                v_model=_show_number(style.min),
                on_v_model=edit("min"),
            ),
            _field(
                "max",
                rv.TextField,
                label=msg("layer_panel.max"),
                v_model=_show_number(style.max),
                on_v_model=edit("max"),
            ),
        ]
        if len(style.bands or []) <= 1:
            fields += [
                _field(
                    "colormap",
                    rv.Select,
                    label=msg("layer_panel.colormap"),
                    items=COLORMAPS,
                    v_model=style.colormap,
                    on_v_model=edit("colormap"),
                ),
                _field(
                    "palette",
                    rv.TextField,
                    label=msg("layer_panel.palette"),
                    v_model=",".join(style.palette or []),
                    on_v_model=edit("palette"),
                ),
            ]
    elif isinstance(style, VectorStyle):
        fields += [
            _field(
                "stroke",
                rv.TextField,
                label=msg("layer_panel.stroke"),
                v_model=style.stroke or "",
                on_v_model=edit("stroke"),
            ),
            _field(
                "fill",
                rv.TextField,
                label=msg("layer_panel.fill"),
                v_model=style.fill or "",
                on_v_model=edit("fill"),
            ),
            _field(
                "fill_opacity",
                rv.Slider,
                label=msg("layer_panel.fill_opacity"),
                min=0,
                max=1,
                step=0.05,
                v_model=style.effective_fill_opacity,
                on_v_model=edit("fill_opacity"),
            ),
            _field(
                "width",
                rv.TextField,
                label=msg("layer_panel.width"),
                type="number",
                v_model=_show_number(style.width),
                on_v_model=edit("width"),
            ),
        ]

    return solara.Column(
        classes=["pysepal-restyle"],
        gap="4px",
        children=[
            *fields,
            # Always rendered, so the element tree keeps its shape.
            rv.Html(
                tag="div",
                class_="error--text",
                attributes={"data-role": "restyle-error"},
                children=[error],
            ),
            solara.Button(
                msg("layer_panel.apply"),
                text=True,
                on_click=lambda: apply_ref.current(),
                attributes={"data-role": "apply"},
            ),
        ],
    )
