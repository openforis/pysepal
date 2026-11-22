import { describe, expect, it } from "vitest";

import {
  ViewPointer,
  wrapLng,
  type MarkerLike,
  type PointerMap,
  type RenderedFeature,
} from "../pointer";
import { parseSourceId } from "../translate";

type Listener = (event: any) => void;

class FakePointerMap implements PointerMap {
  layers: string[] = [];
  /** Source id to its type. */
  sources = new Map<string, string>();
  features: RenderedFeature[] = [];
  queries: { layers: string[] }[] = [];
  zoom = 4;
  canvas = { style: { cursor: "" } };
  private listeners = new Map<string, Set<Listener>>();

  getLayersOrder = () => this.layers;
  getLayer = (id: string) => (this.layers.includes(id) ? {} : undefined);
  /** Answers `getClusterExpansionZoom`; tests swap it to hold the promise. */
  expansionZoom: (id: number) => Promise<number> = async () => 9;
  eased: { options: unknown; eventData: unknown }[] = [];
  getSource = (id: string) =>
    this.sources.has(id)
      ? {
          type: this.sources.get(id),
          getClusterExpansionZoom: (cluster: number) =>
            this.expansionZoom(cluster),
        }
      : undefined;
  easeTo = (options: unknown, eventData?: unknown) =>
    void this.eased.push({ options, eventData });
  getZoom = () => this.zoom;
  getCanvas = () => this.canvas;
  queryRenderedFeatures = (_point: unknown, options: { layers: string[] }) => {
    this.queries.push(options);
    // A feature may name its style layer; MapLibre then returns it only when queried.
    return this.features.filter(
      (f: any) => !f.layer || options.layers.includes(f.layer)
    );
  };
  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }
  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }
  emit(type: string, event: unknown = {}) {
    for (const listener of [...(this.listeners.get(type) ?? [])])
      listener(event);
  }
  count(type: string) {
    return this.listeners.get(type)?.size ?? 0;
  }
}

class FakeModel {
  values: Record<string, unknown> = { cursor: "", marker: {} };
  sent: any[] = [];
  private listeners = new Map<string, Set<() => void>>();
  get(name: string) {
    return this.values[name];
  }
  on(name: string, callback: () => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name)!.add(callback);
  }
  off(name: string, callback: () => void) {
    this.listeners.get(name)?.delete(callback);
  }
  send(content: unknown) {
    this.sent.push(content);
  }
  set(name: string, value: unknown) {
    this.values[name] = value;
    for (const callback of [...(this.listeners.get(`change:${name}`) ?? [])])
      callback();
  }
}

class FakeMarker implements MarkerLike {
  lnglat: [number, number] | null = null;
  added = false;
  removed = false;
  constructor(readonly color: string) {}
  setLngLat(lnglat: [number, number]) {
    this.lnglat = lnglat;
    return this;
  }
  addTo() {
    this.added = true;
    return this;
  }
  remove() {
    this.removed = true;
    return this;
  }
}

const sid = (id: string, instance: number) =>
  `psm:${encodeURIComponent(id)}:${instance}`;

function feature(
  layer: string,
  instance: number,
  id: number | undefined,
  properties: Record<string, unknown> = {}
): RenderedFeature {
  return { id, source: sid(layer, instance), properties };
}

/** Declare a vector layer's source and its style layers on `map`. */
function declareOn(
  map: FakePointerMap,
  id: string,
  instance: number,
  type = "geojson"
) {
  map.sources.set(sid(id, instance), type);
  for (const part of ["fill", "line", "circle"]) {
    map.layers.push(`${sid(id, instance)}:${part}`);
  }
}

