/// <reference types="geojson" />
import type {
  GeoJSONSourceSpecification,
  LayerSpecification,
  SourceSpecification,
} from "maplibre-gl";

import type { OwnedSource, OwnedSourceSpec, OwnedStyle } from "./types";

export const OWNED_PREFIX = "psm:";

const isOwned = (id: string): boolean => id.startsWith(OWNED_PREFIX);

/**
 * The view of a map the reconciler reads and changes. `layer` and `source`
 * return definitions as they were set (MapLibre's `serialize`), without
 * defaults filled in; a GeoJSON source may include its `data`, which the
 * reconciler never reads. Only owned ids are ever passed to `layer` and
 * `source`: MapLibre throws when it serializes a custom layer.
 */
export interface LiveMap {
  layerOrder(): string[]; // every layer in the style, bottom-first
  layer(id: string): LayerSpecification | undefined;
  source(id: string): SourceSpecification | undefined;
  sourceIds(): string[];
  addSource(id: string, spec: SourceSpecification): void;
  removeSource(id: string): void;
  setTiles(id: string, tiles: string[]): void;
  addLayer(spec: LayerSpecification, beforeId?: string): void;
  removeLayer(id: string): void;
  moveLayer(id: string, beforeId?: string): void;
  setLayout(id: string, name: string, value: unknown): void;
  setPaint(id: string, name: string, value: unknown): void;
  setFilter(id: string, filter: unknown): void;
  setZoomRange(id: string, min: number, max?: number): void;
}

/** One style change. A `null` value or filter resets it to the default. */
export type Op =
  | { kind: "addSource"; id: string; spec: OwnedSourceSpec; digest?: string }
  | { kind: "removeSource"; id: string }
  | { kind: "setTiles"; id: string; tiles: string[] }
  | { kind: "addLayer"; layer: LayerSpecification; beforeId?: string }
  | { kind: "removeLayer"; id: string }
  | { kind: "moveLayer"; id: string; beforeId?: string }
  | { kind: "setLayout"; id: string; name: string; value: unknown }
  | { kind: "setPaint"; id: string; name: string; value: unknown }
  | { kind: "setFilter"; id: string; filter: unknown }
  | { kind: "setZoomRange"; id: string; min: number; max?: number };

export type ResolvePayload = (digest: string) => GeoJSON.GeoJSON;

type Json = Record<string, unknown>;

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || !a || !b) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  if (Array.isArray(a)) {
    const other = b as unknown[];
    return (
      a.length === other.length && a.every((v, i) => deepEqual(v, other[i]))
    );
  }
  const left = defined(a as Json);
  const right = defined(b as Json);
  const keys = Object.keys(left);
  return (
    keys.length === Object.keys(right).length &&
    keys.every((key) => key in right && deepEqual(left[key], right[key]))
  );
}

const defined = (object: Json): Json =>
  Object.fromEntries(Object.entries(object).filter(([, v]) => v !== undefined));

/** Source options without GeoJSON worker data, which is never compared. */
function sourceOptions(spec: object): Json {
  const out: Json = {};
  const geojson = (spec as Json).type === "geojson";
  for (const key of Object.keys(spec)) {
    if (geojson && key === "data") continue;
    const value = (spec as Json)[key];
    if (value !== undefined) out[key] = value;
  }
  return out;
}

type SourceChange = "none" | "tiles" | "replace";

function compareSource(live: object, desired: object): SourceChange {
  const a = sourceOptions(live);
  const b = sourceOptions(desired);
  if (deepEqual(a, b)) return "none";
  if (Array.isArray(a.tiles) && Array.isArray(b.tiles)) {
    const { tiles: _a, ...restA } = a;
    const { tiles: _b, ...restB } = b;
    if (deepEqual(restA, restB)) return "tiles";
  }
  return "replace";
}

/** Layout or paint as MapLibre renders it: unset values and defaults dropped. */
function properties(
  layer: LayerSpecification,
  group: "layout" | "paint"
): Json {
  const out: Json = {};
  const values = ((layer as Json)[group] ?? {}) as Json;
  for (const [name, value] of Object.entries(values)) {
    if (value == null) continue;
    if (group === "layout" && name === "visibility" && value === "visible") {
      continue;
    }
    out[name] = value;
  }
  return out;
}

