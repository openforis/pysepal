import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HEARTBEAT_MS,
  StatusReporter,
  ViewPresence,
  onLiveAgain,
  type LayerRef,
} from "../status";

const V1: LayerRef = { id: "v", token: 0, instance: 1 };
const V2: LayerRef = { id: "v", token: 0, instance: 2 };

/** A reporter over a stand-in map whose sources are plain objects. */
function setup() {
  const sent: any[] = [];
  const sources = new Map<string, object>();
  const reporter = new StatusReporter({
    viewId: "view-1",
    side: "main",
    send: (message) => sent.push(message),
    current: (id) => sources.get(id),
  });
  const add = (id: string, ref: LayerRef, geojson = false) => {
    reporter.track(id, ref, geojson);
    const source = {};
    sources.set(id, source);
    reporter.bind(id, source);
    return source;
  };
  const remove = (id: string) => {
    reporter.retire(id);
    sources.delete(id);
  };
  const loaded = (sourceId: string, extra: object = {}) =>
    reporter.sourceData({ sourceId, isSourceLoaded: true, ...extra });
  const statuses = () => sent.map((m) => [m.id, m.instance, m.status]);
  return { sent, sources, reporter, add, remove, loaded, statuses };
}

const tile = (key: string, state = "errored") => ({
  state,
  tileID: { key: `overscaled-${key}`, canonical: { key } },
});

