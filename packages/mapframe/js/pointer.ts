import type { Point } from "maplibre-gl";

import { parseSourceId, sourceId } from "./translate";
import type { LayerState, MapState } from "./types";

/** Where the browser reports a click, and what a hit may carry at most. */
const PER_LAYER = 5;
const IN_ALL = 20;

/** The parts of an owned vector layer that a click can hit. */
const HIT_PART = /^mapframe:[^:]+:\d+:(fill|line|circle|pin|cluster)$/;

/**
 * The owned vector style layers in the live style, optionally of some logical
 * layers: a query may name only layers MapLibre has, or it rejects it whole.
 * Cluster layers are left out unless `clusters` asks for them, alone or too.
 */
export function ownedStyleLayers(
  map: Pick<PointerMap, "getLayersOrder" | "getLayer">,
  wanted?: (layerId: string) => boolean,
  clusters: "exclude" | "include" | "only" = "exclude"
): string[] {
  return map.getLayersOrder().filter((id) => {
    if (!HIT_PART.test(id) || !map.getLayer(id)) return false;
    const cluster = id.endsWith(":cluster");
    if (cluster ? clusters === "exclude" : clusters === "only") return false;
    const parsed = parseSourceId(id);
    return parsed !== null && (!wanted || wanted(parsed.id));
  });
}

/** `lng` brought into [-180, 180]. */
export function wrapLng(lng: number): number {
  if (lng >= -180 && lng <= 180) return lng;
  return ((((lng + 180) % 360) + 360) % 360) - 180;
}

/** What a view reads of a rendered feature. */
export interface RenderedFeature {
  id?: string | number;
  source: string;
  properties?: Record<string, unknown> | null;
  geometry?: { type?: string; coordinates?: unknown };
}

/** How far from the pointer, in px, a feature counts when none is under it. */
export const HIT_TOLERANCE_PX = 3;

/** The part of a map a hit test reads. */
export interface QueryMap {
  queryRenderedFeatures(
    geometry: Point | [[number, number], [number, number]],
    options: { layers: string[] }
  ): RenderedFeature[];
}

/**
 * The features of `layers` under `point`, top first, else those within
 * `HIT_TOLERANCE_PX` of it, so a thin line or a small point can be hit.
 */
export function queryNear(
  map: QueryMap,
  point: Point,
  layers: string[]
): RenderedFeature[] {
  if (!layers.length) return [];
  const under = map.queryRenderedFeatures(point, { layers });
  if (under.length) return under;
  const t = HIT_TOLERANCE_PX;
  const box: [[number, number], [number, number]] = [
    [point.x - t, point.y - t],
    [point.x + t, point.y + t],
  ];
  return map.queryRenderedFeatures(box, { layers });
}

/** Whether a rendered feature is a cluster bubble of a clustered source. */
export const isCluster = (feature: Pick<RenderedFeature, "properties">) =>
  feature.properties?.cluster === true;

interface PointerEvent {
  point: Point;
  lngLat: { lng: number; lat: number };
  originalEvent?: unknown;
}

/** The part of a MapLibre map the pointer rules use. */
export interface PointerMap extends QueryMap {
  getLayersOrder(): string[];
  getLayer(id: string): unknown;
  getSource(
    id: string
  ):
    | { type?: string; getClusterExpansionZoom?(id: number): Promise<number> }
    | undefined;
  getZoom(): number;
  getCanvas(): { style: { cursor: string } };
  easeTo(
    options: { center: [number, number]; zoom: number },
    eventData?: unknown
  ): unknown;
  on(type: string, listener: (event: any) => void): unknown;
  off(type: string, listener: (event: any) => void): unknown;
}

export interface MarkerLike {
  setLngLat(lnglat: [number, number]): unknown;
  addTo(map: any): unknown;
  remove(): unknown;
}

export interface PointerModel {
  get(name: "cursor" | "marker" | "state"): unknown;
  on(name: string, callback: () => void): void;
  off(name: string, callback: () => void): void;
}