const bubble = (id: string, instance: number, clusterId: unknown = 7) => ({
  id: 0,
  source: sid(id, instance),
  properties: { cluster: true, cluster_id: clusterId, point_count: 5 },
  geometry: { type: "Point", coordinates: [3, 4] },
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

function setup(
  options: {
    drawing?: () => boolean;
    send?: (content: unknown) => void;
    clickable?: (id: string) => boolean;
    clustered?: (id: string) => boolean;
    pick?: (point: { x: number; y: number }) => PointerMap;
  } = {}
) {
  const map = new FakePointerMap();
  const model = new FakeModel();
  const markers: FakeMarker[] = [];
  const pointer = new ViewPointer({
    map,
    model,
    viewId: "v1",
    side: "main",
    settled: () => true,
    send: (content) => model.send(content),
    createMarker: (color) => {
      const marker = new FakeMarker(color);
      markers.push(marker);
      return marker;
    },
    ...options,
  });
  const declare = (id: string, instance: number, type = "geojson") =>
    declareOn(map, id, instance, type);
  /** Add the cluster style layer of a declared layer, and declare it in the state. */
  const cluster = (id: string, instance: number, on = map) => {
    on.layers.push(`${sid(id, instance)}:cluster`);
    model.values.state = {
      layers: [
        {
          id,
          instance,
          kind: "geojson",
          visible: true,
          source: { cluster: {} },
        },
      ],
    };
  };
  const click = (lng = 10, lat = 20) =>
    map.emit("click", { point: [1, 2], lngLat: { lng, lat } });
  return { map, model, markers, pointer, declare, cluster, click };
}

describe("parseSourceId", () => {
  it("reads a source id and the id of a layer built on it", () => {
    expect(parseSourceId("psm:a%3Ab:7")).toEqual({ id: "a:b", instance: 7 });
    expect(parseSourceId("psm:a%3Ab:7:fill")).toEqual({
      id: "a:b",
      instance: 7,
    });
  });

  it("rejects the basemap, foreign ids and bad escapes", () => {
    expect(parseSourceId("psm:basemap")).toBeNull();
    expect(parseSourceId("other:a:1")).toBeNull();
    expect(parseSourceId("psm:%E0%A4%A:1")).toBeNull();
  });
});

describe("wrapLng", () => {
  it("wraps into [-180, 180] and leaves the rest alone", () => {
    expect(wrapLng(190)).toBe(-170);
    expect(wrapLng(-190)).toBe(170);
    expect(wrapLng(540)).toBe(-180);
    expect(wrapLng(180)).toBe(180);
    expect(wrapLng(12.5)).toBe(12.5);
  });
});

describe("click", () => {
  it("sends the point, the zoom, settled and the hits", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    map.features = [feature("a", 1, 0, { name: "x" })];
    click();
    expect(model.sent).toEqual([
      {
        type: "click",
        view_id: "v1",
        side: "main",
        lnglat: [10, 20],
        zoom: 4,
        settled: true,
        features: [{ id: "a", instance: 1, properties: { name: "x" } }],
      },
    ]);
  });

  it("wraps the longitude", () => {
    const { model, click } = setup();
    click(190, 0);
    expect(model.sent[0].lnglat).toEqual([-170, 0]);
  });

  it("queries only owned vector style layers that are in the live style", () => {
    const { map, declare, click } = setup();
    declare("a", 1);
    declare("b", 1, "vector");
    map.layers.push(
      "psm:basemap",
      "psm:r:1:raster",
      "water-fill",
      "terra-draw-polygon",
      `${sid("c", 1)}:pin`
    );
    // A layer MapLibre would reject the whole query for.
    const getLayer = map.getLayer;
    map.getLayer = (id: string) =>
      id.endsWith("c:1:pin") ? undefined : getLayer(id);
    click();
    expect(map.queries[0].layers).toEqual([
      `${sid("a", 1)}:fill`,
      `${sid("a", 1)}:line`,
      `${sid("a", 1)}:circle`,
      `${sid("b", 1)}:fill`,
      `${sid("b", 1)}:line`,
      `${sid("b", 1)}:circle`,
    ]);
  });

  it("ignores features of other sources", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    map.features = [
      { id: 1, source: "composite", properties: {} },
      { id: 2, source: "psm:basemap", properties: {} },
      feature("a", 1, 3),
    ];
    click();
    expect(model.sent[0].features).toHaveLength(1);
  });

  it("sends the older instance of a re-declared layer", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    declare("a", 2);
    map.features = [feature("a", 2, 0), feature("a", 1, 0)];
    click();
    expect(model.sent[0].features.map((f: any) => f.instance)).toEqual([2, 1]);
  });

  it("sends a tile duplicate of one GeoJSON feature once", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    map.features = [feature("a", 1, 0, { n: 1 }), feature("a", 1, 0, { n: 1 })];
    click();
    expect(model.sent[0].features).toHaveLength(1);
  });

  it("keeps coincident GeoJSON features and id 0 of two layers", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    declare("b", 1);
    map.features = [
      feature("a", 1, 0, { same: 1 }),
      feature("a", 1, 1, { same: 1 }),
      feature("b", 1, 0, { same: 1 }),
    ];
    click();
    expect(model.sent[0].features.map((f: any) => f.id)).toEqual([
      "a",
      "a",
      "b",
    ]);
  });

  it("keeps every PMTiles hit", () => {
    const { map, model, declare, click } = setup();
    declare("p", 1, "vector");
    map.features = [
      feature("p", 1, 5, { same: 1 }),
      feature("p", 1, 5, { same: 1 }),
      feature("p", 1, undefined, { same: 1 }),
    ];
    click();
    expect(model.sent[0].features).toHaveLength(3);
  });

  it("caps 5 per layer and 20 in all but sends each layer's first hit, top first", () => {
    const { map, model, declare, click } = setup();
    for (let i = 0; i < 25; i++) declare(`l${i}`, 1);
    declare("big", 1);
    map.features = [
      ...Array.from({ length: 8 }, (_, n) => feature("big", 1, n)),
      ...Array.from({ length: 25 }, (_, i) => feature(`l${i}`, 1, 0)),
    ];
    click();
    const sent = model.sent[0].features as { id: string }[];
    expect(sent.filter((f) => f.id === "big")).toHaveLength(5);
    expect(new Set(sent.map((f) => f.id)).size).toBe(26);
    expect(sent.map((f) => f.id)).toEqual([
      ...Array(5).fill("big"),
      ...Array.from({ length: 25 }, (_, i) => `l${i}`),
    ]);
  });

  it("stops filling past 20 hits in all", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    declare("b", 1);
    map.features = [
      ...Array.from({ length: 5 }, (_, n) => feature("a", 1, n)),
      ...Array.from({ length: 30 }, (_, n) => feature("b", 1, n)),
    ];
    click();
    expect(
      model.sent[0].features.filter((f: any) => f.id === "b")
    ).toHaveLength(5);
  });

  it("copies the properties as plain JSON", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    const props = { n: 1, nested: { a: [1, 2] }, undef: undefined };
    map.features = [feature("a", 1, 0, props)];
    click();
    const sent = model.sent[0].features[0].properties;
    expect(sent).toEqual({ n: 1, nested: { a: [1, 2] } });
    expect(sent.nested).not.toBe(props.nested);
  });

  it("sends nothing while drawing is interactive", () => {
    let drawing = true;
    const { model, click } = setup({ drawing: () => drawing });
    click();
    expect(model.sent).toEqual([]);
    drawing = false;
    click();
    expect(model.sent).toHaveLength(1);
  });

  it("stops listening on dispose", () => {
    const { map, pointer } = setup();
    pointer.dispose();
    expect(["click", "mousemove", "mouseout"].map((t) => map.count(t))).toEqual(
      [0, 0, 0]
    );
  });
});

