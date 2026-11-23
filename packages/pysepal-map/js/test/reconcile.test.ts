import type { LayerSpecification, SourceSpecification } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import fixture from "./fixtures/state.json";
import { FakeMap } from "./fake-map";
import {
  OWNED_PREFIX,
  apply,
  plan,
  reconcile,
  type Op,
  type ResolvePayload,
} from "../reconcile";
import { toOwnedStyle } from "../translate";
import type {
  BasemapState,
  InteractionState,
  LayerState,
  MapState,
  OwnedStyle,
  VectorPaint,
} from "../types";

type Payload = ReturnType<ResolvePayload>;

const base = fixture as unknown as MapState;
const V1_DIGEST = (base.layers[0].source as { digest: string }).digest;

const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value));
const isOwned = (id: string) => id.startsWith(OWNED_PREFIX);

function withState(mutate: (state: MapState) => void): MapState {
  const state = clone(base);
  mutate(state);
  return state;
}

function payloads() {
  const cache = new Map<string, Payload>();
  const resolved: string[] = [];
  const resolve: ResolvePayload = (digest) => {
    resolved.push(digest);
    let payload = cache.get(digest);
    if (!payload) {
      payload = {
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { digest },
            geometry: { type: "Point", coordinates: [cache.size, 0] },
          },
        ],
      };
      cache.set(digest, payload);
    }
    return payload;
  };
  return {
    resolve,
    resolved,
    payloadOf: (digest: string) => cache.get(digest),
  };
}

const EMPTY: Payload = { type: "FeatureCollection", features: [] };

const FOREIGN_SOURCES: Record<string, SourceSpecification> = {
  td: { type: "geojson", data: EMPTY },
  "td-tiles": { type: "raster", tiles: ["https://f/{z}/{x}/{y}.png"] },
};
const FOREIGN_LAYERS: LayerSpecification[] = [
  {
    id: "td-poly",
    type: "fill",
    source: "td",
    paint: { "fill-color": "#f00" },
  },
  {
    id: "td-point",
    type: "circle",
    source: "td",
    paint: { "circle-radius": 4 },
  },
];

const withForeign = () =>
  new FakeMap({ sources: FOREIGN_SOURCES, layers: FOREIGN_LAYERS });

/** Rendering-equivalent form of a layer: unset values and defaults dropped. */
function canonical(layer: LayerSpecification | undefined) {
  const out: Record<string, any> = clone(layer ?? {});
  for (const group of ["layout", "paint"]) {
    const entries = Object.entries(out[group] ?? {}).filter(
      ([name, value]) =>
        value != null && !(name === "visibility" && value === "visible")
    );
    if (entries.length) out[group] = Object.fromEntries(entries);
    else delete out[group];
  }
  if (!out.minzoom) delete out.minzoom;
  return out;
}

function snapshotForeign(fake: FakeMap) {
  const order = fake.layerOrder().filter((id) => !isOwned(id));
  const sourceIds = fake.sourceIds().filter((id) => !isOwned(id));
  return {
    order,
    layers: order.map((id) => fake.layer(id)),
    sourceIds,
    specs: sourceIds.map((id) => fake.sourceSpec(id)),
    payloads: sourceIds.map((id) => fake.payload(id)),
  };
}

function expectForeignUntouched(
  fake: FakeMap,
  before: ReturnType<typeof snapshotForeign>,
  at = ""
) {
  const order = fake.layerOrder();
  const foreign = order.filter((id) => !isOwned(id));
  expect(foreign, at).toEqual(before.order);
  expect(
    foreign.map((id) => fake.layer(id)),
    at
  ).toEqual(before.layers);
  const owned = order.filter(isOwned);
  expect(order.slice(0, owned.length), `${at} owned below foreign`).toEqual(
    owned
  );
  const sourceIds = fake.sourceIds().filter((id) => !isOwned(id));
  expect(sourceIds, at).toEqual(before.sourceIds);
  expect(
    sourceIds.map((id) => fake.sourceSpec(id)),
    at
  ).toEqual(before.specs);
  sourceIds.forEach((id, i) =>
    expect(fake.payload(id), at).toBe(before.payloads[i])
  );
  for (const call of fake.calls) {
    expect(isOwned(call.id), `${at} ${call.method} ${call.id}`).toBe(true);
  }
}