export interface PointerOptions {
  map: PointerMap;
  model: PointerModel;
  /** The guarded sender: a closed comm must not abort MapLibre's click dispatch. */
  send(content: unknown): boolean | void;
  viewId: string;
  side: string;
  /** Whether the latest state is on the map, every GeoJSON payload loaded. */
  settled(): boolean;
  /** Whether drawing is interactive: clicks and the cursor are then its own. */
  drawing?(): boolean;
  /** Whether a layer shows a popup, a tooltip or clusters: its features take `pointer`. Read on every move and state change. */
  clickable?(layerId: string): boolean;
  /** Whether a layer shows cluster bubbles: a click on one zooms in, so they take `pointer`. */
  clustered?(layerId: string): boolean;
  /**
   * The map shown at a point of an event, `map` by default. What lies under
   * the pointer is read from it; events, the cursor, the marker and the
   * camera stay on `map`.
   */
  pick?(point: { x: number; y: number }): PointerMap;
  /**
   * In compare, the map the shown one covers at a point; null outside it. A
   * click sends its hits apart, so a reader can tell what the other half has.
   */
  hidden?(point: { x: number; y: number }): PointerMap | null;
  createMarker(color: string): MarkerLike;
}

export interface Hit {
  id: string;
  instance: number;
  properties: Record<string, unknown>;
}

/**
 * The pointer of one view: clicks with the features under them, the canvas
 * cursor and the highlight marker.
 */
export class ViewPointer {
  private marker: MarkerLike | null = null;
  private markerColor = "";
  private over = false;
  /** Where the pointer is on the map, null once it left. */
  private at: Point | null = null;
  private disposed = false;
  /** The cluster expansion waiting for MapLibre; a newer click cancels it. */
  private expansion: { cancel(): void } | null = null;

  constructor(private readonly options: PointerOptions) {
    const { map, model } = options;
    map.on("click", this.onClick);
    map.on("mousemove", this.onMove);
    map.on("mouseout", this.onOut);
    model.on("change:cursor", this.applyCursor);
    model.on("change:marker", this.applyMarker);
    model.on("change:state", this.onState);
    this.applyCursor();
    this.applyMarker();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.expansion?.cancel();
    const { map, model } = this.options;
    map.off("click", this.onClick);
    map.off("mousemove", this.onMove);
    map.off("mouseout", this.onOut);
    model.off("change:cursor", this.applyCursor);
    model.off("change:marker", this.applyMarker);
    model.off("change:state", this.onState);
    this.marker?.remove();
    this.marker = null;
  }

  /**
   * Drawing became interactive or stopped being so. Back from it, the cursor
   * rule applies again: Terra Draw leaves its own cursor on the canvas.
   */
  drawingChanged(): void {
    if (!this.disposed) this.applyCursor();
  }

  /** The hits at a point, top first, capped per layer and in all. */
  hitsAt(point: Point): Hit[] {
    const map = this.pick(point);
    return this.hitsOf(map, this.rendered(map, point));
  }

  private pick(point: Point): PointerMap {
    return this.options.pick?.(point) ?? this.options.map;
  }

  /** The rendered features of the owned vector layers, clusters too. */
  private rendered(map: PointerMap, point: Point): RenderedFeature[] {
    return queryNear(map, point, ownedStyleLayers(map, undefined, "include"));
  }

  private hitsOf(map: PointerMap, features: RenderedFeature[]): Hit[] {
    const perLayer = new Map<string, number>();
    const seen = new Set<string>();
    const hits: Hit[] = [];
    for (const feature of features) {
      if (isCluster(feature)) continue;
      const parsed = parseSourceId(feature.source);
      if (!parsed) continue;
      // MapLibre returns a GeoJSON feature once per tile it crosses; its
      // generated id is unique within its source. Vector tile ids may not be.
      if (
        feature.id !== undefined &&
        map.getSource(feature.source)?.type === "geojson"
      ) {
        const key = `${feature.source}\n${feature.id}`;
        if (seen.has(key)) continue;
        seen.add(key);
      }
      const count = perLayer.get(parsed.id) ?? 0;
      if (count > 0 && (count >= PER_LAYER || hits.length >= IN_ALL)) continue;
      perLayer.set(parsed.id, count + 1);
      hits.push({
        id: parsed.id,
        instance: parsed.instance,
        properties: JSON.parse(JSON.stringify(feature.properties ?? {})),
      });
    }
    return hits;
  }

  /** The popup, tooltip and cluster features at a point, top first. */
  private queryClickable(map: PointerMap, point: Point): RenderedFeature[] {
    const { clickable, clustered } = this.options;
    const layers = [
      ...(clickable ? ownedStyleLayers(map, clickable) : []),
      ...ownedStyleLayers(map, clustered, "only"),
    ];
    return queryNear(map, point, layers);
  }

