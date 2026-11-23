// The state contract published by the Python widget (see state.py).
import type {
  GeoJSONSourceSpecification,
  LayerSpecification,
  SourceSpecification,
} from "maplibre-gl";

export type Bounds = [number, number, number, number];

export interface VectorPaint {
  stroke: string;
  fill: string | null;
  fill_opacity: number;
  width: number;
  point_radius: number;
  marker: "circle" | "pin";
  /** The property whose value picks a colour in `class_colors`. */
  color_by: string | null;
  /** `[value, colour]` pairs; values are all strings or all integers. */
  class_colors: [string | number, string][];
}

export interface ClusterState {
  radius: number;
  max_zoom: number;
}

/** What a click or the pointer shows: `[]` is every property, else `[name, label]` pairs; null is off. */
export interface InteractionState {
  popup: [string, string][] | null;
  tooltip: [string, string][] | null;
}

/** Which half of a compare map draws a layer. */
export type LayerSide = "left" | "right" | "both";

/** The maps of a view: its own, and the right one beside it in compare. */
export type ViewSide = "main" | "right";

interface LayerBase {
  id: string;
  token: number;
  instance: number;
  zone: "data" | "overlay";
  side: LayerSide;
  visible: boolean;
  opacity: number;
  min_zoom: number;
  max_zoom: number | null;
  attribution: string;
  interaction: InteractionState | null;
}

export interface GeoJSONLayerState extends LayerBase {
  kind: "geojson";
  source: { digest: string; cluster: ClusterState | null };
  paint: VectorPaint;
}

export interface PMTilesLayerState extends LayerBase {
  kind: "pmtiles";
  source: { url: string; source_layer: string };
  paint: VectorPaint;
}

export interface RasterLayerState extends LayerBase {
  kind: "raster";
  source: {
    tiles: string[];
    tile_size: number;
    max_native_zoom: number | null;
    bounds: Bounds | null;
  };
  paint: null;
}

export type LayerState =
  | GeoJSONLayerState
  | PMTilesLayerState
  | RasterLayerState;

export interface BasemapState {
  tiles: string[];
  attribution: string;
  max_zoom: number | null;
}

export interface MapState {
  revision: number;
  theme: "light" | "dark";
  /** A swipe compare: each layer's `side` says which map draws it. */
  compare: boolean;
  controls: {
    zoom: boolean;
    fullscreen: boolean;
    scale: boolean;
    coordinates: boolean;
  };
  basemap: BasemapState | null;
  layers: LayerState[];
}

/** A drawn feature, as Terra Draw holds it and the drawing traits carry it. */
export interface DrawFeature {
  type: "Feature";
  id: string | number;
  geometry: { type: string; coordinates: unknown };
  properties: Record<string, unknown>;
}

/**
 * The `drawing` trait: the session that holds the tools, the tools offered
 * (empty while none does), the colour, and the toolbar's label of each tool,
 * of `select` and of `clear`.
 */
export interface DrawingState {
  session: number;
  modes: string[];
  color: string;
  labels: Record<string, string>;
}

/** The `draw_tool` trait: a session's request for an active tool; `seq` only grows. */
export interface DrawToolState {
  seq: number;
  session: number;
  mode: string;
}

/** The `draw_request` trait: features to show instead; `seq` only grows. */
export interface DrawRequestState {
  seq: number;
  features: DrawFeature[];
}

/** The `drawn` trait: the last report Python accepted, on the request it named. */
export interface DrawnState {
  request_seq: number;
  features: DrawFeature[];
}

export type OwnedSourceSpec =
  | SourceSpecification
  | Omit<GeoJSONSourceSpecification, "data">;

export interface OwnedSource {
  id: string;
  spec: OwnedSourceSpec;
  digest?: string;
}

export interface OwnedStyle {
  sources: OwnedSource[];
  layers: LayerSpecification[];
}