function expectConverged(
  fake: FakeMap,
  desired: OwnedStyle,
  payloadOf: (digest: string) => Payload | undefined,
  at = ""
) {
  const owned = fake.layerOrder().filter(isOwned);
  expect(owned, at).toEqual(desired.layers.map((layer) => layer.id));
  for (const layer of desired.layers) {
    expect(canonical(fake.layer(layer.id)), `${at} ${layer.id}`).toEqual(
      canonical(layer)
    );
  }
  const sourceIds = fake.sourceIds().filter(isOwned).sort();
  expect(sourceIds, at).toEqual(desired.sources.map((s) => s.id).sort());
  for (const source of desired.sources) {
    expect(fake.sourceSpec(source.id), `${at} ${source.id}`).toEqual(
      source.spec
    );
    if (source.digest) {
      const payload = payloadOf(source.digest);
      expect(payload, at).toBeDefined();
      expect(fake.payload(source.id), `${at} ${source.id}`).toBe(payload);
    }
  }
  expect(plan(fake, desired), `${at} second plan`).toEqual([]);
}

const describeOp = (op: Op) =>
  `${op.kind} ${op.kind === "addLayer" ? op.layer.id : op.id}`;

describe("FakeMap", () => {
  it("rejects what MapLibre rejects", () => {
    const fake = withForeign();
    expect(() =>
      fake.addSource("td", { type: "geojson", data: EMPTY })
    ).toThrow(/already exists/);
    expect(() =>
      fake.addLayer({ id: "td-poly", type: "fill", source: "td" })
    ).toThrow(/already exists/);
    expect(() => fake.removeSource("td")).toThrow(/cannot be removed/);
    expect(() =>
      fake.addLayer({ id: "x", type: "fill", source: "td" }, "nope")
    ).toThrow(/non-existing layer "nope"/);
    expect(() => fake.moveLayer("td-poly", "nope")).toThrow(
      /non-existing layer "nope"/
    );
    expect(() =>
      fake.addLayer({ id: "x", type: "fill", source: "nope" })
    ).toThrow(/not found/);
    expect(() => fake.addSource("g", { type: "geojson" } as any)).toThrow(
      /"data"/
    );
    expect(() =>
      fake.addSource("g", { type: "geojson", data: EMPTY, digest: "x" } as any)
    ).toThrow(/unknown property "digest"/);
    expect(() => fake.setPaint("td-poly", "line-color", "#000")).toThrow(
      /unknown property/
    );
    expect(() => fake.setTiles("td", ["x"])).toThrow(/no tiles/);
    expect(fake.layerOrder()).toEqual(["td-poly", "td-point"]);
  });

  it("guards the payload of a live GeoJSON source", () => {
    expect(() => JSON.stringify(withForeign().source("td"))).toThrow(/payload/);
  });

  it("moves a layer to the top without a beforeId", () => {
    const fake = withForeign();
    fake.moveLayer("td-poly");
    expect(fake.layerOrder()).toEqual(["td-point", "td-poly"]);
    fake.moveLayer("td-point", "td-point");
    expect(fake.layerOrder()).toEqual(["td-point", "td-poly"]);
  });

  it("keeps a zoom bound that setZoomRange leaves out", () => {
    const fake = withForeign();
    fake.setZoomRange("td-poly", 2, 10);
    fake.setZoomRange("td-poly", 3);
    expect(fake.layer("td-poly")).toMatchObject({ minzoom: 3, maxzoom: 10 });
  });
});

