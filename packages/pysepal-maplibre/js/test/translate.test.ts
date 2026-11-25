import {
  expression,
  featureFilter,
  latest,
} from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import fixture from "./fixtures/state.json";
import { forSide, toOwnedStyle } from "../translate";
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
      "psm:v1:1:cluster",
      "psm:v1:1:count",
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

  it("replaces the circle by a pin symbol on the same point filter", () => {
    const state = withLayers((layers) => {
      layers[0].paint!.marker = "pin";
      layers[0].paint!.fill = "#00ff00";
      layers[0].paint!.point_radius = 10;
      layers[0].opacity = 0.4;
      (layers[0] as GeoJSONLayerState).source.cluster = null;
    });
    const ids = toOwnedStyle(state).layers.map((l) => l.id);
    expect(ids).not.toContain("psm:v1:1:circle");
    const pin = byId(state, "psm:v1:1:pin");
    expect(pin.type).toBe("symbol");
    expect(pin.layout).toEqual({
      visibility: "visible",
      "icon-image": "psm-pin:%2300ff00",
      "icon-size": 2,
      "icon-anchor": "bottom",
      "icon-allow-overlap": true,
      "icon-ignore-placement": true,
    });
    expect(pin.paint).toEqual({ "icon-opacity": 0.4 });
    expect(pin.filter).toEqual(byId(base, "psm:pm:2:circle").filter);
    expect(ids).not.toContain("psm:v1:1:cluster");
  });

  it("tints a pin with the stroke when there is no fill", () => {
    const state = withLayers((layers) => {
      layers[0].paint!.marker = "pin";
    });
    expect(byId(state, "psm:v1:1:pin").layout["icon-image"]).toBe(
      "psm-pin:%233388ff"
    );
  });

  it("draws a bubble circle and a count symbol above it", () => {
    const state = withLayers((layers) => {
      layers[0].paint!.stroke = "#ff0000";
      layers[0].opacity = 0.5;
    });
    const source = toOwnedStyle(state).sources.find((s) => s.id === "psm:v1:1")!
      .spec as any;
    expect(source).toMatchObject({
      type: "geojson",
      cluster: true,
      clusterRadius: 40,
      clusterMaxZoom: 12,
    });
    const cluster = byId(state, "psm:v1:1:cluster");
    const count = byId(state, "psm:v1:1:count");
    expect(cluster).toMatchObject({
      type: "circle",
      filter: ["==", ["get", "cluster"], true],
      paint: {
        "circle-color": "#ff0000",
        "circle-radius": [
          "+",
          11,
          [
            "*",
            2.5,
            [
              "-",
              ["length", ["to-string", ["get", "point_count_abbreviated"]]],
              1,
            ],
          ],
        ],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
        "circle-opacity": 0.5,
        "circle-stroke-opacity": 0.5,
      },
    });
    expect(count).toMatchObject({
      type: "symbol",
      filter: ["==", ["get", "cluster"], true],
      layout: {
        visibility: "visible",
        "text-field": ["to-string", ["get", "point_count_abbreviated"]],
        "text-font": ["Open Sans Bold"],
        "text-size": 12,
        "text-allow-overlap": true,
        "text-ignore-placement": true,
      },
      paint: { "text-color": "#ffffff", "text-opacity": 0.5 },
    });
    const ids = toOwnedStyle(state).layers.map((l) => l.id);
    expect(ids.indexOf("psm:v1:1:count")).toBe(
      ids.indexOf("psm:v1:1:cluster") + 1
    );
    const order = toOwnedStyle(state).layers.map((l) => l.id);
    expect(order.indexOf("psm:v1:1:cluster")).toBeGreaterThan(
      order.indexOf("psm:v1:1:circle")
    );
    expect(byId(state, "psm:v1:1:circle").filter).toEqual([
      "all",
      byId(base, "psm:pm:2:circle").filter,
      ["!=", ["get", "cluster"], true],
    ]);
    expect(byId(state, "psm:v1:1:fill").filter).toEqual(
      byId(base, "psm:pm:2:fill").filter
    );
  });

  it("leaves an unclustered source alone", () => {
    const source = toOwnedStyle(base).sources.find((s) => s.id === "psm:pm:2")!
      .spec as any;
    expect(source.cluster).toBeUndefined();
    expect(byId(base, "psm:pm:2:circle").filter[0]).toBe("in");
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

describe("colours by class", () => {
  // pm is the fixture's unclustered vector layer.
  const classed = (
    classes: [string | number, string][],
    marker: "circle" | "pin" = "circle"
  ) =>
    withLayers((layers) => {
      const paint = layers[1].paint!;
      paint.fill = "#123456";
      paint.marker = marker;
      paint.color_by = "status";
      paint.class_colors = classes;
    });
  const AB: [string, string][] = [
    ["a", "#ff0000"],
    ["b", "#00ff00"],
  ];
  const match = (a: string, b: string, fallback: string) => [
    "match",
    ["get", "status"],
    "a",
    a,
    "b",
    b,
    fallback,
  ];

  it("colours fill, line and circle by class", () => {
    const state = classed(AB);
    expect(byId(state, "psm:pm:2:fill").paint["fill-color"]).toEqual(
      match("#ff0000", "#00ff00", "#123456")
    );
    expect(byId(state, "psm:pm:2:line").paint["line-color"]).toEqual(
      match("#ff0000", "#00ff00", "#3388ff")
    );
    const circle = byId(state, "psm:pm:2:circle").paint;
    expect(circle["circle-color"]).toEqual(
      match("#ff0000", "#00ff00", "#123456")
    );
    expect(circle["circle-stroke-color"]).toBe("#3388ff");
  });

  it("picks a pin image by class", () => {
    const pin = byId(classed(AB, "pin"), "psm:pm:2:pin");
    expect(pin.layout["icon-image"]).toEqual(
      match("psm-pin:%23ff0000", "psm-pin:%2300ff00", "psm-pin:%23123456")
    );
    const compiled = expression.createPropertyExpression(
      pin.layout["icon-image"],
      "icon-image",
      (latest as any).layout_symbol["icon-image"]
    );
    expect(compiled.result).toBe("success");
    const image = (properties: object) =>
      (compiled.value as any)
        .evaluate({ zoom: 0 }, { type: 1, properties })
        .toString();
    expect(image({ status: "b" })).toBe("psm-pin:%2300ff00");
    expect(image({ status: "z" })).toBe("psm-pin:%23123456");
  });

  it("leaves paint alone without color_by", () => {
    const plain = withLayers((layers) => {
      layers[1].paint!.class_colors = AB;
    });
    expect(toOwnedStyle(plain)).toEqual(toOwnedStyle(base));
    const older = withLayers((layers) => {
      const paint = layers[1].paint as any;
      delete paint.color_by;
      delete paint.class_colors;
    });
    expect(toOwnedStyle(older)).toEqual(toOwnedStyle(base));
    expect(byId(base, "psm:pm:2:fill").paint["fill-color"]).toBe("#3388ff");
    expect(byId(base, "psm:pm:2:line").paint["line-color"]).toBe("#3388ff");
    expect(byId(base, "psm:pm:2:circle").paint["circle-color"]).toBe("#3388ff");
  });

  it("draws unmatched class values in the default colour", () => {
    const state = classed([[1, "#ff0000"]]);
    const compiled = (part: string, property: string) => {
      const value = byId(state, `psm:pm:2:${part}`).paint[property];
      const spec = (latest as any)[`paint_${part}`][property];
      const result = expression.createPropertyExpression(value, property, spec);
      if (result.result !== "success") throw new Error(String(result.value));
      return result.value;
    };
    const colour = (part: string, property: string, properties: object) =>
      compiled(part, property)
        .evaluate({ zoom: 0 }, { type: 1, properties } as any)
        .toString();
    const red = "rgba(255,0,0,1)";
    const fallback = "rgba(18,52,86,1)";
    for (const [part, property] of [
      ["fill", "fill-color"],
      ["circle", "circle-color"],
    ]) {
      expect(colour(part, property, { status: 1 })).toBe(red);
      expect(colour(part, property, { status: "1" })).toBe(fallback);
      expect(colour(part, property, { status: null })).toBe(fallback);
      expect(colour(part, property, { status: 2 })).toBe(fallback);
      expect(colour(part, property, {})).toBe(fallback);
    }
  });
});

describe("forSide", () => {
  // The fixture's layers are v1, pm and r1, top-first.
  const sided = (compare: boolean): MapState => {
    const state = withLayers((layers) => {
      layers[0].side = "left";
      layers[1].side = "right";
      layers[2].side = "both";
    });
    return { ...state, compare };
  };
  const ids = (state: MapState) => state.layers.map((layer) => layer.id);

  it("gives main every layer outside compare", () => {
    expect(ids(forSide(sided(false), "main"))).toEqual(["v1", "pm", "r1"]);
  });

  it("gives right no layer outside compare", () => {
    expect(ids(forSide(sided(false), "right"))).toEqual([]);
  });

  it("gives main the left and both layers in compare", () => {
    expect(ids(forSide(sided(true), "main"))).toEqual(["v1", "r1"]);
  });

  it("gives right the right and both layers in compare", () => {
    expect(ids(forSide(sided(true), "right"))).toEqual(["pm", "r1"]);
  });

  it("keeps the order, basemap, theme and controls", () => {
    const state = sided(true);
    const dark = {
      ...state,
      theme: "dark" as const,
      layers: [...state.layers].reverse(),
    };
    const out = forSide(dark, "right");
    expect(ids(out)).toEqual(["r1", "pm"]);
    const { layers: _out, ...rest } = out;
    const { layers: _dark, ...expected } = dark;
    expect(rest).toEqual(expected);
    expect(out.basemap).toEqual(base.basemap);
    expect(out.layers[0]).toEqual(dark.layers[0]);
  });
});
