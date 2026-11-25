import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ADAPTER_SOURCES,
  DRAW_MODES,
  ViewDraw,
  featureId,
  mirrorFeatures,
  prepareFeatures,
  type DrawEngine,
  type DrawFeature,
  type DrawReport,
  type ModeSpec,
} from "../draw";

type Listener = (...args: any[]) => void;

class Toggle {
  constructor(public on = true) {}
  isEnabled = () => this.on;
  enable = () => void (this.on = true);
  disable = () => void (this.on = false);
}

/** A map as the drawing view reads it: style events, sources and navigation. */
class FakeMap {
  sources = new Set<string>();
  dragPan = new Toggle();
  doubleClickZoom = new Toggle();
  private listeners = new Map<string, Set<Listener>>();
  getSource = (id: string) => (this.sources.has(id) ? {} : undefined);
  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }
  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }
  emit(type: string) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener({});
  }
  count() {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }
}

/**
 * Terra Draw as the view drives it. Like the real one, it fires `change` for
 * its own adds and clears, and starting adds the adapter's sources to the map.
 */
class FakeEngine implements DrawEngine {
  enabled = false;
  mode = "static";
  store: DrawFeature[] = [];
  log: string[] = [];
  options: [string, any][] = [];
  /** A reason to reject a feature with, or null to take it. */
  reject: (feature: DrawFeature) => string | null = () => null;
  private listeners = {
    finish: new Set<Listener>(),
    change: new Set<Listener>(),
  };

  constructor(readonly specs: ModeSpec[], private readonly map: FakeMap) {}

  start() {
    this.enabled = true;
    this.log.push("start");
    for (const id of ADAPTER_SOURCES) this.map.sources.add(id);
  }
  stop() {
    this.enabled = false;
    this.log.push("stop");
    this.store = [];
    for (const id of ADAPTER_SOURCES) this.map.sources.delete(id);
  }
  setMode(mode: string) {
    this.log.push(`setMode:${mode}`);
    this.mode = mode;
  }
  getMode() {
    return this.mode;
  }
  addFeatures(features: DrawFeature[]) {
    this.log.push("addFeatures");
    const results = features.map((feature) => {
      const reason = this.reject(feature);
      if (reason) return { id: feature.id, valid: false, reason };
      this.store.push(structuredClone(feature));
      return { id: feature.id, valid: true };
    });
    this.emit(
      "change",
      features.map((f) => f.id),
      "create"
    );
    // A finish here must not count as a user's.
    this.emit("finish", features[0]?.id, { mode: "polygon", action: "draw" });
    return results;
  }
  clear() {
    this.log.push("clear");
    const ids = this.store.map((f) => f.id);
    this.store = [];
    this.emit("change", ids, "delete");
  }
  getSnapshot() {
    return structuredClone(this.store);
  }
  updateModeOptions(mode: string, options: object) {
    this.options.push([mode, options]);
  }
  on(event: "finish" | "change", listener: Listener) {
    this.listeners[event].add(listener);
  }
  off(event: "finish" | "change", listener: Listener) {
    this.listeners[event].delete(listener);
  }
  emit(event: "finish" | "change", ...args: unknown[]) {
    for (const listener of [...this.listeners[event]]) listener(...args);
  }
  /** A user finished drawing or editing `feature`. */
  draw(feature: DrawFeature) {
    const at = this.store.findIndex((f) => f.id === feature.id);
    if (at === -1) this.store.push(structuredClone(feature));
    else this.store[at] = structuredClone(feature);
    this.emit("finish", feature.id, { mode: this.mode, action: "draw" });
  }
  /** A user deleted the features `ids`. */
  remove(...ids: (string | number)[]) {
    this.store = this.store.filter((f) => !ids.includes(f.id));
    this.emit("change", ids, "delete");
  }
}

class FakeModel {
  values: Record<string, unknown>;
  private listeners = new Map<string, Set<() => void>>();
  constructor(values: Record<string, unknown>) {
    this.values = values;
  }
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
  set(name: string, value: unknown) {
    this.setMany({ [name]: value });
  }
  /** Set every value first, then tell each change in order, as one comm message does. */
  setMany(values: Record<string, unknown>) {
    Object.assign(this.values, values);
    for (const name of Object.keys(values)) {
      for (const callback of [...(this.listeners.get(`change:${name}`) ?? [])])
        callback();
    }
  }
  count() {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }
}

let next = 0;
function polygon(west = 0, extra: Record<string, unknown> = {}): DrawFeature {
  next += 1;
  const ring = [
    [west, 0],
    [west + 1, 0],
    [west + 1, 1],
    [west, 1],
    [west, 0],
  ];
  return {
    type: "Feature",
    id: `00000000-0000-4000-8000-${String(next).padStart(12, "0")}`,
    geometry: { type: "Polygon", coordinates: [ring] },
    properties: { mode: "polygon", ...extra },
  };
}

