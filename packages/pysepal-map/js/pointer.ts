import type { PointLike } from "maplibre-gl";

import { parseSourceId } from "./translate";

/** Where the browser reports a click, and what a hit may carry at most. */
const PER_LAYER = 5;
const IN_ALL = 20;

/** The parts of an owned vector layer that a click can hit. */
const HIT_PART = /^psm:[^:]+:\d+:(fill|line|circle|pin)$/;

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
}

interface PointerEvent {
  point: PointLike;
  lngLat: { lng: number; lat: number };
}

/** The part of a MapLibre map the pointer rules use. */
export interface PointerMap {
  getLayersOrder(): string[];
  getLayer(id: string): unknown;
  getSource(id: string): { type?: string } | undefined;
  getZoom(): number;
  getCanvas(): { style: { cursor: string } };
  queryRenderedFeatures(
    geometry: PointLike,
    options: { layers: string[] }
  ): RenderedFeature[];
  on(type: string, listener: (event: any) => void): unknown;
  off(type: string, listener: (event: any) => void): unknown;
}

export interface MarkerLike {
  setLngLat(lnglat: [number, number]): unknown;
  addTo(map: any): unknown;
  remove(): unknown;
}

export interface PointerModel {
  get(name: "cursor" | "marker"): unknown;
  on(name: string, callback: () => void): void;
  off(name: string, callback: () => void): void;
  send(content: unknown): void;
}

export interface PointerOptions {
  map: PointerMap;
  model: PointerModel;
  viewId: string;
  side: string;
  /** Whether the latest state is on the map, every GeoJSON payload loaded. */
  settled(): boolean;
  /** Whether drawing is interactive: clicks and the cursor are then its own. */
  drawing?(): boolean;
  /** Whether a layer shows a popup, a tooltip or clusters: its features take `pointer`. */
  clickable?(layerId: string): boolean;
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
  private disposed = false;

  constructor(private readonly options: PointerOptions) {
    const { map, model } = options;
    map.on("click", this.onClick);
    map.on("mousemove", this.onMove);
    map.on("mouseout", this.onOut);
    model.on("change:cursor", this.applyCursor);
    model.on("change:marker", this.applyMarker);
    this.applyCursor();
    this.applyMarker();
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    const { map, model } = this.options;
    map.off("click", this.onClick);
    map.off("mousemove", this.onMove);
    map.off("mouseout", this.onOut);
    model.off("change:cursor", this.applyCursor);
    model.off("change:marker", this.applyMarker);
    this.marker?.remove();
    this.marker = null;
  }

  /** The owned vector style layers in the live style, optionally of some logical layers. */
  private styleLayers(wanted?: (layerId: string) => boolean): string[] {
    const { map } = this.options;
    return map.getLayersOrder().filter((id) => {
      if (!HIT_PART.test(id) || !map.getLayer(id)) return false;
      const parsed = parseSourceId(id);
      return parsed !== null && (!wanted || wanted(parsed.id));
    });
  }

  /** The hits at a point, top first, capped per layer and in all. */
  hitsAt(point: PointLike): Hit[] {
    const { map } = this.options;
    const layers = this.styleLayers();
    if (!layers.length) return [];
    const perLayer = new Map<string, number>();
    const seen = new Set<string>();
    const hits: Hit[] = [];
    for (const feature of map.queryRenderedFeatures(point, { layers })) {
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

  private readonly onClick = (event: PointerEvent): void => {
    const { map, model, viewId, side, drawing, settled } = this.options;
    if (drawing?.()) return;
    model.send({
      type: "click",
      view_id: viewId,
      side,
      lnglat: [wrapLng(event.lngLat.lng), event.lngLat.lat],
      zoom: map.getZoom(),
      settled: settled(),
      features: this.hitsAt(event.point),
    });
  };

  private readonly onMove = (event: PointerEvent): void => {
    const { clickable } = this.options;
    const layers = clickable ? this.styleLayers(clickable) : [];
    this.over =
      layers.length > 0 &&
      this.options.map.queryRenderedFeatures(event.point, { layers }).length >
        0;
    this.applyCursor();
  };

  private readonly onOut = (): void => {
    this.over = false;
    this.applyCursor();
  };

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
