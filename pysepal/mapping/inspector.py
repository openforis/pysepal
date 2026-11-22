"""The map inspector: the values of every visible layer at a clicked point."""

import asyncio
import json
import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Optional

import traitlets
from pysepal_map import ClickEvent

from pysepal.layers import RenderLayer, local_fingerprint, uri_to_path
from pysepal.mapping.sepal_map import _METERS_PER_PX

if TYPE_CHECKING:
    from pysepal.mapping.sepal_map import SepalMap

__all__ = ["InspectedLayer", "Inspection", "MapInspector", "inspect_point"]

log = logging.getLogger("sepalui.mapping.inspector")

Status = Literal["ready", "empty", "changed", "error", "unsupported"]
_EE_COLLECTIONS = ("FeatureCollection", "Feature", "Geometry")
_NODATA = "nodata"


@dataclass(frozen=True)
class InspectedLayer:
    """What the inspector read from one layer."""

    layer_id: str
    name: str
    status: Status
    values: tuple[tuple[str, str], ...] = ()
    error: str = ""


@dataclass(frozen=True)
class Inspection:
    """The result of one click: ``scale`` is metres per pixel at the clicked view."""

    lng: float
    lat: float
    scale: float
    layers: tuple[InspectedLayer, ...]
    pending: bool


@dataclass(frozen=True)
class _Job:
    """A layer paired with its accepted entry, still to be read."""

    layer_id: str
    spec: Any
    render: RenderLayer
    hit: Optional[Any] = None


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return f"{value:.4f}".rstrip("0").rstrip(".") or "0"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


def _properties(props: Any) -> tuple[tuple[str, str], ...]:
    return tuple((str(k), _fmt(v)) for k, v in dict(props).items())


def _scale(event: ClickEvent) -> float:
    return _METERS_PER_PX * math.cos(math.radians(event.lat)) / 2**event.zoom


def _pair(map_: "SepalMap", event: ClickEvent) -> list:
    """Pair the published layers with the engine's accepted entries, with no await.

    Returns ``InspectedLayer`` for the rows already decided and ``_Job`` for those to read.
    """
    engine = map_.layer_engine
    rows: list = []
    for published in map_.state.get("layers", ()):
        if published["zone"] != "data" or not published["visible"]:
            continue
        layer_id, instance = published["id"], published["instance"]
        accepted = engine.accepted(layer_id)
        if accepted is None:
            rows.append(InspectedLayer(layer_id, layer_id, "changed"))
            continue
        spec, render = accepted
        changed = InspectedLayer(layer_id, spec.name, "changed")
        if engine.accepted_instance(layer_id) != instance:
            rows.append(changed)
        elif render.kind in ("geojson", "pmtiles"):
            rows.append(_vector_row(event, spec, instance, changed))
        elif spec.source.type == "tile":
            rows.append(InspectedLayer(layer_id, spec.name, "unsupported"))
        else:
            rows.append(_Job(layer_id, spec, render))
    return rows


def _vector_row(event: ClickEvent, spec, instance: int, changed: InspectedLayer):
    hits = [f for f in event.features if f.layer_id == spec.id]
    if spec.id in event.stale or any(f.instance != instance for f in hits):
        return changed
    if not hits:
        return InspectedLayer(spec.id, spec.name, "empty") if event.settled else changed
    return InspectedLayer(spec.id, spec.name, "ready", _properties(hits[0].properties))


async def _read_ee(map_: "SepalMap", job: _Job, event: ClickEvent) -> InspectedLayer:
    import ee

    point = ee.Geometry.Point([event.lng, event.lat])
    obj = job.render.ee_object
    if job.spec.source.kind in _EE_COLLECTIONS:
        query = obj.filterBounds(point).limit(1)
        info = await map_.gee_interface.get_info_async(query)
        features = (info or {}).get("features") or []
        if not features:
            return InspectedLayer(job.layer_id, job.spec.name, "empty")
        values = _properties(features[0].get("properties") or {})
    else:
        query = obj.reduceRegion(ee.Reducer.mean(), point, _scale(event))
        info = await map_.gee_interface.get_info_async(query)
        if not info:
            return InspectedLayer(job.layer_id, job.spec.name, "empty")
        values = tuple((str(k), _NODATA if v is None else _fmt(v)) for k, v in info.items())
    return InspectedLayer(job.layer_id, job.spec.name, "ready", values)