function point(lng: number, lat = 0, extra: Record<string, unknown> = {}) {
  const feature = polygon(0, extra);
  return {
    ...feature,
    geometry: { type: "Point", coordinates: [lng, lat] },
    properties: { mode: "point", ...extra },
  } as DrawFeature;
}

const LABELS = {
  polygon: "Draw a polygon",
  rectangle: "Draw a rectangle",
  circle: "Draw a circle",
  linestring: "Draw a line",
  point: "Draw a point",
  select: "Select and edit shapes",
  clear: "Remove all shapes",
};
const ON = (modes = ["polygon", "point", "select"], session = 1) => ({
  session,
  modes,
  color: "#3388ff",
  labels: LABELS,
});
const OFF = { session: 1, modes: [], color: "#3388ff", labels: LABELS };
const UUID4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Another view's handle on `model`: anywidget gives each view its own. */
function proxyOf(model: FakeModel) {
  return {
    get: (name: string) => model.get(name),
    on: (name: string, callback: () => void) => model.on(name, callback),
    off: (name: string, callback: () => void) => model.off(name, callback),
  };
}

function setup(
  values: {
    drawing?: unknown;
    draw_request?: unknown;
    drawn?: unknown;
    draw_tool?: unknown;
  } = {},
  reject: FakeEngine["reject"] = () => null,
  /** The model of a view already built, which this view reaches through a proxy of its own. */
  shared?: FakeModel
) {
  const map = new FakeMap();
  const model =
    shared ??
    new FakeModel({
      drawing: OFF,
      draw_request: { seq: 0, features: [] },
      drawn: { request_seq: 0, features: [] },
      draw_tool: { seq: 0, session: 0, mode: "static" },
      ...values,
    });
  const engines: FakeEngine[] = [];
  const sent: DrawReport[] = [];
  const changes: boolean[] = [];
  const rendered: { features: DrawFeature[]; color: string }[] = [];
  const tools: [string[], Record<string, string>, string][] = [];
  let refuse = false;
  const view: ViewDraw = new ViewDraw({
    map,
    model: shared ? proxyOf(shared) : model,
    viewId: "v1",
    side: "main",
    send: (report) => {
      if (refuse) return false;
      sent.push(structuredClone(report));
      return true;
    },
    createDraw: (specs) => {
      const engine = new FakeEngine(specs, map);
      engine.reject = reject;
      engines.push(engine);
      return engine;
    },
    onInteractiveChange: () => changes.push(view.interactive()),
    onRendered: (features, color) =>
      rendered.push(structuredClone({ features, color })),
    onToolsChange: (modes, labels, active) =>
      tools.push(structuredClone([modes, labels, active])),
  });
  return {
    map,
    model,
    view,
    engines,
    sent,
    changes,
    rendered,
    tools,
    engine: () => engines[engines.length - 1],
    load: () => map.emit("style.load"),
    refuse: (value: boolean) => (refuse = value),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("starting", () => {
  it("runs no Terra Draw while no tool is offered", () => {
    const { load, model, engines } = setup();
    load();
    model.set("drawing", { ...OFF, color: "#000000" });
    expect(engines).toHaveLength(0);
  });

  it("waits for the style before it starts", () => {
    const { view, load, model, engines } = setup();
    model.set("drawing", ON());
    view.setMode("polygon");
    expect(engines).toHaveLength(0);
    load();
    expect(engines).toHaveLength(1);
    expect(engines[0].log).toEqual(["start", "setMode:polygon"]);
  });

  it("registers every drawing mode and select, whatever modes offers", () => {
    const { load, model, engine } = setup();
    load();
    model.set("drawing", ON(["point"]));
    expect(engine().specs.map((s) => s.name)).toEqual([
      ...DRAW_MODES,
      "select",
    ]);
    const select = engine().specs.find((s) => s.name === "select")!;
    const flags = (select.options as any).flags;
    for (const mode of DRAW_MODES)
      expect(flags[mode].feature.draggable).toBe(true);
    for (const mode of ["polygon", "linestring"]) {
      expect(flags[mode].feature.coordinates).toEqual({
        draggable: true,
        midpoints: true,
        deletable: true,
      });
    }
    expect(flags.rectangle.feature.coordinates).toEqual({
      resizable: "opposite",
    });
    expect(flags.circle.feature.coordinates).toEqual({
      resizable: "center-fixed",
    });
    expect(flags.point.feature.coordinates).toBeUndefined();
  });

  it("styles every mode from the colour, with fills at 0.2", () => {
    const { load, model, engine } = setup();
    load();
    model.set("drawing", { ...ON(), color: "#ff0000" });
    const styles = Object.fromEntries(
      engine().specs.map((s) => [s.name, (s.options as any).styles])
    );
    for (const mode of ["polygon", "rectangle", "circle"]) {
      expect(styles[mode]).toMatchObject({
        fillColor: "#ff0000",
        fillOpacity: 0.2,
        outlineColor: "#ff0000",
      });
    }
    expect(styles.linestring.lineStringColor).toBe("#ff0000");
    expect(styles.point.pointColor).toBe("#ff0000");
    expect(styles.select).toMatchObject({
      selectedPolygonColor: "#ff0000",
      selectedPolygonFillOpacity: 0.2,
      selectedPolygonOutlineColor: "#ff0000",
      // As wide as the right map's mirror draws it.
      selectedPolygonOutlineWidth: 2,
      selectedLineStringColor: "#ff0000",
      selectedPointColor: "#ff0000",
    });
  });
});

describe("restoring", () => {
  it("restores drawn when it is as new as the request, silently", () => {
    const saved = polygon();
    const { load, model, engine, sent, view } = setup({
      draw_request: { seq: 2, features: [polygon(5)] },
      drawn: { request_seq: 2, features: [saved] },
    });
    load();
    model.set("drawing", ON());
    expect(engine().store).toEqual([saved]);
    expect(sent).toEqual([]);
    expect(view.inspect().applied).toBe(2);
  });

  it("applies the request when drawn is older, and acknowledges it", () => {
    const seed = polygon(5);
    const { load, model, engine, sent } = setup({
      draw_request: { seq: 3, features: [seed] },
      drawn: { request_seq: 2, features: [polygon()] },
    });
    load();
    model.set("drawing", ON());
    expect(engine().store).toEqual([seed]);
    expect(sent).toEqual([
      {
        type: "draw_report",
        view_id: "v1",
        side: "main",
        request_seq: 3,
        cause: "request",
        features: [seed],
      },
    ]);
  });

  it("adds a rejected feature again under its geometry's mode, else leaves it out", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const rectangle = polygon(0, { mode: "rectangle", name: "r" });
    const broken = polygon(3, { broken: true });
    const reject = (f: DrawFeature) =>
      f.properties.mode === "rectangle"
        ? "Feature intersects itself"
        : f.properties.broken
        ? "Feature has holes"
        : null;
    const { load, model, sent, engines } = setup(
      { draw_request: { seq: 1, features: [rectangle, broken] } },
      reject
    );
    load();
    model.set("drawing", ON());
    expect(engines[0].store.map((f) => f.properties)).toEqual([
      { mode: "polygon", name: "r" },
    ]);
    expect(sent[0].features).toEqual([
      { ...rectangle, properties: { mode: "polygon", name: "r" } },
    ]);
    expect(warn).toHaveBeenCalledTimes(1);
    expect(String(warn.mock.calls[0])).toContain("Feature has holes");
  });
});

describe("preparing", () => {
  it("prepareFeatures rounds, strips reserved names and fixes ids", () => {
    const kept = polygon(0, { mode: "rectangle", selected: true, name: "r" });
    const precise: DrawFeature = {
      type: "Feature",
      id: "not-a-uuid",
      geometry: {
        type: "LineString",
        coordinates: [
          [1.123456789012, 2.0000000004],
          [3, 4],
        ],
      },
      properties: { mode: "point", midPoint: true, marker: true },
    };
    const seeds = [
      kept,
      { ...polygon(2, { mode: "point" }), id: kept.id },
      precise,
      { ...point(5), id: undefined } as unknown as DrawFeature,
    ];
    const before = structuredClone(seeds);
    const prepared = prepareFeatures(seeds, 3);
    expect(seeds).toEqual(before);
    expect(prepared.map((f) => f.id)).toEqual([
      kept.id,
      featureId(3, 1),
      featureId(3, 2),
      featureId(3, 3),
    ]);
    expect(featureId(3, 1)).toBe("00000003-0000-4000-8000-000000000001");
    expect(featureId(300, 4096)).toBe("0000012c-0000-4000-8000-000000001000");
    for (const feature of prepared) expect(String(feature.id)).toMatch(UUID4);
    expect(prepared.map((f) => f.properties)).toEqual([
      { mode: "rectangle", name: "r" },
      { mode: "polygon" },
      { mode: "linestring" },
      { mode: "point" },
    ]);
    expect(prepared[2].geometry.coordinates).toEqual([
      [1.123456789, 2],
      [3, 4],
    ]);

    // Every view gives the same ids, and a restore numbers them by drawn's request.
    const views = [1, 2].map(() =>
      setup({ draw_request: { seq: 3, features: seeds } })
    );
    for (const { load, model } of views) {
      load();
      model.set("drawing", ON());
    }
    const [one, two] = views.map(({ engine }) => engine().store);
    expect(one).toEqual(prepared);
    expect(two).toEqual(prepared);
    expect(views[0].sent[0].features).toEqual(prepared);
    const restored = setup({
      draw_request: { seq: 2, features: [] },
      drawn: { request_seq: 4, features: [{ ...polygon(), id: 7 }] },
    });
    restored.load();
    restored.model.set("drawing", ON());
    expect(restored.engine().store.map((f) => f.id)).toEqual([featureId(4, 0)]);
  });
});

describe("sessions", () => {
  it("a session change drops the old features before its request arrives", () => {
    const seed = polygon(5);
    const { load, model, engine, engines, sent, view } = setup({
      draw_request: { seq: 1, features: [seed] },
    });
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    engine().draw(polygon());
    expect(sent.map((r) => r.cause)).toEqual(["request", "user"]);
    expect(view.inspect().session).toBe(1);

    model.set("drawing", ON(undefined, 2));
    expect(view.inspect().session).toBe(2);
    expect(engines).toHaveLength(2);
    expect(engines[0].enabled).toBe(false);
    expect(engine().store).toEqual([]);
    expect(view.inspect().committed).toEqual([]);
    // A new session starts with no tool.
    expect(engine().getMode()).toBe("static");
    expect(view.interactive()).toBe(false);
    expect(sent).toHaveLength(2);

    const next = polygon(8);
    model.set("draw_request", { seq: 2, features: [next] });
    expect(engine().store).toEqual([next]);
    expect(sent.at(-1)).toMatchObject({
      cause: "request",
      request_seq: 2,
      features: [next],
    });
  });

  it("a new session applies its request once, whichever trait changes first", () => {
    for (const order of [
      ["draw_request", "drawing"],
      ["drawing", "draw_request"],
    ]) {
      const { view, load, model, engine, engines, sent } = setup();
      load();
      model.set("drawing", ON());
      view.setMode("polygon");
      engine().draw(polygon());
      const seed = polygon(3);
      const values: Record<string, unknown> = {
        drawing: ON(undefined, 2),
        draw_request: { seq: 1, features: [seed] },
      };
      model.setMany(Object.fromEntries(order.map((k) => [k, values[k]])));
      expect(engines).toHaveLength(2);
      expect(engines[0].log).not.toContain("clear");
      expect(engine().store).toEqual([seed]);
      expect(sent.map((r) => [r.cause, r.request_seq])).toEqual([
        ["user", 0],
        ["request", 1],
      ]);
    }
  });

  it("modes going empty drops the committed features", () => {
    const { load, model, engine, engines, sent, view } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    engine().draw(polygon());
    model.set("drawing", OFF);
    expect(engines[0].enabled).toBe(false);
    expect(view.inspect().committed).toEqual([]);
    model.set("drawing", ON());
    view.setMode("polygon");
    expect(engines).toHaveLength(2);
    expect(engine().store).toEqual([]);
    expect(sent).toHaveLength(1);
  });

  it("acknowledges no end, whichever trait changes first", () => {
    for (const order of [
      ["draw_request", "drawing"],
      ["drawing", "draw_request"],
    ]) {
      const { view, load, model, engines, sent } = setup();
      load();
      model.set("drawing", ON());
      view.setMode("polygon");
      const values: Record<string, unknown> = {
        drawing: OFF,
        draw_request: { seq: 1, features: [] },
      };
      model.setMany(Object.fromEntries(order.map((k) => [k, values[k]])));
      expect(engines[0].enabled).toBe(false);
      expect(engines[0].log).not.toContain("clear");
      expect(sent).toEqual([]);
    }
  });

  it("a style replacement restores the view's own features", () => {
    const { view, load, model, engine, engines, map, sent } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const mine = polygon();
    engine().draw(mine);
    // Another view's edit, accepted meanwhile.
    model.set("drawn", { request_seq: 0, features: [polygon(9)] });
    map.emit("styledataloading");
    map.emit("style.load");
    expect(engines).toHaveLength(2);
    expect(engine().store).toEqual([mine]);
    expect(engine().log).toEqual(["start", "addFeatures", "setMode:polygon"]);
    expect(sent).toHaveLength(1);
  });
});

describe("requests", () => {
  it("a newer request clears, adds and acknowledges", () => {
    const { load, model, engine, sent } = setup();
    load();
    model.set("drawing", ON());
    engine().draw(polygon());
    engine().log.length = 0;
    const seed = polygon(2);
    model.set("draw_request", { seq: 1, features: [seed] });
    expect(engine().log).toEqual(["clear", "addFeatures"]);
    expect(engine().store).toEqual([seed]);
    expect(sent.at(-1)).toMatchObject({
      cause: "request",
      request_seq: 1,
      features: [seed],
    });
    model.set("draw_request", { seq: 1, features: [] });
    expect(engine().store).toEqual([seed]);
    expect(sent).toHaveLength(2);
  });

  it("sends nothing for the events of a restore, an apply or a clear", () => {
    const { load, model, engine, sent } = setup({
      drawn: { request_seq: 0, features: [polygon()] },
    });
    load();
    model.set("drawing", ON());
    expect(sent).toEqual([]);
    model.set("draw_request", { seq: 1, features: [] });
    expect(sent.map((r) => r.cause)).toEqual(["request"]);
    expect(engine().store).toEqual([]);
  });

  it("acknowledges an empty request even when nothing changes", () => {
    const { load, model, sent } = setup();
    load();
    model.set("drawing", ON());
    model.set("draw_request", { seq: 1, features: [] });
    expect(sent).toEqual([
      expect.objectContaining({ cause: "request", features: [] }),
    ]);
  });
});

describe("user reports", () => {
  it("finish sends one user report on the applied sequence", () => {
    const { view, load, model, engine, sent } = setup({
      draw_request: { seq: 4, features: [] },
      drawn: { request_seq: 4, features: [] },
    });
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const drawn = polygon();
    engine().draw(drawn);
    expect(sent).toEqual([
      expect.objectContaining({
        cause: "user",
        request_seq: 4,
        features: [drawn],
      }),
    ]);
    engine().emit("finish", drawn.id, {
      mode: "select",
      action: "dragFeature",
    });
    expect(sent).toHaveLength(1);
  });

  it("a user's deletion of a committed feature reports, a helper's does not", () => {
    const kept = polygon();
    const gone = polygon(3);
    const { view, load, model, engine, sent } = setup({
      drawn: { request_seq: 0, features: [kept, gone] },
    });
    load();
    model.set("drawing", ON());
    view.setMode("select");
    engine().store.push(point(0, 0, { selectionPoint: true }));
    engine().remove(engine().store[2].id);
    expect(sent).toEqual([]);
    engine().remove(gone.id);
    expect(sent).toEqual([
      expect.objectContaining({ cause: "user", features: [kept] }),
    ]);
  });

  it("selecting and deselecting reports nothing", () => {
    const shown = polygon();
    const { view, load, model, engine, sent } = setup({
      drawn: { request_seq: 0, features: [shown] },
    });
    load();
    model.set("drawing", ON());
    view.setMode("select");
    engine().store[0].properties.selected = true;
    engine().store.push(point(0, 0, { selectionPoint: true, index: 0 }));
    engine().store.push(point(0.5, 0, { midPoint: true }));
    engine().emit("finish", shown.id, {
      mode: "select",
      action: "dragFeature",
    });
    engine().store[0].properties.selected = false;
    engine().remove(engine().store[1].id, engine().store[2].id);
    expect(sent).toEqual([]);
  });

  it("leaves helpers and provisional geometry out of snapshots", () => {
    const committed = polygon(0, {
      name: "a",
      selected: true,
      edited: false,
      coordinatePointIds: ["x"],
    });
    const { view, load, model, engine, sent } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const helpers = [
      polygon(5, { currentlyDrawing: true, committedCoordinateCount: 2 }),
      point(1, 1, { closingPoint: true }),
      point(1, 1, { snappingPoint: true }),
      point(1, 1, { selectionPoint: true, selectionPointFeatureId: "x" }),
      point(1, 1, { midPoint: true }),
      point(1, 1, { coordinatePoint: true }),
      point(1, 1, { edited: true }),
    ];
    engine().store.push(...helpers);
    engine().draw(committed);
    expect(sent).toHaveLength(1);
    expect(sent[0].features).toEqual([
      { ...committed, properties: { mode: "polygon", name: "a" } },
    ]);
    expect(Object.keys(sent[0].features[0])).toEqual([
      "type",
      "id",
      "geometry",
      "properties",
    ]);
  });

  it("clearAll reports an empty user drawing, even when already empty", () => {
    const { load, model, view, engine, sent, rendered } = setup({
      draw_request: { seq: 2, features: [polygon()] },
    });
    view.clearAll();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    view.clearAll();
    expect(engine().store).toEqual([]);
    expect(view.inspect().committed).toEqual([]);
    expect(rendered.at(-1)!.features).toEqual([]);
    view.clearAll();
    expect(sent.map((r) => [r.cause, r.request_seq, r.features])).toEqual([
      ["request", 2, [expect.objectContaining({ type: "Feature" })]],
      ["user", 2, []],
      ["user", 2, []],
    ]);
    expect(engine().getMode()).toBe("polygon");
    model.set("drawing", OFF);
    view.clearAll();
    expect(sent).toHaveLength(3);
  });

  it("sends a report the comm refused again on reconnect", () => {
    const { load, model, engine, sent, view, refuse } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    refuse(true);
    const drawn = polygon();
    engine().draw(drawn);
    refuse(false);
    expect(sent).toEqual([]);
    view.reconnect();
    view.reconnect();
    expect(sent).toEqual([
      expect.objectContaining({ cause: "user", features: [drawn] }),
    ]);
  });
});

describe("longitudes", () => {
  it("moves a feature by whole turns into [-180, 180] and rounds it again", () => {
    const { view, load, model, engine, sent } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("point");
    engine().draw(point(190.1, 10));
    engine().draw(point(360.1, 10));
    const shifted = polygon(370);
    engine().draw(shifted);
    const coordinates = sent
      .at(-1)!
      .features.map((f) => f.geometry.coordinates);
    expect(coordinates[0]).toEqual([-169.9, 10]);
    expect(coordinates[1]).toEqual([0.1, 10]);
    expect((coordinates[2] as number[][][])[0][0]).toEqual([10, 0]);
    // What Terra Draw holds stays where the user drew it.
    expect(engine().store[0].geometry.coordinates).toEqual([190.1, 10]);
  });

  it("leaves out a feature that crosses the antimeridian, with a warning", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const { view, load, model, engine, sent } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const across = polygon(179.5);
    engine().draw(polygon());
    engine().draw(across);
    expect(sent.at(-1)!.features).toHaveLength(1);
    expect(warn).toHaveBeenCalled();
    expect(String(warn.mock.calls[0])).toContain("antimeridian");
  });
});