const field = (layer: LayerSpecification, key: string): unknown =>
  (layer as Json)[key] ?? undefined;

/**
 * Whether the live layer cannot be changed into the desired one in place.
 * MapLibre has no setter for type, source or source layer, and its
 * setLayerZoomRange ignores a missing bound, so it cannot clear a max zoom.
 */
function needsRecreate(live: LayerSpecification, desired: LayerSpecification) {
  return (
    live.type !== desired.type ||
    field(live, "source") !== field(desired, "source") ||
    field(live, "source-layer") !== field(desired, "source-layer") ||
    (desired.maxzoom == null && live.maxzoom != null)
  );
}

function diffLayer(
  ops: Op[],
  live: LayerSpecification,
  desired: LayerSpecification
) {
  const id = desired.id;
  for (const group of ["layout", "paint"] as const) {
    const kind = group === "layout" ? "setLayout" : "setPaint";
    const have = properties(live, group);
    const want = properties(desired, group);
    for (const name of new Set([...Object.keys(have), ...Object.keys(want)])) {
      if (deepEqual(have[name], want[name])) continue;
      const raw = ((desired as Json)[group] as Json | undefined)?.[name];
      ops.push({ kind, id, name, value: raw ?? null });
    }
  }
  const filter = field(desired, "filter");
  if (!deepEqual(field(live, "filter"), filter)) {
    ops.push({ kind: "setFilter", id, filter: filter ?? null });
  }
  const min = desired.minzoom ?? 0;
  const max = desired.maxzoom ?? undefined;
  if ((live.minzoom ?? 0) !== min || (live.maxzoom ?? undefined) !== max) {
    ops.push(
      max === undefined
        ? { kind: "setZoomRange", id, min }
        : { kind: "setZoomRange", id, min, max }
    );
  }
}

function addSourceOp(source: OwnedSource): Op {
  if (source.spec.type !== "geojson") {
    return { kind: "addSource", id: source.id, spec: source.spec };
  }
  if (!source.digest) {
    throw new Error(`GeoJSON source "${source.id}" has no payload digest`);
  }
  return {
    kind: "addSource",
    id: source.id,
    spec: source.spec,
    digest: source.digest,
  };
}

function checkDesired(desired: OwnedStyle): void {
  const sources = new Set<string>();
  for (const { id } of desired.sources) {
    if (!isOwned(id) || sources.has(id)) {
      throw new Error(
        `desired source "${id}" must be unique and start with ${OWNED_PREFIX}`
      );
    }
    sources.add(id);
  }
  const layers = new Set<string>();
  for (const layer of desired.layers) {
    if (!isOwned(layer.id) || layers.has(layer.id)) {
      throw new Error(
        `desired layer "${layer.id}" must be unique and start with ${OWNED_PREFIX}`
      );
    }
    const source = field(layer, "source");
    if (typeof source !== "string" || !sources.has(source)) {
      throw new Error(`desired layer "${layer.id}" uses an undeclared source`);
    }
    layers.add(layer.id);
  }
}

/**
 * The operations that turn the owned part of `live` into `desired`
 * (layers bottom-first). Ids without the owned prefix are never touched,
 * and every owned layer ends up below the lowest foreign layer. The plan
 * runs against a working copy of the layer order so each operation sees
 * the effect of the ones before it.
 */
