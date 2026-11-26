"""The events a map sends to Python."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FeatureHit:
    """A rendered feature under a click.

    ``instance`` is the widget instance of the layer the hit was on, so a
    reader can tell it from a replacement of the same layer id.
    """

    layer_id: str
    instance: int
    properties: Mapping[str, Any]


@dataclass(frozen=True)
class ClickEvent:
    """A click on one view.

    ``zoom`` is that view's zoom. ``settled`` says the view had reconciled its
    latest state, every GeoJSON payload loaded. ``features`` are the hits on
    current layer instances, top first, on the map shown at the click. In
    compare, ``hidden_features`` holds the hits of the other map, the one the
    shown half covers there, in the same form; it is empty outside compare.
    ``stale`` holds the ids of layers whose hits, in either, were dropped
    because they were on a retired instance.
    """

    lng: float
    lat: float
    zoom: float
    settled: bool
    features: tuple[FeatureHit, ...]
    stale: frozenset[str]
    view_id: str
    hidden_features: tuple[FeatureHit, ...] = ()

    def hits(self, layer_id: str) -> tuple[Mapping[str, Any], ...]:
        """The properties of the features hit on ``layer_id``, top first."""
        return tuple(f.properties for f in self.features if f.layer_id == layer_id)
