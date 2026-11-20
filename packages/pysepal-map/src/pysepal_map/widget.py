"""The MapLibre map widget."""

from __future__ import annotations

import hashlib
from pathlib import Path

import anywidget
import traitlets

from .state import GeoJSONSource, MapState

_STATIC = Path(__file__).parent / "static"


class MapWidget(anywidget.AnyWidget):
    """A MapLibre map whose persistent configuration lives in ``state``."""

    _esm = _STATIC / "widget.js"
    _css = _STATIC / "widget.css"

    state = traitlets.Dict().tag(sync=True)
    view = traitlets.Dict().tag(sync=True)
    view_request = traitlets.Dict().tag(sync=True)
    height = traitlets.Unicode("400px").tag(sync=True)

    def __init__(self, *, height: str = "400px", **kwargs):
        super().__init__(height=height, **kwargs)
        self._payloads: dict[str, bytes] = {}
        self._revision = 0
        self._next_instance = 1
        # id -> (identity, instance) of the last published snapshot
        self._instances: dict[str, tuple[tuple, int]] = {}

    def add_payload(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        self._payloads[digest] = bytes(data)
        return digest

    def draw(self, state: MapState) -> None:
        """Publish ``state`` as the next snapshot; a failure changes nothing."""
        if not isinstance(state, MapState):
            raise TypeError("draw expects a MapState")
        referenced = {
            layer.source.digest
            for layer in state.layers
            if isinstance(layer.source, GeoJSONSource)
        }
        missing = sorted(referenced - self._payloads.keys())
        if missing:
            raise KeyError(f"payloads never added: {', '.join(missing)}")

        data = state.to_json()
        instances: dict[str, tuple[tuple, int]] = {}
        next_instance = self._next_instance
        for layer, entry in zip(state.layers, data["layers"]):
            identity = (layer.source, layer.attribution, layer.token)
            previous = self._instances.get(layer.id)
            if previous is not None and previous[0] == identity:
                instance = previous[1]
            else:
                instance = next_instance
                next_instance += 1
            instances[layer.id] = (identity, instance)
            entry["instance"] = instance
        data["revision"] = self._revision + 1

        self._instances = instances
        self._next_instance = next_instance
        self._revision += 1
        self.state = data
        self._payloads = {d: b for d, b in self._payloads.items() if d in referenced}
