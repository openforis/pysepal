"""Legend content derived from layer styles and SEPAL asset visualizations."""

from typing import Any

from .spec import (
    Gradient,
    Legend,
    LegendItem,
    RasterStyle,
    VectorStyle,
    _normalise_color,
    colormap_stops,
)


def _fmt(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0]
    return f"{float(value):g}"


def _gradient_legend(colors: list[str], vmin: Any, vmax: Any, title: str) -> Legend | None:
    if len(colors) < 2 or vmin is None or vmax is None:
        return None
    gradient = Gradient(colors=colors, labels=[_fmt(vmin), _fmt(vmax)], title=title)
    return Legend(title=title, gradients=[gradient])


def derive_legend(
    style: RasterStyle | VectorStyle, *, title: str = "", default_color: str = ""
) -> Legend | None:
    """Derive a legend from a layer style.

    Args:
        style: the raster or vector style.
        title: legend title; also the label of a vector chip.
        default_color: chip color for a vector style with neither fill nor stroke.

    Returns:
        The legend, one item per class for a style with classes, or ``None`` when the
        style has nothing to explain (e.g. multiband).
    """
    if style.class_colors:
        labels = style.class_labels or {}
        items = [
            LegendItem(label=labels.get(k, str(k)), color=c) for k, c in style.class_colors.items()
        ]
        return Legend(title=title, items=items)

    if isinstance(style, VectorStyle):
        color = style.fill or style.stroke or default_color
        if not color:
            return None
        return Legend(title=title, items=[LegendItem(label=title, color=color)])

    colors = colormap_stops(style.colormap) if style.colormap else style.palette
    if not colors:
        return None
    return _gradient_legend(colors, style.min, style.max, title)


def legend_from_asset_viz(viz: dict, *, title: str = "") -> Legend | None:
    """Derive a legend from one SEPAL asset visualization dict.

    Args:
        viz: visualization with ``type``, ``palette``, ``values``, ``labels``, ``min``, ``max``.
        title: legend title.

    Returns:
        The legend, or ``None`` for types without a palette (rgb, hsv) or malformed input.
    """
    try:
        palette = [_normalise_color(c) for c in viz.get("palette") or []]
        if viz.get("type") == "categorical":
            values = viz["values"]
            labels = viz.get("labels") or [str(v) for v in values]
            if not palette or not (len(values) == len(labels) == len(palette)):
                return None
            items = [LegendItem(label=str(lb), color=c) for lb, c in zip(labels, palette)]
            return Legend(title=title, items=items)
        if viz.get("type") == "continuous":
            return _gradient_legend(palette, viz.get("min"), viz.get("max"), title)
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return None
