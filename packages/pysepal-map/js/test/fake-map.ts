import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type {
  LayerSpecification,
  SourceSpecification,
  StyleSpecification,
} from "maplibre-gl";

import type { LiveMap } from "../reconcile";

/** A mutating call, logged so tests can check what was touched. */
export interface Call {
  method: string;
  id: string;
  beforeId?: string;
}

type Spec = Record<string, any>;

const clone = <T>(value: T): T => structuredClone(value);

const EMPTY_GEOJSON = { type: "FeatureCollection", features: [] };

const TILED = new Set(["raster", "raster-dem", "vector"]);

// The reconciler must never read GeoJSON worker data: any access throws.
const PAYLOAD_TRIPWIRE: unknown = new Proxy(
  {},
  {
    get: () => {
      throw new Error("the payload of a live GeoJSON source was read");
    },
    has: () => {
      throw new Error("the payload of a live GeoJSON source was read");
    },
    ownKeys: () => {
      throw new Error("the payload of a live GeoJSON source was read");
    },
  }
);

const withoutData = ({ data: _data, ...rest }: Spec): Spec => rest;

/** Mirror StyleLayer.serialize: unset values and empty groups disappear. */
function serializeLayer(layer: Spec): LayerSpecification {
  const out: Spec = {};
  for (const [key, value] of Object.entries(layer)) {
    if (value === undefined) continue;
    if (key === "layout" || key === "paint") {
      const group = Object.fromEntries(
        Object.entries(value as Spec).filter(([, v]) => v != null)
      );
      if (Object.keys(group).length) out[key] = group;
      continue;
    }
    out[key] = value;
  }
  return out as LayerSpecification;
}

/**
 * A strict, in-memory `LiveMap` that follows MapLibre 6's `Style` where the
 * reconciler depends on it, but throws where MapLibre only fires an error
 * event, so a bad operation fails the test that caused it. Every source and
 * layer is checked with the style-spec validator.
 */
export class FakeMap implements LiveMap {
  readonly calls: Call[] = [];
  private order: string[] = [];
  private layers = new Map<string, Spec>();
  private sources = new Map<string, Spec>();

  constructor(
    init: {
      sources?: Record<string, SourceSpecification>;
      layers?: LayerSpecification[];
    } = {}
  ) {
    for (const [id, spec] of Object.entries(init.sources ?? {})) {
      this.addSource(id, spec);
    }
    for (const layer of init.layers ?? []) this.addLayer(layer);
    this.calls.length = 0;
  }

  layerOrder(): string[] {
    return [...this.order];
  }

  layer(id: string): LayerSpecification | undefined {
    const layer = this.layers.get(id);
    return layer && (clone(layer) as LayerSpecification);
  }

  source(id: string): SourceSpecification | undefined {
    const source = this.sources.get(id);
    if (!source) return undefined;
    const out = clone(withoutData(source));
    if ("data" in source) out.data = PAYLOAD_TRIPWIRE;
    return out as SourceSpecification;
  }

  sourceIds(): string[] {
    return [...this.sources.keys()];
  }

  /** The stored source definition without its data, for assertions. */
  sourceSpec(id: string): Spec | undefined {
    const source = this.sources.get(id);
    return source && clone(withoutData(source));
  }

  /** The data object a GeoJSON source was added with. */
  payload(id: string): unknown {
    return this.sources.get(id)?.data;
  }

  addSource(id: string, spec: SourceSpecification): void {
    this.log("addSource", id);
    if (this.sources.has(id)) throw new Error(`Source "${id}" already exists.`);
    if (!spec.type) throw new Error(`Source "${id}" has no type.`);
    const stored: Spec = clone(withoutData(spec));
    if ("data" in spec) stored.data = spec.data;
    this.validate({ [id]: this.forValidation(stored) }, []);
    this.sources.set(id, stored);
  }

  removeSource(id: string): void {
    this.log("removeSource", id);
    if (!this.sources.has(id)) {
      throw new Error(`There is no source with this ID=${id}`);
    }
    for (const [layerId, layer] of this.layers) {
      if (layer.source === id) {
        throw new Error(
          `Source "${id}" cannot be removed while layer "${layerId}" is using it.`
        );
      }
    }
    this.sources.delete(id);
  }

