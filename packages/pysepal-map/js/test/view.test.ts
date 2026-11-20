import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { REPORT_DELAY_MS, ViewCamera, type ViewReport } from "../view";

type Listener = (event: any) => void;

/**
 * A map camera as ViewCamera drives it. Like MapLibre, a zero-size container
 * leaves the camera at 400 x 300; unlike it, a jump that changes nothing
 * fires no event, so a test sees whether a request is acknowledged anyway.
 */
class FakeCameraMap {
  center = { lng: 0, lat: 0 };
  zoom = 0;
  width = 400;
  height = 300;
  jumps: any[] = [];
  private readonly listeners = new Map<string, Set<Listener>>();

  getCenter() {
    return { ...this.center };
  }

  getZoom() {
    return this.zoom;
  }

  getBounds() {
    const { lng, lat } = this.center;
    return {
      getWest: () => lng - 1,
      getSouth: () => lat - 1,
      getEast: () => lng + 1,
      getNorth: () => lat + 1,
    };
  }

  jumpTo(options: any, eventData: object = {}) {
    this.jumps.push(options);
    const before = JSON.stringify([this.center, this.zoom]);
    if (options.center) {
      const [lng, lat] = options.center;
      this.center = { lng, lat };
    }
    if (options.zoom !== undefined) this.zoom = options.zoom;
    if (JSON.stringify([this.center, this.zoom]) !== before) {
      this.fire("moveend", eventData);
    }
  }

  /** The zoom of a fit tells which width it used. */
  cameraForBounds(bounds: number[], options: { padding?: number } = {}) {
    const padding = options.padding ?? 0;
    if (2 * padding >= this.width || 2 * padding >= this.height) {
      return undefined;
    }
    const [west, south, east, north] = bounds;
    return {
      center: [(west + east) / 2, (south + north) / 2],
      zoom: Math.log2(this.width - 2 * padding),
      bearing: 0,
    };
  }

  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  count(): number {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }

  fire(type: string, data: object = {}) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) {
      listener({ type, ...data });
    }
  }

  userMove(lng: number, lat: number) {
    this.center = { lng, lat };
    this.fire("moveend", { originalEvent: new Event("mouseup") });
  }

  constructor(private readonly host: Host) {}

  /** Measure the host again, as `map.resize()` does. */
  resize(eventData: object = {}) {
    this.resizes++;
    this.width = this.host.clientWidth || 400;
    this.height = this.host.clientHeight || 300;
    this.fire("resize", eventData);
    this.fire("moveend", eventData);
  }

  resizes = 0;

  /** The host changes size; the map hears of it with `observed`. */
  grow(width: number, height: number, observed = true) {
    this.host.clientWidth = width;
    this.host.clientHeight = height;
    if (observed) this.resize();
  }
}

interface Host {
  clientWidth: number;
  clientHeight: number;
}

class FakeModel {
  private readonly listeners = new Map<string, Set<() => void>>();

  constructor(private readonly values: Record<string, unknown>) {}

  get(name: string): unknown {
    return this.values[name];
  }

  set(name: string, value: unknown) {
    this.values[name] = value;
    for (const listener of [...(this.listeners.get(`change:${name}`) ?? [])]) {
      listener();
    }
  }

  on(name: string, listener: () => void) {
    if (!this.listeners.has(name)) this.listeners.set(name, new Set());
    this.listeners.get(name)!.add(listener);
  }

  off(name: string, listener: () => void) {
    this.listeners.get(name)?.delete(listener);
  }

  count(): number {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }
}

const SAVED = {
  center: [10, 20],
  zoom: 5,
  bounds: [9, 19, 11, 21],
  request_seq: 3,
};

function setup({
  view = {} as unknown,
  request = { seq: 1, center: [0, 0], zoom: 2 } as unknown,
  width = 400,
  height = 300,
} = {}) {
  const model = new FakeModel({ view, view_request: request });
  const host: Host = { clientWidth: 0, clientHeight: 0 };
  const map = new FakeCameraMap(host);
  map.grow(width, height);
  const sent: ViewReport[] = [];
  let live = true;
  const camera = new ViewCamera({
    map,
    model,
    viewId: "view-1",
    host,
    send: (report) => {
      if (!live) return false;
      sent.push(report);
      return true;
    },
  });
  const seqs = () => sent.map((r) => r.request_seq);
  const setLive = (value: boolean) => {
    live = value;
  };
  return { model, map, host, sent, camera, seqs, setLive };
}

