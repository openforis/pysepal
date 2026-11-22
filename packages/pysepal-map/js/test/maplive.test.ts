import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it } from "vitest";

import { MapSync, type ViewModel } from "../maplive";
import { StatusReporter } from "../status";
import type { GeoJSONLayerState, MapState } from "../types";
import { FakeMap } from "./fake-map";

type Listener = (...args: any[]) => void;

class Emitter {
  private readonly listeners = new Map<string, Set<Listener>>();

  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string, ...args: unknown[]) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) {
      listener(...args);
    }
  }
}

/**
 * The MapLibre map MapSync drives, over a FakeMap. Each added source gets a
 * new object, as in MapLibre, and its worker load completes only when the
 * test says so.
 */
class FakeMapLibre extends Emitter {
  readonly fake = new FakeMap();
  private readonly objects = new Map<string, object>();

  get style() {
    const ids = this.fake.sourceIds();
    return { tileManagers: Object.fromEntries(ids.map((id) => [id, {}])) };
  }

  getLayersOrder = () => this.fake.layerOrder();
  getLayer = (id: string) =>
    this.fake.layerOrder().includes(id)
      ? { serialize: () => this.fake.layer(id) }
      : undefined;
  getSource = (id: string) => this.objects.get(id);
  addSource = (id: string, spec: any) => {
    this.fake.addSource(id, spec);
    this.objects.set(id, { serialize: () => this.fake.source(id) });
  };
  removeSource = (id: string) => {
    this.fake.removeSource(id);
    this.objects.delete(id);
  };
  addLayer = (spec: any, beforeId?: string) =>
    this.fake.addLayer(spec, beforeId);
  removeLayer = (id: string) => this.fake.removeLayer(id);
  moveLayer = (id: string, beforeId?: string) =>
    this.fake.moveLayer(id, beforeId);
  setLayoutProperty = (id: string, name: string, value: unknown) =>
    this.fake.setLayout(id, name, value);
  setPaintProperty = (id: string, name: string, value: unknown) =>
    this.fake.setPaint(id, name, value);
  setFilter = (id: string, filter: unknown) => this.fake.setFilter(id, filter);
  setLayerZoomRange = (id: string, min: number, max?: number) =>
    this.fake.setZoomRange(id, min, max);

  /** The worker finished loading the data of every GeoJSON source. */
  loadAll() {
    for (const sourceId of this.fake.sourceIds()) {
      this.emit("sourcedata", {
        sourceId,
        sourceDataType: "content",
        isSourceLoaded: true,
      });
    }
  }
}

class FakeModel extends Emitter implements ViewModel {
  readonly sent: any[] = [];
  readonly pulls: any[] = [];

  constructor(private state: unknown) {
    super();
  }

  get(_name: "state"): unknown {
    return this.state;
  }

  set(state: unknown) {
    this.state = state;
    this.emit("change:state");
  }

  send(content: any) {
    this.sent.push(content);
    if (content.type === "pull") this.pulls.push(content);
  }

  /** Answer every pull so far from `payloads`. */
  answer(payloads: Record<string, unknown>) {
    const digests = this.sent.flatMap((m) =>
      m.type === "pull" ? m.digests : []
    );
    this.sent.length = 0;
    for (const digest of new Set<string>(digests)) {
      const bytes = new TextEncoder().encode(JSON.stringify(payloads[digest]));
      this.emit("msg:custom", { type: "data", digest }, [bytes]);
    }
  }
}

const points = (...xy: number[][]) => ({
  type: "FeatureCollection",
  features: xy.map((coordinates) => ({
    type: "Feature",
    properties: {},
    geometry: { type: "Point", coordinates },
  })),
});

const PAYLOADS = { x: points([-20, 0]), y: points([20, 0]) };

function geojson(
  id: string,
  instance: number,
  digest: string
): GeoJSONLayerState {
  return {
    id,
    kind: "geojson",
    token: 0,
    instance,
    zone: "data",
    visible: true,
    opacity: 1,
    min_zoom: 0,
    max_zoom: null,
    attribution: "",
    interaction: null,
    source: { digest, cluster: null },
    paint: {
      stroke: "#3388ff",
      fill: null,
      fill_opacity: 0,
      width: 2,
      point_radius: 5,
      marker: "circle",
    },
  };
}

const state = (revision: number, ...layers: GeoJSONLayerState[]): MapState => ({
  revision,
  theme: "light",
  controls: { zoom: true, fullscreen: true, scale: true, coordinates: false },
  basemap: null,
  layers,
});

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

async function setup(
  initial: MapState,
  prepare: (map: FakeMapLibre) => void = () => {},
  payloads: Record<string, unknown> = PAYLOADS
) {
  const map = new FakeMapLibre();
  prepare(map);
  const model = new FakeModel(initial);
  const root = { dataset: {} as Record<string, string> };
  const reporter = new StatusReporter({
    viewId: "view-1",
    side: "main",
    send: () => {},
    current: (id) => map.getSource(id),
  });
  const sync = new MapSync(
    map as unknown as MapLibreMap,
    model,
    root as unknown as HTMLElement,
    reporter,
    { viewId: "view-1", side: "main" }
  );
  map.emit("style.load");
  await settle();
  model.answer(payloads);
  map.loadAll();
  await settle();
  return { map, model, root, sync };
}

describe("MapSync", () => {
  it("names its view and side in each pull", async () => {
    const { model, root } = await setup(state(1, geojson("a", 1, "x")));
    expect(root.dataset.psmRevision).toBe("1");
    expect(model.pulls).toEqual([
      { type: "pull", view_id: "view-1", side: "main", digests: ["x"] },
    ]);
  });

  it("re-adds a GeoJSON source whose digest changed under the same id", async () => {
    const { map, model, root, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y"))
    );
    expect(root.dataset.psmRevision).toBe("1");
    const before = map.getSource("psm:a:1");

    // Python broke the contract: instance 1 of "a" now names other bytes.
    model.set(state(2, geojson("a", 1, "y")));
    await settle();
    map.loadAll();
    await settle();

    expect(map.getSource("psm:a:1")).not.toBe(before);
    expect(map.fake.payload("psm:a:1")).toEqual(PAYLOADS.y);
    expect(map.fake.sourceIds()).toEqual(["psm:a:1"]);
    expect(root.dataset.psmRevision).toBe("2");
    expect(sync.inspect().rejections).toEqual([]);
    sync.dispose();
  });

  it("settles without a layer whose style operation was rejected", async () => {
    const { root, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y")),
      (map) => {
        const add = map.addLayer;
        map.addLayer = (spec: any, beforeId?: string) => {
          if (spec.id.startsWith("psm:b:")) throw new Error("bad layer");
          add(spec, beforeId);
        };
      }
    );
    expect(sync.inspect().rejections.map((r) => r.layer)).toContain("b");
    expect(sync.settled()).toBe(true);
    expect(root.dataset.psmRevision).toBeUndefined();
    sync.dispose();
  });

  it("settles without a layer whose payload failed", async () => {
    const { root, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y")),
      () => {},
      { x: PAYLOADS.x } // y encodes as invalid JSON
    );
    expect(sync.inspect().payloads).toEqual(["x"]);
    expect(sync.settled()).toBe(true);
    expect(root.dataset.psmRevision).toBeUndefined();
    sync.dispose();
  });
});
