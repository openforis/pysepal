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
}

interface LayerBase {
  id: string;
  token: number;
  instance: number;
  zone: "data" | "overlay";
  visible: boolean;
  opacity: number;
  min_zoom: number;
  max_zoom: number | null;
  attribution: string;
}

export interface GeoJSONLayerState extends LayerBase {
  kind: "geojson";
  source: { digest: string };
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
  GeoJSONLayerState | PMTilesLayerState | RasterLayerState;

export interface BasemapState {
  tiles: string[];
  attribution: string;
  max_zoom: number | null;
}

export interface MapState {
  revision: number;
  theme: "light" | "dark";
  controls: { zoom: boolean; fullscreen: boolean };
  basemap: BasemapState | null;
  layers: LayerState[];
}

export type OwnedSourceSpec =
  SourceSpecification | Omit<GeoJSONSourceSpecification, "data">;

export interface OwnedSource {
  id: string;
  spec: OwnedSourceSpec;
  digest?: string;
}

export interface OwnedStyle {
  sources: OwnedSource[];
  layers: LayerSpecification[];
}
