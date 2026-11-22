// Test-only probes for mounted pysepal-map views, built to .build/harness.js
// and injected into the page by the browser tests. It reaches a view through
// `el.psmMap` and wraps that map instance's methods; the widget bundle never
// imports it. Terra Draw, a foreign drawing plugin, is bundled here only.
import type { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import { TerraDraw, TerraDrawPolygonMode } from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

import type { StatusMessage, StatusReporter } from "../../js/status";
import type { ViewCamera, ViewReport } from "../../js/view";

type PsmElement = HTMLElement & {
  psmMap?: MapLibreMap;
  psmInspect?: () => unknown;
  psmStatus?: StatusReporter;
  psmCamera?: ViewCamera;
};

interface Probe {
  /** Owned-id calls of the map's style mutators. */
  mutations: number;
  /** Hold the first worker result of the next GeoJSON source added. */
  holding: boolean;
  held: boolean;
  release?: () => void;
  /** Make owned paint changes fire an error event and return normally. */
  failPaint: boolean;
  forcedFailures: number;
}

const MUTATORS = [
  "addSource",
  "removeSource",
  "addLayer",
  "removeLayer",
  "moveLayer",
  "setPaintProperty",
  "setLayoutProperty",
  "setFilter",
  "setLayerZoomRange",
] as const;

const probes = new WeakMap<MapLibreMap, Probe>();

function mapOf(el: Element): MapLibreMap {
  const map = (el as PsmElement).psmMap;
  if (!map) throw new Error("the element holds no mounted map");
  return map;
}

const owned = (id: unknown): id is string =>
  typeof id === "string" && id.startsWith("psm:");

// MapLibre 6.19 GeoJSONSource: the worker's reply goes through this method,
// which fires `data` with sourceDataType "content", or `dataabort` once the
// source was removed. Holding the call holds that notification at its origin.
type WorkerResult = (...args: unknown[]) => void;

function holdFirstResult(
  probe: Probe,
  source: { _onWorkerUpdateResult: WorkerResult }
): void {
  probe.holding = false;
  const original = source._onWorkerUpdateResult;
  source._onWorkerUpdateResult = (...args) => {
    source._onWorkerUpdateResult = original;
    probe.held = true;
    probe.release = () => original.apply(source, args);
  };
}

function attach(el: Element): Probe {
  const map = mapOf(el);
  const existing = probes.get(map);
  if (existing) return existing;
  const probe: Probe = {
    mutations: 0,
    holding: false,
    held: false,
    failPaint: false,
    forcedFailures: 0,
  };
  const target = map as unknown as Record<string, (...args: any[]) => any>;
  for (const name of MUTATORS) {
    const original = target[name];
    target[name] = function (this: MapLibreMap, ...args: any[]) {
      const id = typeof args[0] === "string" ? args[0] : args[0]?.id;
      if (owned(id)) probe.mutations++;
      if (name === "setPaintProperty" && probe.failPaint && owned(id)) {
        probe.forcedFailures++;
        this.fire("error", { error: new Error(`forced failure: ${id}`) });
        return this;
      }
      const result = original.apply(this, args);
      if (
        name === "addSource" &&
        probe.holding &&
        args[1]?.type === "geojson"
      ) {
        const source = this.getSource(id) as unknown;
        holdFirstResult(
          probe,
          source as { _onWorkerUpdateResult: WorkerResult }
        );
      }
      return result;
    };
  }
  probes.set(map, probe);
  return probe;
}

/** Wait for `count` animation frames after the map went idle. */
async function quiet(el: Element, count = 5): Promise<void> {
  const map = mapOf(el);
  if (!map.loaded()) await map.once("idle");
  for (let i = 0; i < count; i++) {
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
}

/** The RGBA of one canvas pixel (CSS px from the top left) in the next frame. */
function pixel(el: Element, x: number, y: number): Promise<number[]> {
  const map = mapOf(el);
  return new Promise((resolve) => {
    map.once("render", () => {
      const context = (map as any).painter.context;
      const gl = context.gl as WebGLRenderingContext;
      context.bindFramebuffer.set(null);
      const ratio = map.getPixelRatio();
      const out = new Uint8Array(4);
      gl.readPixels(
        Math.round(x * ratio),
        gl.drawingBufferHeight - Math.round(y * ratio) - 1,
        1,
        1,
        gl.RGBA,
        gl.UNSIGNED_BYTE,
        out
      );
      resolve([...out]);
    });
    map.triggerRepaint();
  });
}

/** How many rendered features of `layers` lie within a few px of `lngLat`. */
function featuresAt(
  el: Element,
  lngLat: [number, number],
  layers: string[]
): number {
  const map = mapOf(el);
  const { x, y } = map.project(lngLat);
  const box: [[number, number], [number, number]] = [
    [x - 3, y - 3],
    [x + 3, y + 3],
  ];
  const present = layers.filter((id) => map.getLayer(id));
  if (present.length !== layers.length) return 0;
  return map.queryRenderedFeatures(box, { layers: present }).length;
}

function inspect(el: Element): unknown {
  const fn = (el as PsmElement).psmInspect;
  if (!fn) throw new Error("the element holds no mounted view");
  return fn();
}

/** The view's current status reports, as it would replay them. */
function statuses(el: Element): StatusMessage[] {
  return (inspect(el) as { statuses: StatusMessage[] }).statuses;
}

interface Gate {
  /** Hold the view's status reports instead of sending them. */
  holding: boolean;
  /** Hold only the reports this accepts; the others go through. */
  only?: (message: StatusMessage) => boolean;
  held: StatusMessage[];
  /** Send the held reports, in order, and stop holding. */
  release(): void;
}

const gates = new WeakMap<StatusReporter, Gate>();

/** Hold a view's status reports at their origin, the reporter's `transmit`. */
function gate(el: Element): Gate {
  const reporter = (el as PsmElement).psmStatus;
  if (!reporter) throw new Error("the element holds no mounted view");
  const existing = gates.get(reporter);
  if (existing) return existing;
  const transmit = reporter.transmit.bind(reporter);
  const probe: Gate = {
    holding: false,
    held: [],
    release() {
      probe.holding = false;
      for (const message of probe.held.splice(0)) transmit(message);
    },
  };
  reporter.transmit = (message) => {
    if (probe.holding && (probe.only?.(message) ?? true)) {
      probe.held.push(message);
    } else {
      transmit(message);
    }
  };
  gates.set(reporter, probe);
  return probe;
}

interface CameraGate {
  /** Hold the view's camera reports instead of sending them. */
  holding: boolean;
  held: ViewReport[];
  /** Send the held reports, newest first if asked, and stop holding. */
  release(newestFirst?: boolean): void;
}

const cameraGates = new WeakMap<ViewCamera, CameraGate>();

/** Hold a view's camera reports at their origin, the camera's `transmit`. */
function cameraGate(el: Element): CameraGate {
  const camera = (el as PsmElement).psmCamera;
  if (!camera) throw new Error("the element holds no mounted view");
  const existing = cameraGates.get(camera);
  if (existing) return existing;
  const transmit = camera.transmit.bind(camera);
  const probe: CameraGate = {
    holding: false,
    held: [],
    release(newestFirst = false) {
      probe.holding = false;
      const held = probe.held.splice(0);
      if (newestFirst) held.reverse();
      for (const report of held) transmit(report);
    },
  };
  camera.transmit = (report) => {
    if (probe.holding) probe.held.push(report);
    else transmit(report);
  };
  cameraGates.set(camera, probe);
  return probe;
}

/** The options index.ts built the view's reporter with. */
function reporterOptions(el: Element): {
  viewId: string;
  send(content: unknown): unknown;
} {
  const reporter = (el as PsmElement).psmStatus as unknown as
    | { options?: { viewId: string; send(content: unknown): unknown } }
    | undefined;
  if (!reporter?.options) throw new Error("the element holds no mounted view");
  return reporter.options;
}

/** The id the view sends its messages under. */
function viewId(el: Element): string {
  return reporterOptions(el).viewId;
}

/** Send a message over the view's comm, as any view of the model could. */
function post(el: Element, content: unknown): void {
  reporterOptions(el).send(content);
}

/**
 * What the view's map holds of the owned style: layers bottom-first, sources
 * by id as they were set (without GeoJSON data), the coordinates each
 * GeoJSON source holds in its worker, and the theme.
 */
async function ownedSnapshot(el: Element) {
  const map = mapOf(el);
  const layers = map
    .getLayersOrder()
    .filter(owned)
    .map((id) => {
      const spec = map.getLayer(id)!.serialize() as Record<string, any>;
      return {
        id,
        type: spec.type,
        source: spec.source ?? null,
        source_layer: spec["source-layer"] ?? null,
        visibility: spec.layout?.visibility ?? "visible",
        paint: spec.paint ?? {},
        min_zoom: spec.minzoom ?? 0,
        max_zoom: spec.maxzoom ?? null,
      };
    });
  // getStyle() would serialize foreign custom layers, which throws.
  const style = (map as any).style;
  const ids = Object.keys(style.tileManagers ?? style.sourceCaches ?? {});
  const sources: Record<string, unknown> = {};
  const coordinates: Record<string, unknown[]> = {};
  for (const id of ids.filter(owned)) {
    const source = map.getSource(id)!;
    const { data: _data, ...spec } = source.serialize() as Record<
      string,
      unknown
    >;
    sources[id] = spec;
    if (spec.type === "geojson") {
      const data = (await (source as GeoJSONSource).getData()) as {
        features: { geometry: { coordinates: unknown } }[];
      };
      coordinates[id] = data.features.map((f) => f.geometry.coordinates);
    }
  }
  const theme = el.classList.contains("psm-dark") ? "dark" : "light";
  return { layers, sources, coordinates, theme };
}

const drawings = new WeakMap<Element, TerraDraw>();

/** Start Terra Draw's polygon mode on the view's map, as a plugin would. */
function startDrawing(el: Element): void {
  const map = mapOf(el);
  const draw = new TerraDraw({
    adapter: new TerraDrawMapLibreGLAdapter({ map }),
    modes: [new TerraDrawPolygonMode()],
  });
  draw.start();
  draw.setMode("polygon");
  drawings.set(el, draw);
}

/** The polygons Terra Draw holds for the view. */
function drawnPolygons(el: Element) {
  const draw = drawings.get(el);
  if (!draw) throw new Error("no drawing was started on the view");
  return draw
    .getSnapshot()
    .filter((feature) => feature.geometry.type === "Polygon")
    .map(({ geometry, properties }) => ({ geometry, properties }));
}

const expansions = new WeakMap<MapLibreMap, (() => Promise<unknown>)[]>();

/** Hold the answers to `getClusterExpansionZoom` of a source until released. */
function holdExpansion(el: Element, sourceId: string): void {
  const map = mapOf(el);
  const source = map.getSource(sourceId) as unknown as {
    getClusterExpansionZoom(id: number): Promise<number>;
  };
  const original = source.getClusterExpansionZoom.bind(source);
  const releases: (() => Promise<unknown>)[] = [];
  expansions.set(map, releases);
  source.getClusterExpansionZoom = (id) =>
    new Promise((resolve, reject) => {
      releases.push(() => original(id).then(resolve, reject));
    });
}

/** Let every held expansion answer, and resolve once they did. */
async function releaseExpansion(el: Element): Promise<void> {
  const releases = expansions.get(mapOf(el)) ?? [];
  expansions.delete(mapOf(el));
  await Promise.allSettled(releases.splice(0).map((release) => release()));
  // The click's continuation runs in the microtasks after the answer.
  await new Promise((resolve) => setTimeout(resolve, 50));
}

(window as unknown as { psmHarness: unknown }).psmHarness = {
  holdExpansion,
  releaseExpansion,
  attach,
  quiet,
  pixel,
  featuresAt,
  inspect,
  statuses,
  gate,
  cameraGate,
  viewId,
  post,
  ownedSnapshot,
  startDrawing,
  drawnPolygons,
};