  private readonly onClick = (event: PointerEvent): void => {
    const { map, send, viewId, side, drawing, settled } = this.options;
    if (drawing?.()) return;
    const shown = this.pick(event.point);
    // The layers the cursor rule offers `pointer` on decide whether a bubble is hit:
    // a feature of another layer above it does not take the click from it.
    const top = this.queryClickable(shown, event.point)[0];
    if (top && isCluster(top)) {
      this.expand(shown, top, event);
      return;
    }
    const features = this.rendered(shown, event.point);
    const hidden = this.options.hidden?.(event.point) ?? null;
    send({
      type: "click",
      view_id: viewId,
      side,
      lnglat: [wrapLng(event.lngLat.lng), event.lngLat.lat],
      zoom: map.getZoom(),
      settled: settled(),
      features: this.hitsOf(shown, features),
      hidden_features: hidden
        ? this.hitsOf(hidden, this.rendered(hidden, event.point))
        : [],
    });
  };

  /**
   * Zoom into a cluster clicked on `shown` once MapLibre knows how far. The
   * answer is dropped if anything that matters changed while it was on its way.
   */
  private expand(
    shown: PointerMap,
    feature: RenderedFeature,
    event: PointerEvent
  ): void {
    const { map, model } = this.options;
    const clusterId = feature.properties?.cluster_id;
    if (typeof clusterId !== "number" || !Number.isFinite(clusterId)) return;
    const source = shown.getSource(feature.source);
    if (!source?.getClusterExpansionZoom) return;
    this.expansion?.cancel();
    let stale = false;
    const onMoveStart = (move: { originalEvent?: unknown }) => {
      if (move.originalEvent) stale = true;
    };
    const onRequest = () => {
      stale = true;
    };
    const stop = () => {
      map.off("movestart", onMoveStart);
      model.off("change:view_request", onRequest);
    };
    const mine = {
      cancel: () => {
        stale = true;
        stop();
      },
    };
    this.expansion = mine;
    map.on("movestart", onMoveStart);
    model.on("change:view_request", onRequest);
    const coordinates = feature.geometry?.coordinates;
    const center: [number, number] =
      Array.isArray(coordinates) && coordinates.length >= 2
        ? [Number(coordinates[0]), Number(coordinates[1])]
        : [event.lngLat.lng, event.lngLat.lat];
    source.getClusterExpansionZoom(clusterId).then(
      (zoom) => {
        stop();
        if (this.expansion === mine) this.expansion = null;
        if (stale || this.disposed || typeof zoom !== "number") return;
        if (!this.declared(feature.source)) return;
        // The click's event data makes the camera report a user move.
        map.easeTo({ center, zoom }, { originalEvent: event.originalEvent });
      },
      () => {
        stop();
        if (this.expansion === mine) this.expansion = null;
      }
    );
  }

  /** Whether the state still declares the source, and its layer is visible. */
  private declared(source: string): boolean {
    const state = this.options.model.get("state") as Partial<MapState> | null;
    const layers: LayerState[] = state?.layers ?? [];
    return layers.some((l) => l.visible && sourceId(l) === source);
  }

  private readonly onMove = (event: PointerEvent): void => {
    this.at = event.point;
    this.look();
  };

  private readonly onOut = (): void => {
    this.at = null;
    this.look();
  };

  // A popup or tooltip may be turned off, or its layer hidden or removed,
  // under a pointer that does not move.
  private readonly onState = (): void => this.look();

  /** Whether a clickable feature is under the pointer, then the cursor. */
  private look(): void {
    const at = this.at;
    this.over =
      at !== null && this.queryClickable(this.pick(at), at).length > 0;
    this.applyCursor();
  }

  /** Drawing's own cursor, else `pointer` over a clickable feature, else the trait. */
  private readonly applyCursor = (): void => {
    const { map, model, drawing } = this.options;
    if (drawing?.()) return;
    const trait = model.get("cursor");
    map.getCanvas().style.cursor = this.over
      ? "pointer"
      : typeof trait === "string"
      ? trait
      : "";
  };

  private readonly applyMarker = (): void => {
    const { map, model, createMarker } = this.options;
    const value = model.get("marker") as {
      lnglat?: [number, number];
      color?: string;
    } | null;
    if (!value?.lnglat) {
      this.marker?.remove();
      this.marker = null;
      return;
    }
    const color = value.color ?? "#3388ff";
    if (this.marker && color !== this.markerColor) {
      this.marker.remove();
      this.marker = null;
    }
    if (!this.marker) {
      this.marker = createMarker(color);
      this.markerColor = color;
      this.marker.setLngLat(value.lnglat);
      this.marker.addTo(map);
    } else {
      this.marker.setLngLat(value.lnglat);
    }
  };
}