describe("modes", () => {
  it("calls setMode only when the mode changes", () => {
    const { view, load, model, engine } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    model.set("drawing", { ...ON(), color: "#000000" });
    view.setMode("polygon");
    model.set("drawing", ON());
    view.setMode("select");
    expect(engine().log.filter((e) => e.startsWith("setMode"))).toEqual([
      "setMode:polygon",
      "setMode:select",
    ]);
  });

  it("updates every mode's styles on a colour change and never restarts", () => {
    const { view, load, model, engine, engines } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    model.set("drawing", { ...ON(), color: "#00ff00" });
    expect(engines).toHaveLength(1);
    expect(engine().log).toEqual(["start", "setMode:polygon"]);
    expect(engine().options.map(([mode]) => mode)).toEqual([
      ...DRAW_MODES,
      "select",
    ]);
    for (const [, options] of engine().options) {
      expect(JSON.stringify(options.styles)).toContain("#00ff00");
    }
  });

  it("is interactive while a tool is active", () => {
    const { load, model, view, changes } = setup();
    expect(view.interactive()).toBe(false);
    load();
    model.set("drawing", ON());
    expect(view.interactive()).toBe(false);
    view.setMode("polygon");
    expect(view.interactive()).toBe(true);
    view.setMode("select");
    view.setMode("static");
    expect(view.interactive()).toBe(false);
    view.setMode("point");
    model.set("drawing", OFF);
    expect(view.interactive()).toBe(false);
    view.setMode("point");
    expect(view.interactive()).toBe(false);
    // Told on each turn, to close popups or to put the cursor rule back.
    expect(changes).toEqual([true, false, true, false]);
  });

  it("stops in static first, then puts navigation back as it was", () => {
    const { view, load, model, engine, map } = setup();
    map.doubleClickZoom.disable();
    load();
    model.set("drawing", ON());
    view.setMode("select");
    // Terra Draw holds both while a vertex is dragged.
    map.dragPan.disable();
    map.doubleClickZoom.enable();
    model.set("drawing", OFF);
    expect(engine().log.slice(-2)).toEqual(["setMode:static", "stop"]);
    expect(map.dragPan.isEnabled()).toBe(true);
    expect(map.doubleClickZoom.isEnabled()).toBe(false);
  });
});