describe("cursor", () => {
  const move = (map: FakePointerMap) =>
    map.emit("mousemove", { point: [1, 1], lngLat: { lng: 0, lat: 0 } });

  it("follows the trait, and an empty trait clears the inline style", () => {
    const { map, model } = setup();
    model.set("cursor", "crosshair");
    expect(map.canvas.style.cursor).toBe("crosshair");
    model.set("cursor", "");
    expect(map.canvas.style.cursor).toBe("");
  });

  it("is pointer over a feature of a clickable layer, the trait elsewhere", () => {
    const { map, model, declare } = setup({ clickable: (id) => id === "a" });
    declare("a", 1);
    declare("b", 1);
    model.set("cursor", "wait");
    map.features = [feature("a", 1, 0)];
    move(map);
    expect(map.canvas.style.cursor).toBe("pointer");
    expect(
      map.queries.at(-1)!.layers.every((l) => l.startsWith(sid("a", 1)))
    ).toBe(true);
    map.emit("mouseout");
    expect(map.canvas.style.cursor).toBe("wait");
    map.features = [];
    move(map);
    expect(map.canvas.style.cursor).toBe("wait");
  });

  it("is recomputed on a state change under a pointer that does not move", () => {
    let on = true;
    const { map, model, declare } = setup({ clickable: () => on });
    declare("a", 1);
    map.features = [feature("a", 1, 0)];
    move(map);
    expect(map.canvas.style.cursor).toBe("pointer");
    on = false;
    model.set("state", {});
    expect(map.canvas.style.cursor).toBe("");
    on = true;
    model.set("state", {});
    expect(map.canvas.style.cursor).toBe("pointer");
    // The layer is hidden: the live style no longer answers the query.
    map.layers.length = 0;
    model.set("state", {});
    expect(map.canvas.style.cursor).toBe("");
  });

  it("does not query when no layer is clickable", () => {
    const { map, declare } = setup();
    declare("a", 1);
    map.features = [feature("a", 1, 0)];
    move(map);
    expect(map.queries).toEqual([]);
    expect(map.canvas.style.cursor).toBe("");
  });

  it("is left alone while drawing is interactive", () => {
    const { map, model } = setup({ drawing: () => true });
    map.canvas.style.cursor = "cell";
    model.set("cursor", "crosshair");
    move(map);
    expect(map.canvas.style.cursor).toBe("cell");
  });

  it("is put back when drawing stops being interactive", () => {
    let drawing = true;
    const { map, model, pointer } = setup({ drawing: () => drawing });
    model.set("cursor", "wait");
    // Terra Draw clears its own cursor as it leaves a mode.
    map.canvas.style.cursor = "";
    pointer.drawingChanged();
    expect(map.canvas.style.cursor).toBe("");
    drawing = false;
    pointer.drawingChanged();
    expect(map.canvas.style.cursor).toBe("wait");
  });
});

