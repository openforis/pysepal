import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  LINK,
  REPORT_DELAY_MS,
  ViewCamera,
  type Insets,
  type ViewReport,
} from "../view";

type Listener = (event: any) => void;

const NO_INSETS: Insets = { left: 0, right: 0, top: 0, bottom: 0 };
const LEFT_300: Insets = { ...NO_INSETS, left: 300 };

/**
 * A map camera as ViewCamera drives it. Like MapLibre, a zero-size container
 * leaves the camera at 400 x 300, and the center sits in the middle of the
 * padding; unlike it, a jump or padding that changes nothing fires no event,
 * so a test sees whether a request is acknowledged anyway.
 */
class FakeCameraMap {
  center = { lng: 0, lat: 0 };
  zoom = 0;
  width = 400;
  height = 300;
  padding: Insets = { ...NO_INSETS };
  jumps: any[] = [];
  /** The options of each fit asked for. */
  fits: any[] = [];
  /** The padding and jump calls, in order. */
  calls: string[] = [];
  private readonly listeners = new Map<string, Set<Listener>>();

  getCenter() {
    return { ...this.center };
  }

  getZoom() {
    return this.zoom;
  }

  /** Two degrees span the width and the height, whatever the zoom. */
  unproject([x, y]: [number, number]) {
    const { left, right, top, bottom } = this.padding;
    const middleX = left + (this.width - left - right) / 2;
    const middleY = top + (this.height - top - bottom) / 2;
    return {
      lng: this.center.lng + ((x - middleX) * 2) / this.width,
      lat: this.center.lat - ((y - middleY) * 2) / this.height,
    };
  }

  setPadding(padding: Insets) {
    this.calls.push("setPadding");
    const before = JSON.stringify(this.padding);
    this.padding = { ...padding };
    if (JSON.stringify(this.padding) !== before) this.fire("moveend");
  }