describe("StatusReporter", () => {
  it("reports loading on track and ready once the source loads", () => {
    const { sent, add, reporter, loaded } = setup();
    add("psm:v:1", V1);
    reporter.sourceData({ sourceId: "psm:v:1", isSourceLoaded: false });
    loaded("psm:v:1");
    expect(sent).toEqual([
      {
        type: "status",
        view_id: "view-1",
        side: "main",
        id: "v",
        token: 0,
        instance: 1,
        status: "loading",
        error: null,
      },
      {
        type: "status",
        view_id: "view-1",
        side: "main",
        id: "v",
        token: 0,
        instance: 1,
        status: "ready",
        error: null,
      },
    ]);
  });

  it("holds a GeoJSON source at loading until its data is applied", () => {
    const { add, loaded, reporter, statuses } = setup();
    add("psm:v:1", V1, true);
    loaded("psm:v:1");
    reporter.idle();
    expect(statuses()).toEqual([["v", 1, "loading"]]);
    reporter.sourceData({
      sourceId: "psm:v:1",
      sourceDataType: "content",
      isSourceLoaded: false,
    });
    expect(statuses()).toEqual([["v", 1, "loading"]]);
    loaded("psm:v:1");
    expect(statuses()).toEqual([
      ["v", 1, "loading"],
      ["v", 1, "ready"],
    ]);
  });

  it("drops an error from a removed source once its successor is ready", () => {
    const { sent, add, remove, loaded, reporter, sources, statuses } = setup();
    add("psm:v:1", V1);
    loaded("psm:v:1");
    remove("psm:v:1");
    add("psm:v:2", V2);
    loaded("psm:v:2");
    const before = sent.length;

    const late = { error: new Error("late"), tile: tile("1/0/0") };
    expect(reporter.sourceError({ sourceId: "psm:v:1", ...late })).toBe(false);
    // The same id on a source object it never bound, as after a style reload.
    sources.set("psm:v:2", {});
    expect(reporter.sourceError({ sourceId: "psm:v:2", ...late })).toBe(false);

    expect(sent.length).toBe(before);
    expect(statuses().filter(([, , s]) => s === "error")).toEqual([]);
    expect(reporter.inspect()).toEqual([
      expect.objectContaining({ id: "v", instance: 2, status: "ready" }),
    ]);
  });

  it("keeps a tile error through an idle event", () => {
    const { add, loaded, reporter, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    const handled = reporter.sourceError({
      sourceId: "psm:r:1",
      error: new Error("AJAXError: Internal Server Error (500)"),
      tile: tile("1/0/0"),
      isSourceLoaded: true,
    });
    expect(handled).toBe(true);
    loaded("psm:r:1", { sourceDataType: "idle" });
    reporter.idle();
    expect(statuses()).toEqual([
      ["r", 1, "loading"],
      ["r", 1, "error"],
    ]);
    expect(reporter.inspect()[0].error).toBe(
      "AJAXError: Internal Server Error (500)"
    );
  });

  it("drops the tile failures of a load in which other tiles loaded", () => {
    const { add, loaded, reporter, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    loaded("psm:r:1", { tile: tile("1/1/0", "loaded") });
    // A transient 429 that MapLibre will not retry while the tile is in view.
    reporter.sourceError({
      sourceId: "psm:r:1",
      error: new Error("AJAXError: Too Many Requests (429)"),
      tile: tile("1/0/0"),
      isSourceLoaded: true,
    });
    reporter.idle();
    expect(statuses()).toEqual([
      ["r", 1, "loading"],
      ["r", 1, "ready"],
    ]);

    // A later load at another zoom: one tile fails, after one loaded.
    loaded("psm:r:1", { tile: tile("2/1/1", "loaded") });
    reporter.sourceError({
      sourceId: "psm:r:1",
      error: new Error("boom"),
      tile: tile("2/0/1"),
    });
    reporter.idle();
    expect(statuses().at(-1)).toEqual(["r", 1, "ready"]);
    expect(statuses().filter(([, , s]) => s === "error")).toEqual([]);
  });

  it("reports a load whose tiles all failed until a tile loads", () => {
    const { add, loaded, reporter, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    loaded("psm:r:1", { tile: tile("1/1/0", "loaded") });
    reporter.idle();
    for (const key of ["2/0/0", "2/0/1"]) {
      reporter.sourceError({
        sourceId: "psm:r:1",
        error: new Error("AJAXError: Forbidden (403)"),
        tile: tile(key),
        isSourceLoaded: true,
      });
    }
    // Undecided until the map is idle.
    expect(statuses().at(-1)).toEqual(["r", 1, "loading"]);
    reporter.idle();
    expect(statuses().at(-1)).toEqual(["r", 1, "error"]);
    expect(reporter.inspect()[0].error).toBe("AJAXError: Forbidden (403)");
    reporter.idle();
    expect(statuses().at(-1)).toEqual(["r", 1, "error"]);

    loaded("psm:r:1", { tile: tile("3/0/0", "loaded") });
    expect(statuses().at(-1)).toEqual(["r", 1, "ready"]);
  });

  it("keeps a source error until the source is replaced", () => {
    const { add, remove, loaded, reporter, statuses } = setup();
    add("psm:v:1", V1, true);
    reporter.sourceError({
      sourceId: "psm:v:1",
      error: new Error("not a valid GeoJSON object"),
    });
    loaded("psm:v:1", { tile: tile("0/0/0", "loaded") });
    reporter.idle();
    expect(statuses().at(-1)).toEqual(["v", 1, "error"]);
    remove("psm:v:1");
    add("psm:v:2", V2, true);
    expect(statuses().at(-1)).toEqual(["v", 2, "loading"]);
  });

  it("reports loading again when a style reload re-adds the source", () => {
    const { add, loaded, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    loaded("psm:r:1");
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    loaded("psm:r:1");
    expect(statuses()).toEqual([
      ["r", 1, "loading"],
      ["r", 1, "ready"],
      ["r", 1, "loading"],
      ["r", 1, "ready"],
    ]);
  });

  it("sends each change once", () => {
    const { add, loaded, reporter, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    loaded("psm:r:1");
    loaded("psm:r:1");
    reporter.idle();
    expect(statuses()).toEqual([
      ["r", 1, "loading"],
      ["r", 1, "ready"],
    ]);
  });

  it("marks every bound source loaded when the map is idle", () => {
    const { add, reporter, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    reporter.idle();
    expect(statuses().at(-1)).toEqual(["r", 1, "ready"]);
  });

  it("replays its statuses when Python asks this view and side", () => {
    const { sent, add, loaded, reporter } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    add("psm:v:2", V2, true);
    loaded("psm:r:1");
    const before = sent.length;
    reporter.receive({
      type: "status_request",
      view_id: "other",
      side: "main",
    });
    reporter.receive({
      type: "status_request",
      view_id: "view-1",
      side: "left",
    });
    reporter.receive({ type: "data", digest: "x" });
    expect(sent.length).toBe(before);
    reporter.receive({
      type: "status_request",
      view_id: "view-1",
      side: "main",
    });
    expect(sent.slice(before).map((m) => [m.id, m.status])).toEqual([
      ["r", "ready"],
      ["v", "loading"],
    ]);
  });

  it("replays every status on reconnect, since reports sent meanwhile may be lost", () => {
    const { sent, add, loaded, reporter } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    add("psm:v:2", V2, true);
    loaded("psm:r:1");
    const before = sent.length;
    reporter.replay();
    expect(sent.slice(before).map((m) => [m.id, m.status])).toEqual([
      ["r", "ready"],
      ["v", "loading"],
    ]);
    reporter.dispose();
    reporter.replay();
    expect(sent.length).toBe(before + 2);
  });

  it("reports a rejected style operation with its draw revision", () => {
    const { sent, add, loaded, reporter, statuses } = setup();
    add("psm:v:1", V1);
    loaded("psm:v:1");
    reporter.styleFailed("psm:v:1", V1, 2, "forced failure");
    expect(sent.at(-1)).toEqual({
      type: "status",
      view_id: "view-1",
      side: "main",
      id: "v",
      token: 0,
      instance: 1,
      status: "error",
      error: "forced failure",
      style_revision: 2,
    });
    // The same failure on the next revision is a new report for Python.
    reporter.styleFailed("psm:v:1", V1, 3, "forced failure");
    expect(sent.at(-1).style_revision).toBe(3);
    reporter.reconciled(2);
    expect(statuses().at(-1)).toEqual(["v", 1, "error"]);
    reporter.reconciled(4);
    expect(sent.at(-1)).toMatchObject({ status: "ready", error: null });
    expect(sent.at(-1)).not.toHaveProperty("style_revision");
  });

  it("reports a style failure of a layer whose source never got added", () => {
    const { reporter, statuses } = setup();
    reporter.styleFailed("psm:v:1", V1, 1, "bad source");
    reporter.reconciled(2);
    expect(statuses()).toEqual([
      ["v", 1, "error"],
      ["v", 1, "loading"],
    ]);
  });

  it("reports a source error before a style error", () => {
    const { add, reporter, sent } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    reporter.styleFailed(
      "psm:r:1",
      { id: "r", token: 0, instance: 1 },
      2,
      "style"
    );
    reporter.sourceError({
      sourceId: "psm:r:1",
      error: new Error("tile"),
      tile: tile("1/0/0"),
    });
    reporter.idle();
    expect(sent.at(-1)).toMatchObject({ status: "error", error: "tile" });
    expect(sent.at(-1)).not.toHaveProperty("style_revision");
  });

  it("reports a payload that cannot be decoded", () => {
    const { reporter, statuses } = setup();
    reporter.payloadFailed("psm:v:1", V1, "not GeoJSON");
    reporter.payloadFailed("psm:v:1", V1, "not GeoJSON");
    expect(statuses()).toEqual([["v", 1, "error"]]);
    expect(reporter.inspect()[0].error).toBe("not GeoJSON");
  });

  it("forgets what the state no longer holds and sources a reload replaced", () => {
    const { add, loaded, reporter, sources, statuses } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    add("psm:v:1", V1);
    loaded("psm:r:1");
    loaded("psm:v:1");
    sources.delete("psm:r:1");
    reporter.sweep(new Set(["psm:r:1"]));
    expect(reporter.inspect()).toEqual([
      expect.objectContaining({ id: "r", status: "loading" }),
    ]);
    expect(statuses().at(-1)).toEqual(["r", 1, "loading"]);
    // A late event for the forgotten source changes nothing.
    expect(
      reporter.sourceError({ sourceId: "psm:v:1", error: new Error("x") })
    ).toBe(false);
  });

  it("ignores sources it does not track", () => {
    const { reporter, sent } = setup();
    expect(
      reporter.sourceError({ sourceId: "psm:basemap", error: new Error("x") })
    ).toBe(false);
    reporter.sourceData({ sourceId: "foreign", isSourceLoaded: true });
    reporter.sourceData({ isSourceLoaded: true });
    expect(sent).toEqual([]);
  });

  it("sends nothing after dispose", () => {
    const { add, loaded, reporter, sent } = setup();
    add("psm:r:1", { id: "r", token: 0, instance: 1 });
    reporter.dispose();
    loaded("psm:r:1");
    reporter.receive({
      type: "status_request",
      view_id: "view-1",
      side: "main",
    });
    expect(sent.length).toBe(1);
  });
});

describe("ViewPresence", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function presence() {
    const sent: any[] = [];
    const page = new EventTarget();
    const view = new ViewPresence({
      viewId: "view-1",
      side: "main",
      send: (message) => sent.push(message),
      page,
    });
    const types = () => sent.map((m) => m.type);
    return { sent, page, view, types };
  }

  it("opens on start and repeats the open every 20 s", () => {
    const { sent, view, types } = presence();
    view.start();
    expect(sent).toEqual([
      { type: "view_open", view_id: "view-1", side: "main" },
    ]);
    vi.advanceTimersByTime(HEARTBEAT_MS - 1);
    expect(types()).toEqual(["view_open"]);
    vi.advanceTimersByTime(1);
    expect(types()).toEqual(["view_open", "view_open"]);
    expect(HEARTBEAT_MS).toBe(20_000);
  });

  it("closes on pagehide and opens at once on pageshow", () => {
    const { page, view, types } = presence();
    view.start();
    page.dispatchEvent(new Event("pagehide"));
    vi.advanceTimersByTime(3 * HEARTBEAT_MS);
    expect(types()).toEqual(["view_open", "view_close"]);
    page.dispatchEvent(new Event("pageshow"));
    expect(types()).toEqual(["view_open", "view_close", "view_open"]);
    vi.advanceTimersByTime(HEARTBEAT_MS);
    expect(types().length).toBe(4);
  });

  it("opens at once on reconnect", () => {
    const { view, types } = presence();
    view.start();
    view.reopen();
    expect(types()).toEqual(["view_open", "view_open"]);
  });

  it("closes on dispose and stops its heartbeat and listeners", () => {
    const { page, view, types } = presence();
    view.start();
    view.dispose();
    vi.advanceTimersByTime(3 * HEARTBEAT_MS);
    page.dispatchEvent(new Event("pageshow"));
    view.reopen();
    expect(types()).toEqual(["view_open", "view_close"]);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("onLiveAgain", () => {
  /**
   * A model whose `comm_live_update` listeners run as anywidget runs them:
   * with the widget view as `this`, whose model holds `comm_live`.
   */
  function host() {
    const listeners = new Set<(this: unknown) => void>();
    const model = {
      on: (_: string, listener: (this: unknown) => void) =>
        void listeners.add(listener),
      off: (_: string, listener: (this: unknown) => void) =>
        void listeners.delete(listener),
    };
    const update = (context: unknown) => {
      for (const listener of [...listeners]) listener.call(context);
    };
    const live = (comm_live: boolean) => update({ model: { comm_live } });
    return { model, listeners, update, live };
  }

  it("calls back on the edge back to live only", () => {
    const { model, live } = host();
    const back = vi.fn();
    onLiveAgain(model, back);
    live(true);
    expect(back).not.toHaveBeenCalled();
    live(false);
    live(false);
    expect(back).not.toHaveBeenCalled();
    live(true);
    expect(back).toHaveBeenCalledTimes(1);
    live(true);
    expect(back).toHaveBeenCalledTimes(1);
    live(false);
    live(true);
    expect(back).toHaveBeenCalledTimes(2);
  });

  it("calls back on every update where it cannot tell the edge", () => {
    const { model, update } = host();
    const back = vi.fn();
    onLiveAgain(model, back);
    update(undefined);
    update({ el: {} });
    expect(back).toHaveBeenCalledTimes(2);
  });

  it("reopens the view and replays its statuses, without sending while down", () => {
    const { model, live } = host();
    const sent: any[] = [];
    let up = true;
    const send = (message: unknown) => {
      if (!up) throw new Error("comm closed");
      sent.push(message);
    };
    const presence = new ViewPresence({
      viewId: "view-1",
      side: "main",
      send,
      page: new EventTarget(),
    });
    const reporter = new StatusReporter({
      viewId: "view-1",
      side: "main",
      send,
      current: () => source,
    });
    const source = {};
    presence.start();
    reporter.track("psm:v:1", V1, false);
    reporter.bind("psm:v:1", source);
    onLiveAgain(model, () => {
      presence.reopen();
      reporter.replay();
    });
    sent.length = 0;

    up = false;
    live(false);
    up = true;
    live(true);
    expect(sent.map((m) => m.type)).toEqual(["view_open", "status"]);
    presence.dispose();
  });

  it("stops listening once unsubscribed", () => {
    const { model, listeners } = host();
    const off = onLiveAgain(model, () => {});
    expect(listeners.size).toBe(1);
    off();
    expect(listeners.size).toBe(0);
  });
});
