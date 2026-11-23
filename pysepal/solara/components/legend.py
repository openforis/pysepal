"""Reusable map legend for Solara apps.

Supports discrete color chips and continuous gradient bars. By default it floats
bottom-center over a ``MapApp``'s map; it can also sit in an app's panel
(``placement="inline"``) or in a slot over a ``MapView`` (``placement="map"``).

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

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Callable, Literal, Optional

import solara

from pysepal.message import msg

LegendPlacement = Literal["viewport", "inline", "map"]


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
def _LegendTemplate(
    legend_data: Optional[dict] = None,
    visible: bool = True,
    collapsed: bool = False,
    event_set_collapsed: Optional[Callable[[bool], None]] = None,
    selector_options: Optional[list[dict[str, str]]] = None,
    selected: Optional[str] = None,
    event_set_selected: Optional[Callable[[str], None]] = None,
    placement: LegendPlacement = "viewport",
    title: str = "",
    labels: Optional[dict[str, str]] = None,
):
    """The template's traits; ``LegendComponent`` resolves the placement and the labels."""
    pass


@solara.component
def LegendComponent(
    legend_data: Optional[dict] = None,
    visible: bool = True,
    collapsed: bool = False,
    event_set_collapsed: Optional[Callable[[bool], None]] = None,
    selector_options: Optional[list[dict[str, str]]] = None,
    selected: Optional[str] = None,
    event_set_selected: Optional[Callable[[str], None]] = None,
    inline: bool = False,
    placement: Optional[LegendPlacement] = None,
    title: str = "",
    labels: Optional[Mapping[str, str]] = None,
):
    """Map legend card with a toggle bar under it.

    Supports gradient bars and discrete color chips. The card's title row names
    the shown layer: a dropdown with the layer's name and its rank (``2/4``)
    when two or more options are given, else the title as plain text. A long
    legend scrolls inside the card, and the collapsed bar keeps the name.

    Args:
        legend_data: Serialized LegendData (use dataclasses.asdict).
            Empty dict or missing keys = nothing rendered.
        visible: Show/hide the entire legend.
        collapsed: Collapsed state (the bar only).
        event_set_collapsed: Callback when user toggles collapse.
        selector_options: Optional [{"value", "text"}] layer options. When two
            or more are given, a compact dropdown renders at the top of the
            legend body; one or none renders no dropdown.
        selected: The currently selected option value.
        event_set_selected: Callback when the user picks a different option.
        inline: Shorthand for ``placement="inline"``, read only when
            ``placement`` is None.
        placement: Where the legend sits:

            - ``"viewport"``: fixed bottom-center over the map area, between
              the ``MapApp`` drawer and panels it reads from CSS variables; the
              body scrolls past 40 % of the viewport's height.
            - ``"inline"``: in the normal flow at the width of its container,
              for a panel.
            - ``"map"``: in the normal flow, no wider or taller than its
              container, which positions it, e.g. a slot over the map. In a
              container whose height is capped, as a flex column with a
              ``max-height`` or with a set height, the body shrinks and scrolls.

            None means ``"inline"`` when ``inline`` is set, else ``"viewport"``.
        title: The shown layer's name, used when there is no dropdown.
        labels: The texts of the dropdown (``choose``) and of the bar
            (``show``, ``hide``). Missing keys use pysepal's translated messages.
    """
    strings = {
        "choose": msg("legend.choose"),
        "show": msg("legend.show"),
        "hide": msg("legend.hide"),
        **(labels or {}),
    }
    return _LegendTemplate(
        legend_data=legend_data,
        visible=visible,
        collapsed=collapsed,
        event_set_collapsed=event_set_collapsed,
        selector_options=selector_options,
        selected=selected,
        event_set_selected=event_set_selected,
        placement=placement or ("inline" if inline else "viewport"),
        title=title,
        labels=strings,
    )