def _sample_raster(job: _Job, lng: float, lat: float) -> InspectedLayer:
    """Read every band at a point; runs in a thread."""
    import numpy as np
    import rasterio
    from rasterio.warp import transform
    from rasterio.windows import Window

    spec, render = job.spec, job.render
    if local_fingerprint(spec) != render.fingerprint:
        return InspectedLayer(job.layer_id, spec.name, "changed")
    with rasterio.open(uri_to_path(spec.source.uri)) as ds:
        if ds.crs:
            (x,), (y,) = transform("EPSG:4326", ds.crs, [lng], [lat])
        else:
            x, y = lng, lat
        row, col = ds.index(x, y)
        if not (0 <= row < ds.height and 0 <= col < ds.width):
            return InspectedLayer(job.layer_id, spec.name, "empty")
        data = ds.read(window=Window(col, row, 1, 1), masked=True)
        labels = [d or f"band {i}" for i, d in enumerate(ds.descriptions, 1)]
    values = tuple(
        (label, _NODATA if np.ma.is_masked(band[0, 0]) else _fmt(band[0, 0].item()))
        for label, band in zip(labels, data)
    )
    if local_fingerprint(spec) != render.fingerprint:
        return InspectedLayer(job.layer_id, spec.name, "changed")
    return InspectedLayer(job.layer_id, spec.name, "ready", values)


async def _read(map_: "SepalMap", row, event: ClickEvent) -> InspectedLayer:
    if isinstance(row, InspectedLayer):
        return row
    try:
        if row.spec.source.type == "gee":
            return await _read_ee(map_, row, event)
        return await asyncio.to_thread(_sample_raster, row, event.lng, event.lat)
    except Exception as exc:
        log.debug("inspecting %s failed", row.layer_id, exc_info=True)
        return InspectedLayer(row.layer_id, row.spec.name, "error", error=str(exc))


async def inspect_point(
    map_: "SepalMap", event: ClickEvent, rows: Optional[list] = None
) -> list[InspectedLayer]:
    """Read the visible data layers at a click, top first.

    Args:
        map_: the map.
        event: the click; its zoom gives the scale.
        rows: the layers :func:`_pair` returned when the click was accepted; paired now
            when omitted.

    Returns:
        One ``InspectedLayer`` per visible data layer; a failure stays in its own layer.
    """
    rows = _pair(map_, event) if rows is None else rows
    return list(await asyncio.gather(*(_read(map_, row, event) for row in rows)))


class MapInspector(traitlets.HasTraits):
    """The one inspector of a map: it owns the cursor, the marker and the click callback."""

    active = traitlets.Bool(False)
    inspection = traitlets.Instance(Inspection, allow_none=True)

    def __init__(self, map_: "SepalMap") -> None:
        """Create an inactive inspector for ``map_``."""
        super().__init__()
        self._map = map_
        self._generation = 0
        self._task: Optional[asyncio.Task] = None

    def activate(self) -> None:
        """Start reading values on click and show the crosshair."""
        if self.active:
            return
        self._map.on_click(self._on_click)
        self._map.cursor = "crosshair"
        self.active = True

    def deactivate(self) -> None:
        """Stop, drop the running inspection and clear the marker and the cursor."""
        self._map.on_click(self._on_click, remove=True)
        self._generation += 1
        self._cancel()
        self._map.clear_marker()
        self._map.cursor = ""
        self.active = False
        self.inspection = None

    def close(self) -> None:
        """Deactivate; the map calls it when it closes."""
        self.deactivate()

    def _cancel(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def _on_click(self, event: ClickEvent) -> None:
        if not self.active:
            return
        # pairing happens now: what a later await sees may already be another instance
        rows = _pair(self._map, event)
        self._cancel()
        self._generation += 1
        generation, scale = self._generation, _scale(event)
        self._map.set_marker(event.lng, event.lat)
        self.inspection = Inspection(event.lng, event.lat, scale, (), True)
        loop = getattr(self._map, "loop", None) or asyncio.get_running_loop()
        self._task = loop.create_task(self._run(generation, event, rows, scale))

    async def _run(self, generation: int, event: ClickEvent, rows: list, scale: float) -> None:
        try:
            layers = await inspect_point(self._map, event, rows)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("inspecting a point failed")
            layers = []
        if generation == self._generation and self.active:
            self.inspection = Inspection(event.lng, event.lat, scale, tuple(layers), False)