describe("the active tool", () => {
  const TOOL = (seq: number, mode: string, session = 1) => ({
    seq,
    session,
    mode,
  });
  const setModes = (engine: FakeEngine) =>
    engine.log.filter((e) => e.startsWith("setMode"));

  it("setMode switches Terra Draw and tells the tools", () => {
    const { load, model, view, engine, tools } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    expect(engine().getMode()).toBe("polygon");
    // Modes the session does not offer are ignored.
    view.setMode("circle");
    view.setMode("hexagon");
    expect(engine().getMode()).toBe("polygon");
    view.setMode("static");
    expect(engine().getMode()).toBe("static");
    const labels = { ...LABELS, clear: "Tout effacer" };
    model.set("drawing", { ...ON(), labels });
    view.setMode("point");
    model.set("drawing", OFF);
    const modes = ON().modes;
    expect(tools).toEqual([
      [modes, LABELS, "static"],
      [modes, LABELS, "polygon"],
      [modes, LABELS, "static"],
      [modes, labels, "static"],
      [modes, labels, "point"],
      [[], LABELS, "static"],
    ]);
    expect(view.tools()).toEqual({
      modes: [],
      labels: LABELS,
      active: "static",
    });
  });

  it("a tool request of the running session applies once", () => {
    const { load, model, view, engine } = setup();
    load();
    model.set("drawing", ON());
    model.set("draw_tool", TOOL(1, "polygon"));
    expect(engine().getMode()).toBe("polygon");
    view.setMode("static");
    model.set("draw_tool", TOOL(1, "polygon"));
    expect(engine().getMode()).toBe("static");
    model.set("draw_tool", TOOL(2, "point"));
    expect(engine().getMode()).toBe("point");
    expect(view.tools().active).toBe("point");
    // Not offered: ignored, though its seq counts as applied.
    model.set("draw_tool", TOOL(3, "circle"));
    model.set("draw_tool", TOOL(3, "select"));
    expect(engine().getMode()).toBe("point");
    model.set("draw_tool", TOOL(4, "static"));
    expect(setModes(engine())).toEqual([
      "setMode:polygon",
      "setMode:static",
      "setMode:point",
      "setMode:static",
    ]);
  });

  it("a tool request of another session never applies", () => {
    const { load, model, view, engine, engines } = setup({
      drawing: ON(undefined, 2),
      draw_tool: TOOL(4, "polygon", 1),
    });
    load();
    expect(engines).toHaveLength(1);
    model.set("draw_tool", TOOL(5, "point", 1));
    model.set("draw_tool", TOOL(6, "point", 3));
    expect(setModes(engine())).toEqual([]);
    // A new session starts with no tool, even after one was picked.
    view.setMode("polygon");
    model.set("drawing", ON(undefined, 4));
    expect(engines).toHaveLength(2);
    expect(setModes(engine())).toEqual([]);
    expect(view.tools().active).toBe("static");
  });

  it("the current session's tool request applies at the first start", () => {
    const { load, engines } = setup({
      drawing: ON(),
      draw_tool: TOOL(1, "polygon"),
    });
    load();
    expect(engines[0].log).toEqual(["start", "setMode:polygon"]);
    for (const order of [
      ["draw_tool", "drawing"],
      ["drawing", "draw_tool"],
    ]) {
      const { load, model, engine, engines } = setup();
      load();
      model.set("drawing", ON());
      const values: Record<string, unknown> = {
        drawing: ON(undefined, 2),
        draw_tool: TOOL(1, "point", 2),
      };
      model.setMany(Object.fromEntries(order.map((k) => [k, values[k]])));
      expect(engines).toHaveLength(2);
      expect(engine().log).toEqual(["start", "setMode:point"]);
    }
  });

  it("a style replacement keeps the active tool", () => {
    const { load, model, view, engine, engines, map } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const get = vi.spyOn(model, "get");
    map.emit("styledataloading");
    expect(view.tools().active).toBe("polygon");
    map.emit("style.load");
    expect(engines).toHaveLength(2);
    expect(engine().getMode()).toBe("polygon");
    expect(get.mock.calls.map(([name]) => name)).not.toContain("draw_tool");
  });

  it("a remount does not apply a consumed tool request", () => {
    const first = setup({ drawing: ON(), draw_tool: TOOL(1, "polygon") });
    first.load();
    expect(first.engine().getMode()).toBe("polygon");
    first.view.dispose();
    const second = setup({}, undefined, first.model);
    second.load();
    expect(second.engine().log).toEqual(["start"]);
    expect(second.view.tools().active).toBe("static");
    // A newer request still reaches it.
    first.model.set("draw_tool", TOOL(2, "point"));
    expect(second.engine().getMode()).toBe("point");
  });

  it("two running views both apply a tool request", () => {
    const one = setup({ drawing: ON() });
    const two = setup({}, undefined, one.model);
    one.load();
    two.load();
    two.view.setMode("point");
    one.model.set("draw_tool", TOOL(1, "polygon"));
    expect(one.engine().getMode()).toBe("polygon");
    expect(two.engine().getMode()).toBe("polygon");
    // A view shown after both starts with no tool.
    const three = setup({}, undefined, one.model);
    three.load();
    expect(three.engine().getMode()).toBe("static");
  });
});