describe("send", () => {
  it("sends through the guarded sender, never the model", () => {
    const sent: unknown[] = [];
    const { map, model, declare } = setup({ send: (c) => void sent.push(c) });
    model.send = () => {
      throw new Error("closed comm");
    };
    declare("a", 1);
    map.features = [feature("a", 1, 1)];
    expect(() =>
      map.emit("click", { point: [1, 2], lngLat: { lng: 0, lat: 0 } })
    ).not.toThrow();
    expect(sent).toHaveLength(1);
  });
});

describe("marker", () => {
  it("is added, moved in place, recoloured and removed", () => {
    const { model, markers, pointer } = setup();
    model.set("marker", { lnglat: [1, 2], color: "#111111" });
    expect(markers).toHaveLength(1);
    expect(markers[0]).toMatchObject({
      color: "#111111",
      lnglat: [1, 2],
      added: true,
    });
    model.set("marker", { lnglat: [3, 4], color: "#111111" });
    expect(markers).toHaveLength(1);
    expect(markers[0].lnglat).toEqual([3, 4]);
    model.set("marker", { lnglat: [3, 4], color: "#222222" });
    expect(markers).toHaveLength(2);
    expect(markers[0].removed).toBe(true);
    model.set("marker", {});
    expect(markers[1].removed).toBe(true);
    model.set("marker", { lnglat: [5, 6], color: "#222222" });
    expect(markers).toHaveLength(3);
    pointer.dispose();
    expect(markers[2].removed).toBe(true);
  });
});