describe("ViewCamera", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("applies the first request on start and reports it 250 ms later", () => {
    const { camera, map, sent } = setup();
    camera.start();
    expect([map.center, map.zoom]).toEqual([{ lng: 0, lat: 0 }, 2]);
    vi.advanceTimersByTime(REPORT_DELAY_MS - 1);
    expect(sent).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(sent).toEqual([
      {
        type: "view_report",
        view_id: "view-1",
        center: [0, 0],
        zoom: 2,
        bounds: [-1, -1, 1, 1],
        request_seq: 1,
      },
    ]);
    expect(REPORT_DELAY_MS).toBe(250);
  });

  it("keeps the camera north-up and flat on every request", () => {
    const { camera, map, model } = setup();
    camera.start();
    model.set("view_request", { seq: 2, bounds: [0, 0, 10, 10], padding: 20 });
    expect(map.jumps.map((j) => [j.bearing, j.pitch])).toEqual([
      [0, 0],
      [0, 0],
    ]);
  });

  it("restores the saved camera and sequence, then applies only a newer request", () => {
    const { camera, map, model, seqs } = setup({
      view: SAVED,
      request: { seq: 3, center: [0, 0], zoom: 2 },
    });
    camera.start();
    expect([map.center, map.zoom]).toEqual([{ lng: 10, lat: 20 }, 5]);
    vi.runAllTimers();
    expect(seqs()).toEqual([]);

    // No zoom keeps the current one.
    model.set("view_request", { seq: 4, center: [1, 1], zoom: null });
    expect([map.center, map.zoom]).toEqual([{ lng: 1, lat: 1 }, 5]);
    vi.runAllTimers();
    expect(seqs()).toEqual([4]);
  });

  it("applies a newer saved request on mount and ignores a stale one", () => {
    const { camera, map, model } = setup({
      view: SAVED,
      request: { seq: 4, center: [7, 7], zoom: 1 },
    });
    camera.start();
    expect([map.center, map.zoom]).toEqual([{ lng: 7, lat: 7 }, 1]);
    const jumps = map.jumps.length;
    model.set("view_request", { seq: 4, center: [8, 8], zoom: 1 });
    model.set("view_request", { seq: 2, center: [8, 8], zoom: 1 });
    expect(map.jumps.length).toBe(jumps);
  });

  it.each([
    ["a text sequence", { ...SAVED, request_seq: "3" }],
    ["no center", { ...SAVED, center: [10] }],
    ["no zoom", { ...SAVED, zoom: null }],
  ])("starts from the request when the saved view has %s", (_, view) => {
    const { camera, map } = setup({ view });
    camera.start();
    expect([map.center, map.zoom]).toEqual([{ lng: 0, lat: 0 }, 2]);
  });

  it.each([
    ["no sequence", { center: [5, 5], zoom: 2 }],
    ["a text sequence", { seq: "2", center: [5, 5], zoom: 2 }],
    ["neither center nor bounds", { seq: 2, zoom: 2 }],
    ["short bounds", { seq: 2, bounds: [0, 0, 1], padding: 0 }],
  ])("ignores a request with %s", (_, request) => {
    const { camera, map, model } = setup();
    camera.start();
    model.set("view_request", request);
    expect([map.center, map.zoom]).toEqual([{ lng: 0, lat: 0 }, 2]);
    expect(camera.inspect().applied).toBe(1);
  });

  it("never moves for another view's report", () => {
    const { camera, map, model } = setup();
    camera.start();
    model.set("view", { ...SAVED, request_seq: 1 });
    expect([map.center, map.zoom]).toEqual([{ lng: 0, lat: 0 }, 2]);
  });

  it("coalesces moves into one trailing report at the applied request", () => {
    const { camera, map, sent } = setup();
    camera.start();
    vi.runAllTimers();
    sent.length = 0;
    map.userMove(1, 1);
    vi.advanceTimersByTime(100);
    map.userMove(2, 2);
    vi.advanceTimersByTime(REPORT_DELAY_MS - 101);
    expect(sent).toEqual([]);
    vi.advanceTimersByTime(1);
    expect(sent.map((r) => [r.center, r.request_seq])).toEqual([[[2, 2], 1]]);
  });

  it("reports no move that neither a request nor the user made", () => {
    const { camera, map, seqs } = setup();
    camera.start();
    vi.runAllTimers();
    map.fire("moveend");
    map.grow(500, 300);
    vi.runAllTimers();
    expect(seqs()).toEqual([1]);
  });

  it("acknowledges a request that does not move the camera", () => {
    const { camera, map, model, seqs } = setup();
    camera.start();
    vi.runAllTimers();
    const jumps = map.jumps.length;
    model.set("view_request", { seq: 2, center: [0, 0], zoom: 2 });
    expect(map.jumps.length).toBe(jumps + 1);
    vi.runAllTimers();
    expect(seqs()).toEqual([1, 2]);
  });

  it("drops the trailing report of an older request for a newer one", () => {
    const { camera, map, model, sent } = setup();
    camera.start();
    vi.advanceTimersByTime(100);
    map.userMove(9, 9);
    model.set("view_request", { seq: 2, center: [3, 3], zoom: 4 });
    vi.runAllTimers();
    expect(sent.map((r) => [r.request_seq, r.center])).toEqual([[2, [3, 3]]]);
  });

  it("fits only once its host has a size, and then the latest request", () => {
    const { camera, map, model, seqs } = setup({ width: 0, height: 0 });
    camera.start();
    // A center needs no size; its report waits for one.
    expect(camera.inspect()).toEqual({ applied: 1, pending: null, owed: 1 });
    vi.runAllTimers();
    expect(seqs()).toEqual([]);

    model.set("view_request", { seq: 2, bounds: [0, 0, 10, 10], padding: 20 });
    model.set("view_request", {
      seq: 3,
      bounds: [20, 20, 30, 30],
      padding: 20,
    });
    expect(camera.inspect()).toEqual({ applied: 1, pending: 3, owed: null });
    // Another view acknowledged request 3 meanwhile; this one still owes it.
    model.set("view", { ...SAVED, request_seq: 3 });
    expect([map.center, map.zoom]).toEqual([{ lng: 0, lat: 0 }, 2]);

    map.grow(800, 600);
    expect([map.center, map.zoom]).toEqual([
      { lng: 25, lat: 25 },
      Math.log2(760),
    ]);
    expect(camera.inspect()).toEqual({ applied: 3, pending: null, owed: 3 });
    vi.runAllTimers();
    expect(seqs()).toEqual([3]);
  });

  it("keeps a fit MapLibre cannot make pending until it fits", () => {
    const { camera, model, map, seqs } = setup({ width: 30, height: 30 });
    camera.start();
    vi.runAllTimers();
    model.set("view_request", { seq: 2, bounds: [0, 0, 1, 1], padding: 20 });
    expect(camera.inspect()).toMatchObject({ applied: 1, pending: 2 });
    vi.runAllTimers();
    expect(seqs()).toEqual([1]);
    map.grow(100, 100);
    expect(camera.inspect()).toMatchObject({ applied: 2, pending: null });
    vi.runAllTimers();
    expect(seqs()).toEqual([1, 2]);
  });

  it("fits for the host's size before the map observed it", () => {
    const { camera, model, map, seqs } = setup();
    camera.start();
    map.grow(800, 600, false);
    model.set("view_request", { seq: 2, bounds: [0, 0, 10, 10], padding: 20 });
    expect(map.zoom).toBe(Math.log2(760));
    expect(camera.inspect()).toEqual({ applied: 2, pending: null, owed: 2 });
    vi.runAllTimers();
    expect(seqs()).toEqual([2]);
  });

  it("drops a deferred fit for a newer center", () => {
    const { camera, model, map, sent } = setup({ width: 0, height: 0 });
    camera.start();
    model.set("view_request", { seq: 2, bounds: [0, 0, 10, 10], padding: 20 });
    model.set("view_request", { seq: 3, center: [4, 4], zoom: 6 });
    expect(camera.inspect()).toEqual({ applied: 3, pending: null, owed: 3 });
    map.grow(400, 300);
    expect([map.center, map.zoom]).toEqual([{ lng: 4, lat: 4 }, 6]);
    vi.runAllTimers();
    expect(sent.map((r) => [r.request_seq, r.center])).toEqual([[3, [4, 4]]]);
  });

  it("sends a report the comm refused again on reconnect", () => {
    const { camera, map, seqs, sent, setLive } = setup();
    camera.start();
    vi.runAllTimers();
    camera.reconnect();
    vi.runAllTimers();
    expect(seqs()).toEqual([1]);

    setLive(false);
    map.userMove(5, 5);
    vi.runAllTimers();
    expect(seqs()).toEqual([1]);
    setLive(true);
    camera.reconnect();
    vi.runAllTimers();
    expect(sent.map((r) => [r.request_seq, r.center])).toEqual([
      [1, [0, 0]],
      [1, [5, 5]],
    ]);
  });

  it("stops on dispose", () => {
    const { camera, map, model, seqs } = setup();
    camera.start();
    camera.dispose();
    vi.runAllTimers();
    map.userMove(1, 1);
    model.set("view_request", { seq: 2, center: [3, 3], zoom: 4 });
    vi.runAllTimers();
    expect(seqs()).toEqual([]);
    expect(map.count()).toBe(0);
    expect(model.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