describe("reconcile", () => {
  it("never reads a foreign layer, which a custom one cannot serialize", () => {
    const fake = withForeign();
    const { resolve, payloadOf } = payloads();
    const style = toOwnedStyle(base);
    reconcile(fake, style, resolve);
    fake.addCustomLayer("td-custom", fake.layerOrder().find(isOwned));

    reconcile(fake, style, resolve);
    expectConverged(fake, style, payloadOf);
    const order = fake.layerOrder();
    const owned = order.filter(isOwned);
    expect(order.slice(owned.length)).toEqual([
      "td-custom",
      "td-poly",
      "td-point",
    ]);
    const fewer = toOwnedStyle(withState((s) => void s.layers.pop()));
    reconcile(fake, fewer, resolve);
    expectConverged(fake, fewer, payloadOf);
  });

  it("reaches the desired style from empty", () => {
    const fake = new FakeMap();
    const style = toOwnedStyle(base);
    const { resolve, resolved, payloadOf } = payloads();
    reconcile(fake, style, resolve);
    expect(fake.layerOrder()).toEqual(style.layers.map((layer) => layer.id));
    expect(resolved).toEqual([V1_DIGEST]);
    expectConverged(fake, style, payloadOf);
  });

  it("hiding and showing never moves a layer", () => {
    const fake = new FakeMap();
    const { resolve, payloadOf } = payloads();
    reconcile(fake, toOwnedStyle(base), resolve);

    const hidden = toOwnedStyle(
      withState((state) => {
        state.layers[0].visible = false;
      })
    );
    const hide = plan(fake, hidden);
    expect(hide).toHaveLength(5);
    expect(hide).toEqual(
      expect.arrayContaining(
        ["fill", "line", "circle", "cluster", "count"].map((part) => ({
          kind: "setLayout",
          id: `psm:v1:1:${part}`,
          name: "visibility",
          value: "none",
        }))
      )
    );
    apply(fake, hide, resolve);
    expectConverged(fake, hidden, payloadOf);

    const show = plan(fake, toOwnedStyle(base));
    expect(show).toHaveLength(5);
    for (const op of show) {
      expect(op).toMatchObject({ kind: "setLayout", value: "visible" });
    }
  });

  it("a new instance id replaces the source and its layers", () => {
    const fake = new FakeMap();
    const { resolve, payloadOf } = payloads();
    reconcile(fake, toOwnedStyle(base), resolve);

    const next = toOwnedStyle(
      withState((state) => {
        state.layers[1].instance = 7; // pm
      })
    );
    const ops = plan(fake, next);
    expect(ops.map(describeOp)).toEqual([
      "removeLayer psm:pm:2:fill",
      "removeLayer psm:pm:2:line",
      "removeLayer psm:pm:2:circle",
      "removeSource psm:pm:2",
      "addSource psm:pm:7",
      "addLayer psm:pm:7:circle",
      "addLayer psm:pm:7:line",
      "addLayer psm:pm:7:fill",
    ]);
    expect(ops[5]).toMatchObject({ beforeId: "psm:v1:1:fill" });
    apply(fake, ops, resolve);
    expectConverged(fake, next, payloadOf);
  });

  it("a basemap tiles-only change uses setTiles", () => {
    const fake = new FakeMap();
    const { resolve, payloadOf } = payloads();
    reconcile(fake, toOwnedStyle(base), resolve);

    const tiles = ["https://u/{z}/{x}/{y}.png", "https://v/{z}/{x}/{y}.png"];
    const next = toOwnedStyle(
      withState((state) => {
        state.basemap!.tiles = tiles;
      })
    );
    const ops = plan(fake, next);
    expect(ops).toEqual([{ kind: "setTiles", id: "psm:basemap", tiles }]);
    apply(fake, ops, resolve);
    expectConverged(fake, next, payloadOf);
  });

  it("a basemap attribution or max zoom change detaches the layer, then replaces the source", () => {
    const changes: ((basemap: BasemapState) => void)[] = [
      (b) => (b.attribution = "© Other"),
      (b) => (b.attribution = ""),
      (b) => (b.max_zoom = 12),
      (b) => (b.max_zoom = null),
      (b) => {
        b.tiles = ["https://u/{z}/{x}/{y}.png"];
        b.max_zoom = 18;
      },
    ];
    for (const change of changes) {
      const fake = new FakeMap();
      const { resolve, payloadOf } = payloads();
      reconcile(fake, toOwnedStyle(base), resolve);

      const next = toOwnedStyle(withState((state) => change(state.basemap!)));
      const ops = plan(fake, next);
      expect(ops.map(describeOp)).toEqual([
        "removeLayer psm:basemap",
        "removeSource psm:basemap",
        "addSource psm:basemap",
        "addLayer psm:basemap",
      ]);
      expect(ops[3]).toMatchObject({ beforeId: "psm:r1:3:raster" });
      apply(fake, ops, resolve);
      expectConverged(fake, next, payloadOf);
    }
  });

  it("foreign layers are kept and stay above owned layers", () => {
    const fake = withForeign();
    const before = snapshotForeign(fake);
    const style = toOwnedStyle(base);
    const { resolve, payloadOf } = payloads();

    reconcile(fake, style, resolve);
    expect(fake.layerOrder()).toEqual([
      ...style.layers.map((layer) => layer.id),
      "td-poly",
      "td-point",
    ]);
    expectConverged(fake, style, payloadOf);
    expectForeignUntouched(fake, before);

    fake.moveLayer("psm:v1:1:line"); // drifts above the foreign layers
    fake.calls.length = 0;
    expect(plan(fake, style)).toEqual([
      { kind: "moveLayer", id: "psm:v1:1:line", beforeId: "psm:v1:1:circle" },
    ]);
    reconcile(fake, style, resolve);
    expectConverged(fake, style, payloadOf);
    expectForeignUntouched(fake, before);

    const empty = { sources: [], layers: [] };
    reconcile(fake, empty, resolve);
    expect(fake.layerOrder()).toEqual(["td-poly", "td-point"]);
    expectConverged(fake, empty, payloadOf);
    expectForeignUntouched(fake, before);
  });

  it("resets the properties the desired style leaves out", () => {
    const fake = new FakeMap();
    const style = toOwnedStyle(base);
    const { resolve, payloadOf } = payloads();
    reconcile(fake, style, resolve);
    const circle = style.layers.find((l) => l.id === "psm:v1:1:circle")!;

    fake.setPaint("psm:v1:1:fill", "fill-antialias", false);
    fake.setLayout("psm:pm:2:line", "line-cap", "round");
    fake.setLayout("psm:pm:2:circle", "visibility", null);
    fake.setFilter("psm:v1:1:circle", null);
    fake.setZoomRange("psm:r1:3:raster", 4);
    const ops = plan(fake, style);
    expect(ops).toHaveLength(4);
    expect(ops).toEqual(
      expect.arrayContaining([
        {
          kind: "setPaint",
          id: "psm:v1:1:fill",
          name: "fill-antialias",
          value: null,
        },
        {
          kind: "setLayout",
          id: "psm:pm:2:line",
          name: "line-cap",
          value: null,
        },
        {
          kind: "setFilter",
          id: "psm:v1:1:circle",
          filter: (circle as { filter: unknown }).filter,
        },
        { kind: "setZoomRange", id: "psm:r1:3:raster", min: 0 },
      ])
    );
    apply(fake, ops, resolve);
    expectConverged(fake, style, payloadOf);
  });

  it("sets a layer max zoom in place and recreates the layer to clear it", () => {
    const fake = new FakeMap();
    const { resolve, payloadOf } = payloads();
    const open = toOwnedStyle(base);
    const capped = toOwnedStyle(
      withState((state) => {
        state.layers[2].max_zoom = 18; // r1
      })
    );
    reconcile(fake, open, resolve);

    const cap = plan(fake, capped);
    expect(cap).toEqual([
      { kind: "setZoomRange", id: "psm:r1:3:raster", min: 0, max: 18 },
    ]);
    apply(fake, cap, resolve);
    expectConverged(fake, capped, payloadOf);

    // MapLibre's setLayerZoomRange cannot unset a bound.
    const uncap = plan(fake, open);
    expect(uncap).toEqual([
      { kind: "removeLayer", id: "psm:r1:3:raster" },
      {
        kind: "addLayer",
        layer: open.layers.find((l) => l.id === "psm:r1:3:raster"),
        beforeId: "psm:pm:2:fill",
      },
    ]);
    apply(fake, uncap, resolve);
    expectConverged(fake, open, payloadOf);
  });

  it("reorders and restyles without resolving or reading payloads", () => {
    const fake = withForeign();
    const { resolve, resolved, payloadOf } = payloads();
    reconcile(fake, toOwnedStyle(base), resolve);
    resolved.length = 0;

    const next = toOwnedStyle(
      withState((state) => {
        state.layers.reverse();
        state.layers[0].zone = "overlay";
        for (const layer of state.layers) {
          layer.opacity = 0.5;
          if (layer.paint) layer.paint.stroke = "#000000";
        }
      })
    );
    reconcile(fake, next, resolve);
    expect(resolved).toEqual([]);
    expectConverged(fake, next, payloadOf);
  });

  it("resolves every payload before it changes the map", () => {
    const fake = new FakeMap();
    const missing: ResolvePayload = () => {
      throw new Error("payload missing");
    };
    expect(() => reconcile(fake, toOwnedStyle(base), missing)).toThrow(
      "payload missing"
    );
    expect(fake.calls).toEqual([]);
  });

  it("refuses to plan ids it does not own", () => {
    const desired: OwnedStyle = {
      sources: [{ id: "mine", spec: { type: "geojson" }, digest: V1_DIGEST }],
      layers: [{ id: "mine", type: "fill", source: "mine" }],
    };
    expect(() => plan(new FakeMap(), desired)).toThrow(/psm:/);
  });

  it("random desired states converge", () => {
    const rnd = mulberry32(0x5eed);
    const gen = new StateGenerator(rnd);
    const fake = withForeign();
    const before = snapshotForeign(fake);
    const { resolve, payloadOf } = payloads();
    const kinds = new Map<Op["kind"], number>();

    const converge = (desired: OwnedStyle, at: string) => {
      fake.calls.length = 0;
      const ops = plan(fake, desired);
      apply(fake, ops, resolve);
      for (const op of ops) kinds.set(op.kind, (kinds.get(op.kind) ?? 0) + 1);
      expectConverged(fake, desired, payloadOf, at);
      expectForeignUntouched(fake, before, at);
    };

    for (let step = 0; step < 1000; step++) {
      const desired = toOwnedStyle(gen.next());
      converge(desired, `step ${step}`);
      // Drift behind the reconciler's back is undone on the next pass.
      if (rnd() < 0.25) {
        tamper(fake, rnd, step);
        converge(desired, `step ${step} after tampering`);
      }
    }

    const all: Op["kind"][] = [
      "addSource",
      "removeSource",
      "setTiles",
      "addLayer",
      "removeLayer",
      "moveLayer",
      "setLayout",
      "setPaint",
      "setFilter",
      "setZoomRange",
    ];
    for (const kind of all) expect(kinds.get(kind), kind).toBeGreaterThan(10);
  });
});

