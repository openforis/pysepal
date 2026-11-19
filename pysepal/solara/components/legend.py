"""Reusable floating map legend for Solara apps.

Supports discrete color chips and continuous gradient bars.
Designed for bottom-center overlay on map-based pysepal apps.

Usage:
    from pysepal.solara.components.legend import (
        LegendComponent, LegendData, GradientEntry, DiscreteEntry,
    )
    from dataclasses import asdict

    legend = LegendData(
        gradients=[GradientEntry(colors=["#ffff00", "#8b0000"], labels=["2001", "2024"])],
        items=[DiscreteEntry("Forest", "#006400", detail="12,345 km² · 42%")],
    )
    LegendComponent(legend_data=asdict(legend))

Pass ``selector_options`` when several layers each have their own legend, and
swap ``legend_data`` as the selection changes::

    LegendComponent(
        legend_data=asdict(legends[selected.value]),
        selector_options=[{"value": k, "text": v.title} for k, v in legends.items()],
        selected=selected.value,
        event_set_selected=selected.set,
    )

See ``demo_apps/solara_map_app/component/widget/legend.py`` for a
working example.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional

import solara


@dataclass
class GradientEntry:
    """A continuous color ramp with labeled endpoints."""

    colors: list[str]
    labels: list[str]
    title: str = ""


@dataclass
class DiscreteEntry:
    """A single labeled color chip.

    Args:
        label: Text shown next to the chip.
        color: Chip color. An empty string renders an invisible chip, which
            keeps labels aligned and reads as a totals row.
        detail: Right-aligned secondary text, e.g. an area or a share. As soon
            as any entry sets it, the whole item block switches from wrapped
            chips to one stacked row per entry so the details line up.
    """

    label: str
    color: str
    detail: str = ""


@dataclass
class LegendData:
    """Complete legend specification passed to LegendComponent."""

    gradients: list[GradientEntry] = field(default_factory=list)
    items: list[DiscreteEntry] = field(default_factory=list)


@solara.component_vue("Legend.vue")
def LegendComponent(
    legend_data: Optional[dict] = None,
    visible: bool = True,
    collapsed: bool = False,
    event_set_collapsed: Optional[Callable[[bool], None]] = None,
    selector_options: Optional[list[dict[str, str]]] = None,
    selected: Optional[str] = None,
    event_set_selected: Optional[Callable[[str], None]] = None,
    inline: bool = False,
):
    """Floating map legend overlay.

    Renders at bottom-center of the viewport over the map area.
    Supports gradient bars and discrete color chips.

    Args:
        legend_data: Serialized LegendData (use dataclasses.asdict).
            Empty dict or missing keys = nothing rendered.
        visible: Show/hide the entire legend.
        collapsed: Collapsed state (icon pill only).
        event_set_collapsed: Callback when user toggles collapse.
        selector_options: Optional [{"value", "text"}] layer options. When two
            or more are given, a compact dropdown renders at the top of the
            legend body; one or none renders no dropdown.
        selected: The currently selected option value.
        event_set_selected: Callback when the user picks a different option.
        inline: Render in the normal flow at the width of its container (for
            a panel) instead of floating over the map.
    """
    pass
