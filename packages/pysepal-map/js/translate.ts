import type { FilterSpecification, LayerSpecification } from "maplibre-gl";

import type {
  GeoJSONLayerState,
  LayerState,
  MapState,
  OwnedSource,
  OwnedStyle,
  PMTilesLayerState,
  RasterLayerState,
} from "./types";

export const BASEMAP_ID = "psm:basemap";

export const sourceId = (layer: Pick<LayerState, "id" | "instance">): string =>
  `psm:${encodeURIComponent(layer.id)}:${layer.instance}`;

/**
 * The layer id and instance in an owned source id, or in the id of a style
 * layer built on one (`psm:<id>:<instance>[:<part>]`); null for anything else.
 */
export function parseSourceId(
  id: string
): { id: string; instance: number } | null {
  const match = /^psm:([^:]+):(\d+)(?::[a-z]+)?$/.exec(id);
  if (!match) return null;
  try {
    return { id: decodeURIComponent(match[1]), instance: Number(match[2]) };
  } catch {
    return null;
  }
}

// Tile features report numeric types (multi geometries collapse into their
// single kind) but GeoJSON-typed features keep the Multi* names, so list both.
const geometryIn = (...types: string[]): FilterSpecification => [
  "in",
  ["geometry-type"],
  ["literal", types],
];
const POLYGON = geometryIn("Polygon", "MultiPolygon");
const LINE = geometryIn(
  "LineString",
  "MultiLineString",
  "Polygon",
  "MultiPolygon"
);
const POINT = geometryIn("Point", "MultiPoint");

function zoomRange(layer: LayerState): { minzoom?: number; maxzoom?: number } {
  const range: { minzoom?: number; maxzoom?: number } = {};
  if (layer.min_zoom) range.minzoom = layer.min_zoom;
  if (layer.max_zoom != null) range.maxzoom = layer.max_zoom;
  return range;
}

/** Prefixes of the generated image ids; see images.ts. */
export const PIN_PREFIX = "psm-pin:";
export const COUNT_PREFIX = "psm-count:";

const NOT_CLUSTER: FilterSpecification = ["!=", ["get", "cluster"], true];

function vectorLayers(
  layer: GeoJSONLayerState | PMTilesLayerState,
  source: string
): LayerSpecification[] {
  const { paint, opacity } = layer;
  const layout = { visibility: layer.visible ? "visible" : "none" } as const;
  const common = {
    source,
    layout,
    ...zoomRange(layer),
    ...(layer.kind === "pmtiles"
      ? { "source-layer": layer.source.source_layer }
      : {}),
  };
  const fillColor = paint.fill ?? paint.stroke;
  const fillOpacity = paint.fill_opacity * opacity;
  const cluster = layer.kind === "geojson" && layer.source.cluster !== null;
  const pointFilter: FilterSpecification = cluster
    ? (["all", POINT, NOT_CLUSTER] as FilterSpecification)
    : POINT;
  const point: LayerSpecification =
    paint.marker === "pin"
      ? {
          ...common,
          id: `${source}:pin`,
          type: "symbol",
          filter: pointFilter,
          layout: {
            ...layout,
            "icon-image": `${PIN_PREFIX}${encodeURIComponent(fillColor)}`,
            "icon-size": paint.point_radius / 5,
            "icon-anchor": "bottom",
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
          },
          paint: { "icon-opacity": opacity },
        }
      : {
          ...common,
          id: `${source}:circle`,
          type: "circle",
          filter: pointFilter,
          paint: {
            "circle-radius": paint.point_radius,
            "circle-color": fillColor,
            "circle-opacity": fillOpacity,
            "circle-stroke-color": paint.stroke,
            "circle-stroke-width": paint.width,
            "circle-stroke-opacity": opacity,
          },
        };
  const layers = [
    {
      ...common,
      id: `${source}:fill`,
      type: "fill",
      filter: POLYGON,
      paint: { "fill-color": fillColor, "fill-opacity": fillOpacity },
    },
    {
      ...common,
      id: `${source}:line`,
      type: "line",
      filter: LINE,
      paint: {
        "line-color": paint.stroke,
        "line-width": paint.width,
        "line-opacity": opacity,
      },
    },
    point,
  ] as LayerSpecification[];
  if (cluster) {
    layers.push({
      ...common,
      id: `${source}:cluster`,
      type: "symbol",
      filter: ["==", ["get", "cluster"], true],
      layout: {
        ...layout,
        "icon-image": [
          "concat",
          `${COUNT_PREFIX}${encodeURIComponent(paint.stroke)}:`,
          ["to-string", ["get", "point_count_abbreviated"]],
        ],
        "icon-allow-overlap": true,
        "icon-ignore-placement": true,
      },
      paint: { "icon-opacity": opacity },
    } as LayerSpecification);
  }
  return layers;
}

function rasterLayer(
  layer: RasterLayerState,
  source: string
): LayerSpecification {
  return {
    id: `${source}:raster`,
    type: "raster",
    source,
    layout: { visibility: layer.visible ? "visible" : "none" },
    paint: { "raster-opacity": layer.opacity },
    ...zoomRange(layer),
  };
}

function translateLayer(layer: LayerState): {
  source: OwnedSource;
  layers: LayerSpecification[];
} {
  const id = sourceId(layer);
  const attribution = layer.attribution
    ? { attribution: layer.attribution }
    : {};
  switch (layer.kind) {
    case "geojson":
      return {
        source: {
          id,
          spec: {
            type: "geojson",
            generateId: true,
            ...(layer.source.cluster
              ? {
                  cluster: true,
                  clusterRadius: layer.source.cluster.radius,
                  clusterMaxZoom: layer.source.cluster.max_zoom,
                }
              : {}),
            ...attribution,
          },
          digest: layer.source.digest,
        },
        layers: vectorLayers(layer, id),
      };
    case "pmtiles":
      return {
        source: {
          id,
          spec: {
            type: "vector",
            url: `pmtiles://${layer.source.url}`,
            ...attribution,
          },
        },
        layers: vectorLayers(layer, id),
      };
    case "raster": {
      const { tiles, tile_size, max_native_zoom, bounds } = layer.source;
      return {
        source: {
          id,
          spec: {
            type: "raster",
            tiles,
            tileSize: tile_size,
            ...(bounds ? { bounds } : {}),
            ...(max_native_zoom != null ? { maxzoom: max_native_zoom } : {}),
            ...attribution,
          },
        },
        layers: [rasterLayer(layer, id)],
      };
    }
  }
}

/** Translate the published state into owned sources and layers, bottom-first. */
export function toOwnedStyle(state: MapState): OwnedStyle {
  const sources: OwnedSource[] = [];
  const layers: LayerSpecification[] = [];

  if (state.basemap) {
    const { tiles, attribution, max_zoom } = state.basemap;
    sources.push({
      id: BASEMAP_ID,
      spec: {
        type: "raster",
        tiles,
        tileSize: 256,
        ...(attribution ? { attribution } : {}),
        ...(max_zoom != null ? { maxzoom: max_zoom } : {}),
      },
    });
    layers.push({ id: BASEMAP_ID, type: "raster", source: BASEMAP_ID });
  }

  // state.layers is top-first; the overlay zone draws above the data zone.
  const bottomFirst = [...(state.layers ?? [])].reverse();
  const ordered = [
    ...bottomFirst.filter((l) => l.zone !== "overlay"),
    ...bottomFirst.filter((l) => l.zone === "overlay"),
  ];
  for (const layer of ordered) {
    const out = translateLayer(layer);
    sources.push(out.source);
    layers.push(...out.layers);
  }
  return { sources, layers };
}