export function plan(live: LiveMap, desired: OwnedStyle): Op[] {
  checkDesired(desired);
  const ops: Op[] = [];
  const order = live.layerOrder();
  const wantSources = new Map(desired.sources.map((s) => [s.id, s]));
  const wantLayers = new Map(desired.layers.map((l) => [l.id, l]));

  // 1. Sources: keep, retile in place, or retire (removed or replaced).
  const liveSources = new Set<string>();
  const retired = new Set<string>();
  const additions: OwnedSource[] = [];
  const retiles: Op[] = [];
  for (const id of live.sourceIds()) {
    if (!isOwned(id)) continue;
    liveSources.add(id);
    const want = wantSources.get(id);
    if (!want) {
      retired.add(id);
      continue;
    }
    const change = compareSource(live.source(id)!, want.spec);
    if (change === "tiles") {
      const tiles = (want.spec as { tiles: string[] }).tiles;
      retiles.push({ kind: "setTiles", id, tiles });
    } else if (change === "replace") {
      retired.add(id);
      additions.push(want);
    }
  }
  for (const source of desired.sources) {
    if (!liveSources.has(source.id)) additions.push(source);
  }

  // 2. A source can only go once no layer uses it, and a layer can only
  // come once its source exists: remove layers, then sources, then add.
  const kept = new Map<string, LayerSpecification>();
  for (const id of order.filter(isOwned)) {
    const layer = live.layer(id)!;
    const want = wantLayers.get(id);
    const source = field(layer, "source");
    if (
      !want ||
      (typeof source === "string" && retired.has(source)) ||
      needsRecreate(layer, want)
    ) {
      ops.push({ kind: "removeLayer", id });
      order.splice(order.indexOf(id), 1);
    } else {
      kept.set(id, layer);
    }
  }
  for (const id of retired) ops.push({ kind: "removeSource", id });
  for (const source of additions) ops.push(addSourceOp(source));
  ops.push(...retiles);

  // 3. Place the layers top-down, each directly below the one placed before
  // it, starting below the lowest foreign layer (or at the top without
  // one). Every owned layer left in the order is desired, so once the walk
  // ends they form one block, in order, under every foreign layer.
  let anchor: string | undefined = order.find((id) => !isOwned(id));
  for (let i = desired.layers.length - 1; i >= 0; i--) {
    const layer = desired.layers[i];
    const at = order.indexOf(layer.id);
    const target = anchor === undefined ? order.length : order.indexOf(anchor);
    if (at === -1) {
      ops.push({ kind: "addLayer", layer, beforeId: anchor });
      order.splice(target, 0, layer.id);
    } else if (at !== target - 1) {
      ops.push({ kind: "moveLayer", id: layer.id, beforeId: anchor });
      order.splice(at, 1);
      order.splice(at < target ? target - 1 : target, 0, layer.id);
    }
    anchor = layer.id;
  }

  // 4. Properties of the layers that were kept rather than added.
  for (const layer of desired.layers) {
    const current = kept.get(layer.id);
    if (current) diffLayer(ops, current, layer);
  }
  return ops;
}

/** Run `ops` in order; a GeoJSON source is added with its resolved payload. */
export function apply(
  live: LiveMap,
  ops: Op[],
  resolvePayload: ResolvePayload
): void {
  // Resolve first, so a missing payload fails before the map changes.
  const payloads = new Map<Op, GeoJSON.GeoJSON>();
  for (const op of ops) {
    if (op.kind === "addSource" && op.spec.type === "geojson") {
      if (!op.digest) {
        throw new Error(`GeoJSON source "${op.id}" has no payload digest`);
      }
      payloads.set(op, resolvePayload(op.digest));
    }
  }
  for (const op of ops) {
    switch (op.kind) {
      case "addSource": {
        const data = payloads.get(op);
        const spec = data
          ? ({ ...op.spec, data } as GeoJSONSourceSpecification)
          : (op.spec as SourceSpecification);
        live.addSource(op.id, spec);
        break;
      }
      case "removeSource":
        live.removeSource(op.id);
        break;
      case "setTiles":
        live.setTiles(op.id, op.tiles);
        break;
      case "addLayer":
        live.addLayer(op.layer, op.beforeId);
        break;
      case "removeLayer":
        live.removeLayer(op.id);
        break;
      case "moveLayer":
        live.moveLayer(op.id, op.beforeId);
        break;
      case "setLayout":
        live.setLayout(op.id, op.name, op.value);
        break;
      case "setPaint":
        live.setPaint(op.id, op.name, op.value);
        break;
      case "setFilter":
        live.setFilter(op.id, op.filter);
        break;
      case "setZoomRange":
        live.setZoomRange(op.id, op.min, op.max);
        break;
    }
  }
}

/**
 * Bring the owned part of `live` to `available`: the desired style limited
 * to the sources whose payloads are at hand, and their layers.
 */
export function reconcile(
  live: LiveMap,
  available: OwnedStyle,
  resolvePayload: ResolvePayload
): void {
  apply(live, plan(live, available), resolvePayload);
}