describe("style replacement", () => {
  it("stops before a full replacement and starts again with its features, silently", () => {
    const { view, load, model, engine, engines, map, sent } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("select");
    const mine = polygon();
    engine().draw(mine);
    map.dragPan.disable();
    map.emit("styledataloading");
    expect(engines[0].log.slice(-2)).toEqual(["setMode:static", "stop"]);
    expect(map.dragPan.isEnabled()).toBe(true);
    map.emit("style.load");
    expect(engines).toHaveLength(2);
    expect(engine().store).toEqual([mine]);
    expect(engine().getMode()).toBe("select");
    expect(sent).toHaveLength(1);
  });

  it("starts again once a diff removed the adapter's sources", () => {
    for (const event of ["style.load", "styledata"]) {
      const { view, load, model, engines, map, engine } = setup();
      load();
      model.set("drawing", ON());
      view.setMode("polygon");
      const mine = polygon();
      engine().draw(mine);
      map.emit(event);
      expect(engines).toHaveLength(1);
      for (const id of ADAPTER_SOURCES) map.sources.delete(id);
      map.emit(event);
      expect(engines).toHaveLength(2);
      expect(engines[0].enabled).toBe(false);
      expect(engine().store).toEqual([mine]);
      expect(engine().getMode()).toBe("polygon");
    }
  });

  it("applies a request that came during the replacement", () => {
    const { load, model, engine, map, sent } = setup();
    load();
    model.set("drawing", ON());
    map.emit("styledataloading");
    const seed = polygon(1);
    model.set("draw_request", { seq: 1, features: [seed] });
    map.emit("style.load");
    expect(engine().store).toEqual([seed]);
    expect(sent.map((r) => r.cause)).toEqual(["request"]);
  });
});