function mulberry32(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const POOL = ["a", "b", "c", "d", "e", "f", "g h", "i:j"];
const COLORS = ["#3388ff", "#ff7800", "#000000", "#e31a1c"];
const DIGESTS = ["1", "2", "3", "4", "5"].map((c) => c.repeat(64));
const PMTILES = ["https://x.org/a.pmtiles", "https://x.org/b.pmtiles"];
const TILE_SETS = [
  ["https://r/{z}/{x}/{y}.png"],
  ["https://s/{z}/{x}/{y}.png", "https://s2/{z}/{x}/{y}.png"],
];
const BASEMAP_TILES = [
  ["https://t/{z}/{x}/{y}.png"],
  ["https://u/{z}/{x}/{y}.png"],
  ["https://v/{z}/{x}/{y}.png", "https://w/{z}/{x}/{y}.png"],
];

/**
 * Walks through states the way a caller drawing repeatedly would: layers
 * persist, change a few properties, reorder, and get new instances when
 * their source, attribution or token changes. Now and then a raster or
 * PMTiles source changes under the same instance, which the widget never
 * does, to drive in-place source replacement and layer re-creation. A
 * GeoJSON digest never does, because its id is its only identity.
 */
class StateGenerator {
  private layers: LayerState[] = [];
  private basemap: BasemapState | null = clone(base.basemap);
  private instance = 0;
  private revision = 0;

  constructor(private rnd: () => number) {}

  next(): MapState {
    const roll = this.rnd();
    let ids = this.layers.map((layer) => layer.id);
    if (roll < 0.35) {
      // same layers, same order
    } else if (roll < 0.6) {
      ids = this.edit(ids);
    } else {
      ids = this.shuffle(POOL).slice(0, this.int(0, POOL.length));
    }
    const previous = new Map(this.layers.map((layer) => [layer.id, layer]));
    this.layers = ids.map((id) => this.layer(id, previous.get(id)));
    this.basemap = this.nextBasemap(this.basemap);
    return {
      revision: ++this.revision,
      theme: "light",
      compare: false,
      controls: {
        zoom: true,
        fullscreen: true,
        scale: true,
        coordinates: false,
      },
      basemap: clone(this.basemap),
      layers: clone(this.layers),
    };
  }

  private edit(ids: string[]): string[] {
    const out = [...ids];
    const absent = POOL.filter((id) => !out.includes(id));
    const roll = this.rnd();
    if (roll < 0.4 && out.length > 1) {
      const i = this.int(0, out.length - 2);
      [out[i], out[i + 1]] = [out[i + 1], out[i]];
    } else if (roll < 0.7 && out.length) {
      out.splice(this.int(0, out.length - 1), 1);
    } else if (absent.length) {
      out.splice(this.int(0, out.length), 0, this.pick(absent));
    }
    return out;
  }

  private layer(id: string, old?: LayerState): LayerState {
    const kind = old && !this.chance(0.05) ? old.kind : this.pick(KINDS);
    const sameKind = old?.kind === kind;
    let source = sameKind && !this.chance(0.1) ? old.source : this.source(kind);
    const attribution =
      old && !this.chance(0.08)
        ? old.attribution
        : this.pick(["", "© A", "© B"]);
    const token = old && !this.chance(0.05) ? old.token : this.int(1, 4);
    const keep =
      sameKind &&
      source === old.source &&
      attribution === old.attribution &&
      token === old.token;
    if (keep && kind !== "geojson" && this.chance(0.05)) {
      source = this.source(kind);
    }

    const vary = <T>(value: T | undefined, options: readonly T[]): T =>
      value !== undefined && !this.chance(0.15) ? value : this.pick(options);
    const layer = {
      id,
      kind,
      token,
      instance: keep ? old.instance : ++this.instance,
      zone: vary(old?.zone, ["data", "data", "data", "overlay"] as const),
      visible: vary(old?.visible, [true, true, true, false]),
      opacity: vary(old?.opacity, [0, 0.5, 0.8, 1]),
      min_zoom: vary(old?.min_zoom, [0, 0, 0, 2, 5]),
      max_zoom: vary(old?.max_zoom, [null, null, 12, 18]),
      attribution,
      interaction:
        kind === "raster"
          ? null
          : vary(old ? old.interaction : undefined, INTERACTIONS),
      source,
      paint: kind === "raster" ? null : this.paint(old?.paint ?? undefined),
    };
    return layer as LayerState;
  }

  private paint(old?: VectorPaint): VectorPaint {
    const vary = <T>(value: T | undefined, options: readonly T[]): T =>
      value !== undefined && !this.chance(0.15) ? value : this.pick(options);
    return {
      stroke: vary(old?.stroke, COLORS),
      fill: vary(old?.fill, [null, ...COLORS]),
      fill_opacity: vary(old?.fill_opacity, [0, 0.3, 1]),
      width: vary(old?.width, [1, 2, 3.5]),
      point_radius: vary(old?.point_radius, [3, 5, 8]),
      marker: vary(old?.marker, ["circle", "pin"] as const),
      color_by: null,
      class_colors: [],
    };
  }

  private source(kind: LayerState["kind"]): LayerState["source"] {
    switch (kind) {
      case "geojson":
        return {
          digest: this.pick(DIGESTS),
          cluster: this.pick([null, null, { radius: 40, max_zoom: 12 }]),
        };
      case "pmtiles":
        return {
          url: this.pick(PMTILES),
          source_layer: this.pick(["roads", "water"]),
        };
      case "raster":
        return {
          tiles: this.pick(TILE_SETS),
          tile_size: this.pick([256, 512]),
          max_native_zoom: this.pick([null, 18, 20]),
          bounds: this.pick([null, [-10, -5, 10, 5]] as const),
        } as LayerState["source"];
    }
  }

  private nextBasemap(old: BasemapState | null): BasemapState | null {
    if (this.chance(0.6)) return old;
    if (!old || this.chance(0.2)) {
      return this.chance(0.4)
        ? null
        : {
            tiles: this.pick(BASEMAP_TILES),
            attribution: this.pick(["", "© OSM", "© Esri"]),
            max_zoom: this.pick([null, 18, 19]),
          };
    }
    const next = clone(old);
    const field = this.pick(["tiles", "tiles", "attribution", "max_zoom"]);
    if (field === "tiles") next.tiles = this.pick(BASEMAP_TILES);
    if (field === "attribution") {
      next.attribution = this.pick(["", "© OSM", "© Esri"]);
    }
    if (field === "max_zoom") next.max_zoom = this.pick([null, 18, 19]);
    return next;
  }

  private chance(p: number): boolean {
    return this.rnd() < p;
  }

  private int(min: number, max: number): number {
    return min + Math.floor(this.rnd() * (max - min + 1));
  }

  private pick<T>(options: readonly T[]): T {
    return options[Math.floor(this.rnd() * options.length)];
  }

  private shuffle<T>(items: readonly T[]): T[] {
    const out = [...items];
    for (let i = out.length - 1; i > 0; i--) {
      const j = this.int(0, i);
      [out[i], out[j]] = [out[j], out[i]];
    }
    return out;
  }
}

const INTERACTIONS: (InteractionState | null)[] = [
  null,
  null,
  { popup: [], tooltip: null },
  {
    popup: [["name", "Name"]],
    tooltip: [
      ["name", "name"],
      ["id", "id"],
    ],
  },
  { popup: null, tooltip: [] },
];

const KINDS = ["geojson", "pmtiles", "raster"] as const;

const EXTRA_PAINT: Record<string, [string, unknown]> = {
  fill: ["fill-antialias", false],
  line: ["line-blur", 2],
  circle: ["circle-blur", 1],
  symbol: ["icon-halo-width", 1],
  raster: ["raster-saturation", -1],
};
const MAIN_PAINT: Record<string, [string, unknown]> = {
  fill: ["fill-color", "#123456"],
  line: ["line-width", 9],
  circle: ["circle-radius", 1],
  symbol: ["icon-opacity", 0.25],
  raster: ["raster-opacity", 0.25],
};

/** Changes the live map behind the reconciler's back. */
function tamper(fake: FakeMap, rnd: () => number, step: number) {
  const pick = <T>(options: readonly T[]): T =>
    options[Math.floor(rnd() * options.length)];
  const owned = fake.layerOrder().filter(isOwned);
  const action = pick([
    "top",
    "move",
    "extra",
    "restyle",
    "visibility",
    "zoom",
    "filter",
    "remove",
    "stray",
  ]);
  if (action === "stray") {
    const id = `psm:stray:${step}`;
    fake.addSource(id, { type: "raster", tiles: ["https://z/{z}/{x}/{y}"] });
    fake.addLayer({ id: `${id}:raster`, type: "raster", source: id });
    return;
  }
  if (!owned.length) return;
  const id = pick(owned);
  const layer = fake.layer(id)!;
  switch (action) {
    case "top":
      return fake.moveLayer(id);
    case "move":
      return fake.moveLayer(id, pick(fake.layerOrder()));
    case "extra":
      return fake.setPaint(id, ...EXTRA_PAINT[layer.type]);
    case "restyle":
      return fake.setPaint(id, ...MAIN_PAINT[layer.type]);
    case "visibility": {
      const hidden = (layer.layout as any)?.visibility === "none";
      return fake.setLayout(id, "visibility", hidden ? "visible" : "none");
    }
    case "zoom":
      return fake.setZoomRange(id, 3, 15);
    case "filter": {
      const vector = owned.filter(
        (other) => fake.layer(other)!.type !== "raster"
      );
      if (vector.length) fake.setFilter(pick(vector), null);
      return;
    }
    case "remove":
      return fake.removeLayer(id);
  }
}