describe("clusters", () => {
  /** A map whose expansion answer waits for `release`. */
  function held(map: FakePointerMap) {
    const waiting: ((zoom: number) => void)[] = [];
    map.expansionZoom = () => new Promise((resolve) => waiting.push(resolve));
    return (zoom = 11) => waiting.shift()!(zoom);
  }

  it("zooms into a clicked cluster and sends no click", async () => {
    const { map, model, declare, cluster } = setup();
    declare("a", 1);
    cluster("a", 1);
    map.features = [bubble("a", 1), feature("a", 1, 1)];
    const original = { type: "click" };
    map.emit("click", {
      point: [1, 2],
      lngLat: { lng: 0, lat: 0 },
      originalEvent: original,
    });
    await settle();
    expect(model.sent).toEqual([]);
    expect(map.eased).toEqual([
      {
        options: { center: [3, 4], zoom: 9 },
        eventData: { originalEvent: original },
      },
    ]);
  });

  it("expands a bubble under a fill of a higher data layer or the overlay zone", async () => {
    const { map, model, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    declare("b", 1);
    declare("overlay", 1);
    map.features = [
      Object.assign(feature("b", 1, 1), { layer: `${sid("b", 1)}:fill` }),
      Object.assign(feature("overlay", 1, 1), {
        layer: `${sid("overlay", 1)}:fill`,
      }),
      Object.assign(bubble("a", 1), { layer: `${sid("a", 1)}:cluster` }),
    ] as RenderedFeature[];
    click();
    await settle();
    expect(model.sent).toEqual([]);
    expect(map.eased).toHaveLength(1);
  });

  it("sends the click when the feature above a bubble is clickable", async () => {
    const { map, model, declare, cluster, click } = setup({
      clickable: (id) => id === "b",
    });
    declare("a", 1);
    cluster("a", 1);
    declare("b", 1);
    map.features = [
      Object.assign(feature("b", 1, 1), { layer: `${sid("b", 1)}:fill` }),
      Object.assign(bubble("a", 1), { layer: `${sid("a", 1)}:cluster` }),
    ] as RenderedFeature[];
    click();
    await settle();
    expect(model.sent).toHaveLength(1);
  });

  it("queries the cluster layers with the others", () => {
    const { map, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    click();
    expect(map.queries[0].layers).toContain(`${sid("a", 1)}:cluster`);
  });

  it("leaves clusters out of the hits", () => {
    const { map, model, declare, click } = setup();
    declare("a", 1);
    map.features = [feature("a", 1, 1, { n: 1 })];
    click();
    expect(model.sent[0].features).toHaveLength(1);
  });

  it("does nothing for a cluster id that is not a number", async () => {
    const { map, model, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const calls: number[] = [];
    map.expansionZoom = async (id) => (calls.push(id), 9);
    for (const bad of ["7", NaN, null, {}]) {
      map.features = [bubble("a", 1, bad)];
      click();
    }
    await settle();
    expect(calls).toEqual([]);
    expect(map.eased).toEqual([]);
    expect(model.sent).toEqual([]);
  });

  it("does not move when the source was replaced meanwhile", async () => {
    const { map, model, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1)];
    click();
    cluster("a", 2);
    release();
    await settle();
    expect(map.eased).toEqual([]);
    model.values.state = {};
  });

  it("does not move when the layer was hidden meanwhile", async () => {
    const { map, model, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1)];
    click();
    (model.values.state as any).layers[0].visible = false;
    release();
    await settle();
    expect(map.eased).toEqual([]);
  });

  it("does not move when the view was disposed meanwhile", async () => {
    const { map, pointer, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1)];
    click();
    pointer.dispose();
    release();
    await settle();
    expect(map.eased).toEqual([]);
    expect(map.count("movestart")).toBe(0);
  });

  it("lets a newer cluster click win", async () => {
    const { map, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1, 1)];
    click();
    map.features = [bubble("a", 1, 2)];
    click();
    release(5);
    release(12);
    await settle();
    expect(map.eased.map((e: any) => e.options.zoom)).toEqual([12]);
  });

  it("yields to a newer view request", async () => {
    const { map, model, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1)];
    click();
    model.set("view_request", { seq: 2 });
    release();
    await settle();
    expect(map.eased).toEqual([]);
  });

  it("yields to a user gesture but not to a programmatic move", async () => {
    const { map, declare, cluster, click } = setup();
    declare("a", 1);
    cluster("a", 1);
    const release = held(map);
    map.features = [bubble("a", 1)];
    click();
    map.emit("movestart", {});
    release();
    await settle();
    expect(map.eased).toHaveLength(1);

    map.features = [bubble("a", 1)];
    click();
    map.emit("movestart", { originalEvent: { type: "mousedown" } });
    release();
    await settle();
    expect(map.eased).toHaveLength(1);
  });

  it("shows the pointer cursor over a cluster of a clustered layer", () => {
    const { map, declare, cluster } = setup({ clustered: (id) => id === "a" });
    declare("a", 1);
    cluster("a", 1);
    map.features = [bubble("a", 1)];
    map.emit("mousemove", { point: [1, 1], lngLat: { lng: 0, lat: 0 } });
    expect(map.canvas.style.cursor).toBe("pointer");
    expect(map.queries.at(-1)!.layers).toEqual([`${sid("a", 1)}:cluster`]);
  });
});

