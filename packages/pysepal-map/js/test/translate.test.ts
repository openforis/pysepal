import { featureFilter } from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import fixture from "./fixtures/state.json";
import { toOwnedStyle } from "../translate";
import type { GeoJSONLayerState, LayerState, MapState } from "../types";

const base = fixture as unknown as MapState;

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));

function withLayers(mutate: (layers: LayerState[]) => void): MapState {
  const state = clone(base);
  mutate(state.layers);
  return state;
}

const byId = (state: MapState, id: string) =>
  toOwnedStyle(state).layers.find((layer) => layer.id === id) as any;

describe("toOwnedStyle", () => {
  it("orders the fixture layers bottom-first", () => {
    expect(toOwnedStyle(base).layers.map((l) => l.id)).toEqual([
      "psm:basemap",
      "psm:r1:3:raster",
      "psm:pm:2:fill",
      "psm:pm:2:line",
      "psm:pm:2:circle",
      "psm:v1:1:fill",
      "psm:v1:1:line",
      "psm:v1:1:circle",
    ]);
  });

  it("keeps overlay layers above every data layer", () => {
    const state = withLayers((layers) => {
      layers[layers.length - 1].zone = "overlay"; // r1, listed last
    });
    const ids = toOwnedStyle(state).layers.map((l) => l.id);
    expect(ids.at(-1)).toBe("psm:r1:3:raster");
    expect(ids[0]).toBe("psm:basemap");
  });

  it("hides every part of a hidden layer", () => {
    const state = withLayers((layers) => {
      layers[0].visible = false;
      layers[2].visible = false;
    });
    const layers = toOwnedStyle(state).layers as any[];
    for (const l of layers.filter(
      (x) => x.id.startsWith("psm:v1:") || x.id.startsWith("psm:r1:")
    )) {
      expect(l.layout.visibility).toBe("none");
    }
    expect(byId(state, "psm:pm:2:fill").layout.visibility).toBe("visible");
  });

  it("applies opacity to vector and raster paint", () => {
    const state = withLayers((layers) => {
      for (const l of layers) {
        l.opacity = 0.5;
        if (l.paint) l.paint.fill_opacity = 0.4;
      }
    });
    expect(byId(state, "psm:v1:1:fill").paint["fill-opacity"]).toBeCloseTo(0.2);
    expect(byId(state, "psm:v1:1:line").paint["line-opacity"]).toBe(0.5);
    expect(byId(state, "psm:v1:1:circle").paint["circle-stroke-opacity"]).toBe(
      0.5
    );
    expect(byId(state, "psm:v1:1:circle").paint["circle-opacity"]).toBeCloseTo(
      0.2
    );
    expect(byId(state, "psm:r1:3:raster").paint["raster-opacity"]).toBe(0.5);
  });

  it("maps vector paint values", () => {
    const state = withLayers((layers) => {
      layers[0].paint!.fill = "#ff0000";
    });
    expect(byId(state, "psm:v1:1:fill").paint["fill-color"]).toBe("#ff0000");
    expect(byId(state, "psm:v1:1:circle").paint["circle-color"]).toBe(
      "#ff0000"
    );
    expect(byId(base, "psm:v1:1:fill").paint["fill-color"]).toBe("#3388ff");
    expect(byId(base, "psm:v1:1:line").paint["line-width"]).toBe(2);
    expect(byId(base, "psm:v1:1:circle").paint["circle-radius"]).toBe(5);
    expect(byId(base, "psm:v1:1:circle").paint["circle-stroke-width"]).toBe(2);
  });

  it("puts native zoom on the source and the cutoff on the layer", () => {
    const style = toOwnedStyle(
      withLayers((layers) => {
        layers[2].attribution = "© R";
      })
    );
    const source = style.sources.find((s) => s.id === "psm:r1:3")!.spec as any;
    expect(source.maxzoom).toBe(20);
    expect(source.attribution).toBe("© R");
    expect(source.bounds).toEqual([-10, -5, 10, 5]);
    expect(source.tileSize).toBe(256);
    expect(byId(base, "psm:r1:3:raster")).not.toHaveProperty("maxzoom");

    const capped = withLayers((layers) => {
      layers[2].max_zoom = 18;
    });
    expect(byId(capped, "psm:r1:3:raster").maxzoom).toBe(18);
    const cappedSource = toOwnedStyle(capped).sources.find(
      (s) => s.id === "psm:r1:3"
    )!.spec as any;
    expect(cappedSource.maxzoom).toBe(20);
  });

  it("describes the basemap, geojson and pmtiles sources", () => {
    const { sources } = toOwnedStyle(base);
    expect(sources.map((s) => s.id)).toEqual([
      "psm:basemap",
      "psm:r1:3",
      "psm:pm:2",
      "psm:v1:1",
    ]);
    expect(sources[0].spec).toMatchObject({
      type: "raster",
      tiles: ["https://t/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OSM",
      maxzoom: 19,
    });
    expect(sources[2].spec).toEqual({
      type: "vector",
      url: "pmtiles://https://x.org/a.pmtiles",
    });
    const geo = sources[3];
    expect(geo.spec.type).toBe("geojson");
    expect(geo.spec).not.toHaveProperty("data");
    expect(geo.digest).toBe(
      (base.layers[0] as GeoJSONLayerState).source.digest
    );
  });

  it("encodes logical ids", () => {
    const state = withLayers((layers) => {
      layers[0].id = "a b:c";
    });
    expect(toOwnedStyle(state).layers.map((l) => l.id)).toContain(
      "psm:a%20b%3Ac:1:fill"
    );
  });

  it("sets the source layer on PMTiles parts only", () => {
    for (const part of ["fill", "line", "circle"]) {
      expect(byId(base, `psm:pm:2:${part}`)["source-layer"]).toBe("roads");
      expect(byId(base, `psm:v1:1:${part}`)).not.toHaveProperty("source-layer");
    }
  });

  it("returns nothing for an empty or missing state", () => {
    expect(toOwnedStyle({ ...base, basemap: null, layers: [] })).toEqual({
      sources: [],
      layers: [],
    });
    expect(toOwnedStyle({} as MapState)).toEqual({ sources: [], layers: [] });
  });

  it("lets multi geometries through the geometry filters", () => {
    const compile = (id: string) =>
      featureFilter(byId(base, id).filter, "layers[0].filter").filter;
    const poly = compile("psm:v1:1:fill");
    const line = compile("psm:v1:1:line");
    const circle = compile("psm:v1:1:circle");
    const feature = (type: string) => ({ type, properties: {} } as any);
    const ctx = { zoom: 0 };
    expect(poly(ctx, feature("Polygon"))).toBe(true);
    expect(poly(ctx, feature("MultiPolygon"))).toBe(true);
    expect(poly(ctx, feature("LineString"))).toBe(false);
    expect(line(ctx, feature("MultiLineString"))).toBe(true);
    expect(line(ctx, feature("MultiPolygon"))).toBe(true);
    expect(line(ctx, feature("Point"))).toBe(false);
    expect(circle(ctx, feature("MultiPoint"))).toBe(true);
    expect(circle(ctx, feature("Polygon"))).toBe(false);
    // vector tiles report numeric types: 1 point, 2 line, 3 polygon
    const tiled = (type: number) => ({ type, properties: {} } as any);
    expect(poly(ctx, tiled(3))).toBe(true);
    expect(poly(ctx, tiled(2))).toBe(false);
    expect(line(ctx, tiled(2))).toBe(true);
    expect(circle(ctx, tiled(1))).toBe(true);
  });
});