  jumpTo(options: any, eventData: object = {}) {
    this.calls.push("jumpTo");
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

  /**
   * The zoom of a fit is the log2 of the pixels per degree its box gets of
   * the width left inside the map's padding and its own, so it tells which
   * width it used. A box with no area zooms in to the cap.
   */
  cameraForBounds(
    bounds: number[],
    options: { padding?: number; maxZoom?: number } = {}
  ) {
    this.fits.push(options);
    const padding = options.padding ?? 0;
    const { left, right, top, bottom } = this.padding;
    const width = this.width - left - right - 2 * padding;
    const height = this.height - top - bottom - 2 * padding;
    if (width <= 0 || height <= 0) return undefined;
    const [west, south, east, north] = bounds;
    // Like MapLibre, which caps at NaN for a maxZoom key holding undefined.
    const cap = "maxZoom" in options ? options.maxZoom : 24;
    return {
      center: [(west + east) / 2, (south + north) / 2],
      zoom: Math.min(
        Math.log2(width / Math.max(east - west, north - south)),
        cap as number
      ),
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
  const causes = () => sent.map((r) => [r.request_seq, r.cause]);
  const setLive = (value: boolean) => {
    live = value;
  };
  return { model, map, host, sent, camera, seqs, causes, setLive };
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
        cause: "request",
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
    expect(sent.map((r) => [r.center, r.request_seq, r.cause])).toEqual([
      [[2, 2], 1, "user"],
    ]);
  });

  it("reports every other move as a resize", () => {
    const { camera, map, causes } = setup();
    camera.start();
    vi.runAllTimers();
    map.fire("moveend");
    vi.runAllTimers();
    map.grow(500, 300);
    vi.runAllTimers();
    expect(causes()).toEqual([
      [1, "request"],
      [1, "resize"],
      [1, "resize"],
    ]);
  });

  it("reports a window with a user move as the user's", () => {
    const { camera, map, causes } = setup();
    camera.start();
    map.userMove(1, 1);
    map.fire("moveend");
    vi.runAllTimers();
    map.fire("moveend");
    map.userMove(2, 2);
    vi.runAllTimers();
    expect(causes()).toEqual([
      [1, "user"],
      [1, "user"],
    ]);
  });

  it("ignores frame link moves and reports link and user marks", () => {
    const { camera, map, sent, causes } = setup();
    camera.start();
    vi.runAllTimers();
    sent.length = 0;
    map.fire("moveend", { [LINK]: "frame" });
    vi.runAllTimers();
    expect(sent).toEqual([]);
    map.fire("moveend", { [LINK]: "link" });
    vi.runAllTimers();
    map.fire("moveend", { [LINK]: "frame" });
    map.fire("moveend", { [LINK]: "user" });
    vi.runAllTimers();
    expect(causes()).toEqual([
      [1, "link"],
      [1, "user"],
    ]);
  });

  it("ranks link between request and user", () => {
    const { camera, map, causes } = setup();
    camera.start();
    map.fire("moveend");
    map.fire("moveend", { [LINK]: "link" });
    map.fire("moveend");
    vi.runAllTimers();
    map.fire("moveend", { [LINK]: "link" });
    map.userMove(2, 2);
    map.fire("moveend", { [LINK]: "link" });
    vi.runAllTimers();
    expect(causes()).toEqual([
      [1, "link"],
      [1, "user"],
    ]);
  });

  it("returns on start the request that moved it past the saved camera", () => {
    const saved = setup({ view: SAVED, request: { seq: 3, center: [0, 0] } });
    expect(saved.camera.start()).toBeNull();
    const newer = setup({ view: SAVED, request: { seq: 4, center: [0, 0] } });
    expect(newer.camera.start()).toBe(4);
    // A fit that waits for a size has not moved it yet.
    const waiting = setup({
      request: { seq: 1, bounds: [0, 0, 1, 1] },
      width: 0,
      height: 0,
    });
    expect(waiting.camera.start()).toBeNull();
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
    expect(sent.map((r) => [r.request_seq, r.center, r.cause])).toEqual([
      [2, [3, 3], "request"],
    ]);
  });

  it("fits only once its host has a size, and then the latest request", () => {
    const { camera, map, model, causes } = setup({ width: 0, height: 0 });
    camera.start();
    // A center needs no size; its report waits for one.
    expect(camera.inspect()).toEqual({ applied: 1, pending: null, owed: 1 });
    vi.runAllTimers();
    map.grow(0, 0);
    vi.runAllTimers();
    expect(causes()).toEqual([]);

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
      Math.log2(76),
    ]);
    expect(camera.inspect()).toEqual({ applied: 3, pending: null, owed: 3 });
    vi.runAllTimers();
    expect(causes()).toEqual([[3, "request"]]);
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
    expect(map.zoom).toBe(Math.log2(76));
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
    expect(sent.map((r) => [r.request_seq, r.center, r.cause])).toEqual([
      [1, [0, 0], "request"],
      [1, [5, 5], "user"],
    ]);
  });

  it("applies insets as padding before restoring the camera", () => {
    const { camera, map } = setup({
      view: SAVED,
      request: { seq: 3, center: [0, 0], zoom: 2 },
    });
    camera.setInsets(LEFT_300);
    expect(map.calls).toEqual([]);
    camera.start();
    expect(map.calls).toEqual(["setPadding", "jumpTo"]);
    expect(map.padding).toEqual(LEFT_300);
    expect([map.center, map.zoom]).toEqual([{ lng: 10, lat: 20 }, 5]);
  });

  it("updates padding when insets change", () => {
    const { camera, map, causes } = setup();
    camera.start();
    vi.runAllTimers();
    camera.setInsets(LEFT_300);
    expect(map.padding).toEqual(LEFT_300);
    const insets = { left: 0, right: 20, top: 50, bottom: 10 };
    camera.setInsets(insets);
    expect(map.padding).toEqual(insets);
    vi.runAllTimers();
    // The usable area moved, and with it the bounds Python holds.
    expect(causes()).toEqual([
      [1, "request"],
      [1, "resize"],
    ]);
  });

  it("reports the bounds inside the insets", () => {
    const { camera, map, sent } = setup();
    camera.setInsets(LEFT_300);
    camera.start();
    vi.runAllTimers();
    const [w, h] = [400, 300];
    expect(sent.map((r) => r.bounds)).toEqual([
      [
        map.unproject([300, h / 2]).lng,
        map.unproject([350, h]).lat,
        map.unproject([w, h / 2]).lng,
        map.unproject([350, 0]).lat,
      ],
    ]);
    expect(sent[0].bounds[0]).toBeGreaterThan(map.unproject([0, h / 2]).lng);
  });

  const fit = (seq: number, more: object = {}) => ({
    seq,
    bounds: [0, 0, 10, 10],
    padding: 20,
    max_zoom: null,
    zoom_out: 0,
    ...more,
  });

  it("fit omits maxZoom when max_zoom is null", () => {
    const { camera, map, model } = setup();
    camera.start();
    model.set("view_request", fit(2));
    expect(map.fits.map(Object.keys)).toEqual([["padding"]]);
    expect(map.zoom).toBe(Math.log2(36));
  });

  it("fit caps at max_zoom", () => {
    const { camera, map, model } = setup();
    camera.start();
    model.set("view_request", fit(2, { bounds: [5, 5, 5, 5], max_zoom: 12 }));
    expect(map.fits).toEqual([{ padding: 20, maxZoom: 12 }]);
    expect([map.center, map.zoom]).toEqual([{ lng: 5, lat: 5 }, 12]);
  });

  it("fit subtracts zoom_out, down to zoom 0", () => {
    const { camera, map, model, sent } = setup();
    camera.start();
    model.set("view_request", fit(2, { zoom_out: 1.5 }));
    expect(map.zoom).toBe(Math.log2(36) - 1.5);
    vi.runAllTimers();
    expect(sent.map((r) => [r.request_seq, r.zoom])).toEqual([
      [2, Math.log2(36) - 1.5],
    ]);
    model.set("view_request", fit(3, { zoom_out: 9 }));
    expect(map.zoom).toBe(0);
  });

  it("a deferred fit runs when insets shrink", () => {
    const { camera, model, map, seqs } = setup();
    camera.start();
    vi.runAllTimers();
    // The insets cover the whole width: no usable area.
    camera.setInsets({ ...NO_INSETS, left: 400 });
    model.set("view_request", fit(2));
    expect(camera.inspect()).toMatchObject({ applied: 1, pending: 2 });
    vi.runAllTimers();
    expect(seqs()).toEqual([1]);

    const resizes = map.resizes;
    camera.setInsets({ ...NO_INSETS, left: 100 });
    expect(camera.inspect()).toMatchObject({ applied: 2, pending: null });
    expect(map.zoom).toBe(Math.log2(26));
    vi.runAllTimers();
    expect(seqs()).toEqual([1, 2]);
    // Only the fit measured the host; it never changed size.
    expect(map.resizes).toBe(resizes + 1);
  });

  it("stops on dispose", () => {
    const { camera, map, model, seqs } = setup();
    camera.start();
    camera.dispose();
    vi.runAllTimers();
    map.userMove(1, 1);
    model.set("view_request", { seq: 2, center: [3, 3], zoom: 4 });
    camera.setInsets(LEFT_300);
    vi.runAllTimers();
    expect(seqs()).toEqual([]);
    expect(map.padding).toEqual(NO_INSETS);
    expect(map.count()).toBe(0);
    expect(model.count()).toBe(0);
    expect(vi.getTimerCount()).toBe(0);
  });
});