describe("a picked map", () => {
  /** A second map `pick` returns for every point, as a compare view's right half. */
  function picked(options: Parameters<typeof setup>[0] = {}) {
    const other = new FakePointerMap();
    const points: unknown[] = [];
    const ctx = setup({
      ...options,
      pick: (point) => {
        points.push(point);
        return other;
      },
    });
    return { ...ctx, other, points };
  }
  const AT = { x: 600, y: 40 };

  it("gives a click its hits, deduplicated through its own sources", () => {
    const { map, model, other, points } = picked();
    declareOn(map, "l", 1);
    map.features = [feature("l", 1, 0)];
    declareOn(other, "r", 1);
    other.features = [
      feature("r", 1, 0, { n: 1 }),
      feature("r", 1, 0, { n: 1 }),
    ];
    map.emit("click", { point: AT, lngLat: { lng: 10, lat: 20 } });
    expect(model.sent).toHaveLength(1);
    expect(model.sent[0].features).toEqual([
      { id: "r", instance: 1, properties: { n: 1 } },
    ]);
    expect(map.queries).toEqual([]);
    expect(points.length).toBeGreaterThan(0);
    expect(points.every((p) => p === AT)).toBe(true);
  });

  it("decides the main canvas's cursor", () => {
    const { map, other } = picked({ clickable: (id) => id === "r" });
    declareOn(other, "r", 1);
    other.features = [feature("r", 1, 0)];
    map.emit("mousemove", { point: AT, lngLat: { lng: 0, lat: 0 } });
    expect(map.canvas.style.cursor).toBe("pointer");
    expect(other.canvas.style.cursor).toBe("");
    expect(map.queries).toEqual([]);
  });

  it("expands a cluster of its own source, and the main map eases", async () => {
    const { map, model, other, cluster } = picked();
    declareOn(other, "a", 1);
    cluster("a", 1, other);
    other.expansionZoom = async () => 12;
    other.features = [bubble("a", 1)];
    const original = { type: "click" };
    map.emit("click", {
      point: AT,
      lngLat: { lng: 0, lat: 0 },
      originalEvent: original,
    });
    await settle();
    expect(model.sent).toEqual([]);
    expect(map.eased).toEqual([
      {
        options: { center: [3, 4], zoom: 12 },
        eventData: { originalEvent: original },
      },
    ]);
    expect(other.eased).toEqual([]);
  });
});
