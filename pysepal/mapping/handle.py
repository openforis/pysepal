"""Live handles to layers held by a map's ``LayerStore``."""

from typing import TYPE_CHECKING, Any, Literal

from pysepal_map import Side

from pysepal.layers import LayerSpec, LayerStore

if TYPE_CHECKING:
    from .sepal_map import SepalMap

__all__ = ["LayerGoneError", "LayerHandle", "ZoomResult"]

ZoomResult = Literal["moved", "preparing", "no_bounds", "failed", "missing", "superseded"]


class LayerGoneError(KeyError):
    """The layer is no longer on the map."""

    def __init__(self, layer_id: str) -> None:
        """Build the message from the id."""
        super().__init__(f"Layer {layer_id!r} is no longer on the map")
        self.layer_id = layer_id

    def __str__(self) -> str:
        """Return the plain message, not the KeyError repr."""
        return self.args[0]


class LayerHandle:
    """A live view of one layer: it holds the map and the id, never a copy of the state."""

    def __init__(self, map_: "SepalMap", layer_id: str) -> None:
        """Hold the map and the id; the store is read once."""
        self._map = map_
        self.id = layer_id
        self.store: LayerStore = map_.layer_store

    @property
    def alive(self) -> bool:
        """Whether the id is in the store."""
        return self.id in self.store

    def _check(self) -> None:
        if self.id not in self.store:
            raise LayerGoneError(self.id)

    @property
    def spec(self) -> LayerSpec:
        """A copy of the current spec."""
        self._check()
        return self.store.get(self.id)

    @property
    def name(self) -> str:
        """The layer name."""
        return self.spec.name

    @property
    def visible(self) -> bool:
        """Whether the layer is shown."""
        self._check()
        return self.store.view(self.id).visible

    @visible.setter
    def visible(self, value: bool) -> None:
        """Show or hide the layer."""
        self._check()
        self.store.set_visible(self.id, value)

    @property
    def opacity(self) -> float:
        """The layer opacity."""
        self._check()
        return self.store.view(self.id).opacity

    @opacity.setter
    def opacity(self, value: float) -> None:
        """Set the layer opacity."""
        self._check()
        self.store.set_opacity(self.id, value)

    @property
    def side(self) -> Side:
        """The half of a compare map that draws the layer."""
        self._check()
        return self.store.view(self.id).side

    @side.setter
    def side(self, value: Side) -> None:
        """Set the half of a compare map that draws the layer."""
        self._check()
        self.store.set_side(self.id, value)

    @property
    def status(self) -> str:
        """The preparation status."""
        self._check()
        return self.store.view(self.id).status

    @property
    def error(self) -> str:
        """The preparation error message, if any."""
        self._check()
        return self.store.view(self.id).error

    def restyle(self, **changes: Any) -> LayerSpec:
        """Apply changes to the spec through the store."""
        self._check()
        return self.store.restyle(self.id, **changes)

    def zoom(self, zoom_out: int = 1) -> ZoomResult:
        """Move the camera to the layer."""
        self._check()
        return self._map.zoom_layer(self.id, zoom_out)

    async def zoom_async(self, zoom_out: int = 1) -> ZoomResult:
        """Move the camera to the layer without blocking."""
        self._check()
        return await self._map.zoom_layer_async(self.id, zoom_out)

    def remove(self) -> None:
        """Remove the layer from the map."""
        self._check()
        self.store.remove(self.id)

    def __eq__(self, other: object) -> bool:
        """Equal when both name the same id in the same store."""
        if not isinstance(other, LayerHandle):
            return NotImplemented
        return self.store is other.store and self.id == other.id

    def __hash__(self) -> int:
        """Hash by store identity and id."""
        return hash((id(self.store), self.id))

    def __repr__(self) -> str:
        """Show the id."""
        return f"LayerHandle({self.id!r})"
