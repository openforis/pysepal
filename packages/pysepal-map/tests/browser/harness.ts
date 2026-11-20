// Test-only probes for mounted pysepal-map views, built to .build/harness.js
// and injected into the page by the browser tests. It reaches a view through
// `el.psmMap` and wraps that map instance's methods; the widget bundle never
// imports it.
import type { Map as MapLibreMap } from "maplibre-gl";

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
    if (probe.holding) probe.held.push(message);
    else transmit(message);
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

(window as unknown as { psmHarness: unknown }).psmHarness = {
  attach,
  quiet,
  pixel,
  featuresAt,
  inspect,
  statuses,
  gate,
  cameraGate,
};
