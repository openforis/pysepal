// Test-only probes for mounted pysepal-map views, built to .build/harness.js
// and injected into the page by the browser tests. It reaches a view through
// `el.psmMap` and wraps that map instance's methods; the widget bundle never
// imports it.
import type { Map as MapLibreMap } from "maplibre-gl";

type PsmElement = HTMLElement & {
  psmMap?: MapLibreMap;
  psmInspect?: () => unknown;
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

(window as unknown as { psmHarness: unknown }).psmHarness = {
  attach,
  quiet,
  pixel,
  featuresAt,
  inspect,
};