  setTiles(id: string, tiles: string[]): void {
    this.log("setTiles", id);
    const source = this.sources.get(id);
    if (!source) throw new Error(`There is no source with this ID=${id}`);
    if (!TILED.has(source.type)) {
      throw new Error(`Source "${id}" of type ${source.type} has no tiles.`);
    }
    source.tiles = [...tiles];
  }

  addLayer(spec: LayerSpecification, beforeId?: string): void {
    this.log("addLayer", spec.id, beforeId);
    if (this.layers.has(spec.id)) {
      throw new Error(`Layer "${spec.id}" already exists on this map.`);
    }
    const layer = serializeLayer(clone(spec));
    this.validateLayer(layer);
    if (beforeId && !this.order.includes(beforeId)) {
      throw new Error(
        `Cannot add layer "${spec.id}" before non-existing layer "${beforeId}".`
      );
    }
    const index = beforeId ? this.order.indexOf(beforeId) : this.order.length;
    this.order.splice(index, 0, spec.id);
    this.layers.set(spec.id, layer);
  }

  removeLayer(id: string): void {
    this.log("removeLayer", id);
    if (!this.layers.has(id)) {
      throw new Error(`Cannot remove non-existing layer "${id}".`);
    }
    this.layers.delete(id);
    this.order.splice(this.order.indexOf(id), 1);
  }

  moveLayer(id: string, beforeId?: string): void {
    this.log("moveLayer", id, beforeId);
    if (!this.layers.has(id)) {
      throw new Error(`The layer '${id}' does not exist and cannot be moved.`);
    }
    if (id === beforeId) return;
    if (beforeId && !this.order.includes(beforeId)) {
      throw new Error(
        `Cannot move layer "${id}" before non-existing layer "${beforeId}".`
      );
    }
    this.order.splice(this.order.indexOf(id), 1);
    const index = beforeId ? this.order.indexOf(beforeId) : this.order.length;
    this.order.splice(index, 0, id);
  }

  setLayout(id: string, name: string, value: unknown): void {
    this.log("setLayout", id);
    this.update(id, (layer) => {
      layer.layout = { ...layer.layout, [name]: clone(value) };
    });
  }

  setPaint(id: string, name: string, value: unknown): void {
    this.log("setPaint", id);
    this.update(id, (layer) => {
      layer.paint = { ...layer.paint, [name]: clone(value) };
    });
  }

  setFilter(id: string, filter: unknown): void {
    this.log("setFilter", id);
    this.update(id, (layer) => {
      layer.filter = filter == null ? undefined : clone(filter);
    });
  }

  // Like Style.setLayerZoomRange, a missing bound leaves the current one.
  setZoomRange(id: string, min: number, max?: number): void {
    this.log("setZoomRange", id);
    this.update(id, (layer) => {
      if (min != null) layer.minzoom = min;
      if (max != null) layer.maxzoom = max;
    });
  }

  private log(method: string, id: string, beforeId?: string): void {
    this.calls.push(
      beforeId === undefined ? { method, id } : { method, id, beforeId }
    );
  }

  private update(id: string, mutate: (layer: Spec) => void): void {
    const current = this.layers.get(id);
    if (!current) throw new Error(`Cannot style non-existing layer "${id}".`);
    const next = clone(current);
    mutate(next);
    const layer = serializeLayer(next);
    this.validateLayer(layer);
    this.layers.set(id, layer);
  }

  private validateLayer(layer: Spec): void {
    const source = this.sources.get(layer.source);
    if (!source) {
      throw new Error(
        `Layer "${layer.id}": source "${layer.source}" not found.`
      );
    }
    this.validate({ [layer.source]: this.forValidation(source) }, [layer]);
  }

  private forValidation(source: Spec): Spec {
    return "data" in source
      ? { ...withoutData(source), data: EMPTY_GEOJSON }
      : source;
  }

  private validate(sources: Spec, layers: Spec[]): void {
    const style = { version: 8, sources, layers } as StyleSpecification;
    const errors = validateStyleMin(style);
    if (errors.length) {
      throw new Error(errors.map((error) => error.message).join("; "));
    }
  }
}
