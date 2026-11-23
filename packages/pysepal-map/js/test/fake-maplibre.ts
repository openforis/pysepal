import type { ViewModel } from "../maplive";
import type { GeoJSONLayerState, MapState } from "../types";
import { FakeMap } from "./fake-map";

type Listener = (...args: any[]) => void;

export class Emitter {
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

  listening(type: string): number {
    return this.listeners.get(type)?.size ?? 0;
  }
}

/**
 * The MapLibre map MapSync drives, over a FakeMap. Each added source gets a
 * new object, as in MapLibre, and its worker load completes only when the
 * test says so.
 */
export class FakeMapLibre extends Emitter {
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
    this.objects.set(id, {
      serialize: () => this.fake.source(id),
      setData: (data: unknown) => this.fake.setData(id, data),
    });
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

export class FakeModel extends Emitter implements ViewModel {
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

export const points = (...xy: number[][]) => ({
  type: "FeatureCollection",
  features: xy.map((coordinates) => ({
    type: "Feature",
    properties: {},
    geometry: { type: "Point", coordinates },
  })),
});

export const PAYLOADS = { x: points([-20, 0]), y: points([20, 0]) };

export function geojson(
  id: string,
  instance: number,
  digest: string,
  side: GeoJSONLayerState["side"] = "both"
): GeoJSONLayerState {
  return {
    id,
    kind: "geojson",
    token: 0,
    instance,
    zone: "data",
    side,
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
      color_by: null,
      class_colors: [],
    },
  };
}

export const state = (
  revision: number,
  ...layers: GeoJSONLayerState[]
): MapState => ({
  revision,
  theme: "light",
  compare: false,
  controls: { zoom: true, fullscreen: true, scale: true, coordinates: false },
  basemap: null,
  layers,
});

export const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