describe("what Terra Draw renders", () => {
  const plain = (feature: DrawFeature, psmRole: string) => ({
    type: "Feature",
    id: feature.id,
    geometry: feature.geometry,
    properties: { psmRole },
  });

  it("keeps shapes being drawn and handles, as plain features tagged by role", () => {
    const drawing = polygon(5, {
      currentlyDrawing: true,
      committedCoordinateCount: 2,
    });
    const edited = polygon(7, { edited: true });
    const drawn = point(3, 4, { name: "p" });
    const closing = point(1, 1, { closingPoint: true });
    const vertex = point(0, 0, {
      selectionPoint: true,
      selectionPointFeatureId: drawing.id,
      index: 0,
    });
    const midpoint = point(0.5, 0, { midPoint: true });
    expect(
      mirrorFeatures([drawing, edited, drawn, closing, vertex, midpoint])
    ).toEqual([
      plain(drawing, "shape"),
      plain(edited, "shape"),
      plain(drawn, "shape"),
      plain(closing, "vertex"),
      plain(vertex, "vertex"),
      plain(midpoint, "midpoint"),
    ]);
  });

  it("is told after a restore, on a user's change, and as Terra Draw stops", () => {
    const saved = polygon();
    const { view, load, model, engine, rendered } = setup({
      drawn: { request_seq: 0, features: [saved] },
    });
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    expect(rendered.at(-1)).toEqual({
      features: mirrorFeatures([saved]),
      color: "#3388ff",
    });
    // Terra Draw changes a polygon in progress on every pointer move.
    const drawing = polygon(4, { currentlyDrawing: true });
    engine().store.push(drawing);
    engine().emit("change", [drawing.id], "create");
    expect(rendered.at(-1)!.features).toEqual(mirrorFeatures([saved, drawing]));
    model.set("drawing", OFF);
    expect(rendered.at(-1)).toEqual({ features: [], color: "#3388ff" });
  });

  it("is told on the changes the view makes itself, and after it applied a request", () => {
    const { load, model, engine, rendered } = setup();
    load();
    model.set("drawing", ON());
    engine().draw(polygon());
    rendered.length = 0;
    const seed = polygon(2);
    model.set("draw_request", { seq: 1, features: [seed] });
    // The clear and the add each fire a change while the view is quiet.
    expect(rendered.map((r) => r.features.length)).toEqual([0, 1, 1]);
    expect(rendered.at(-1)!.features).toEqual(mirrorFeatures([seed]));
  });

  it("is told the new colour", () => {
    const { view, load, model, engine, rendered } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    const mine = polygon();
    engine().draw(mine);
    model.set("drawing", { ...ON(), color: "#00ff00" });
    expect(rendered.at(-1)).toEqual({
      features: mirrorFeatures([mine]),
      color: "#00ff00",
    });
  });
});

describe("dispose", () => {
  it("stops Terra Draw and lets go of the map and the model", () => {
    const { load, model, engine, map, view } = setup();
    load();
    model.set("drawing", ON());
    view.setMode("polygon");
    view.dispose();
    expect(engine().enabled).toBe(false);
    expect(map.count()).toBe(0);
    expect(model.count()).toBe(0);
  });
});
