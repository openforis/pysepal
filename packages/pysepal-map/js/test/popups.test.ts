import { describe, expect, it } from "vitest";

import type { RenderedFeature } from "../pointer";
import {
  ViewPopups,
  type ElementLike,
  type PopupLike,
  type PopupOptions,
} from "../popups";
import type { InteractionState, MapState } from "../types";

type Listener = (event: any) => void;

class FakeElement implements ElementLike {
  className = "";
  textContent = "";
  readonly children: FakeElement[] = [];
  constructor(readonly tagName: string) {}
  append(...nodes: FakeElement[]) {
    this.children.push(...nodes);
  }
}

const doc = { createElement: (tag: string) => new FakeElement(tag) };

/** Rows of a popup table as [name, value]. */
const rows = (content: FakeElement) =>
  content.children.map((tr) => tr.children.map((td) => td.textContent));

class FakePopup implements PopupLike {
  static all: FakePopup[] = [];
  lngLat: [number, number] | null = null;
  content: FakeElement | null = null;
  open = false;
  htmlCalls = 0;
  private listeners = new Map<string, Listener>();
  constructor(readonly options: PopupOptions) {
    FakePopup.all.push(this);
  }
  setLngLat(lnglat: [number, number]) {
    this.lngLat = lnglat;
    return this;
  }
  setDOMContent(node: FakeElement) {
    this.content = node;
    return this;
  }
  setHTML() {
    this.htmlCalls += 1;
    return this;
  }
  addTo() {
    this.open = true;
    return this;
  }
  on(type: string, listener: Listener) {
    this.listeners.set(type, listener);
    return this;
  }
  remove() {
    if (!this.open) return this;
    this.open = false;
    this.listeners.get("close")?.({});
    return this;
  }
  get lines(): string[] {
    return this.content!.children.map((c) => c.textContent);
  }
}

class FakeMap {
  layers: string[] = [];
  features: RenderedFeature[] = [];
  queries: { layers: string[] }[] = [];
  private listeners = new Map<string, Set<Listener>>();
  getLayersOrder = () => this.layers;
  getLayer = (id: string) => (this.layers.includes(id) ? {} : undefined);
  queryRenderedFeatures = (_p: unknown, options: { layers: string[] }) => {
    this.queries.push(options);
    return this.features;
  };
  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }
  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }
  emit(type: string, event: unknown = {}) {
    for (const listener of [...(this.listeners.get(type) ?? [])])
      listener(event);
  }
  count(type: string) {
    return this.listeners.get(type)?.size ?? 0;
  }
}

class FakeModel {
  state: Partial<MapState> = { layers: [] };
  private listeners = new Set<() => void>();
  get() {
    return this.state;
  }
  on(_name: string, callback: () => void) {
    this.listeners.add(callback);
  }
  off(_name: string, callback: () => void) {
    this.listeners.delete(callback);
  }
  set(state: Partial<MapState>) {
    this.state = state;
    for (const callback of [...this.listeners]) callback();
  }
  get size() {
    return this.listeners.size;
  }
}

const sid = (id: string, instance: number) =>
  `psm:${encodeURIComponent(id)}:${instance}`;

function layer(
  id: string,
  instance: number,
  interaction: InteractionState | null,
  visible = true
) {
  return { id, instance, visible, kind: "geojson", interaction } as any;
}

function feature(
  id: string,
  instance: number,
  properties: Record<string, unknown>
): RenderedFeature {
  return { id: 0, source: sid(id, instance), properties };
}

function setup() {
  FakePopup.all = [];
  const map = new FakeMap();
  const model = new FakeModel();
  const frames: (() => void)[] = [];
  let isDrawing = false;
  const popups = new ViewPopups({
    map,
    model,
    drawing: () => isDrawing,
    createPopup: (options) => new FakePopup(options),
    doc,
    requestFrame: (callback) => frames.push(callback),
  });
  const declare = (...layers: ReturnType<typeof layer>[]) => {
    map.layers = layers.map((l) => `${sid(l.id, l.instance)}:circle`);
    model.set({ layers });
  };
  const click = (lng = 1, lat = 2) =>
    map.emit("click", { point: [3, 4], lngLat: { lng, lat } });
  const flush = () => frames.splice(0).forEach((f) => f());
  const move = (lng = 1, lat = 2) => {
    map.emit("mousemove", { point: [3, 4], lngLat: { lng, lat } });
    flush();
  };
  return {
    map,
    model,
    popups,
    declare,
    click,
    move,
    frames,
    flush,
    setDrawing: (v: boolean) => (isDrawing = v),
    popup: () =>
      FakePopup.all.filter((p) => p.options.className === "psm-popup"),
    tooltip: () =>
      FakePopup.all.filter((p) => p.options.className === "psm-tooltip"),
  };
}

type Ctx = ReturnType<typeof setup>;

const POPUP = (...fields: string[]): InteractionState => ({
  popup: fields,
  tooltip: null,
});
const TOOLTIP = (...fields: string[]): InteractionState => ({
  popup: null,
  tooltip: fields,
});

describe("click popup", () => {
  it("opens one popup at the click with a row per named property", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP("name", "missing", "count")));
    map.features = [feature("a", 1, { count: 3, name: "x", extra: true })];
    click(10, 20);
    const [opened] = popup();
    expect(opened.open).toBe(true);
    expect(opened.lngLat).toEqual([10, 20]);
    expect(opened.options).toEqual({
      className: "psm-popup",
      closeButton: true,
      maxWidth: "320px",
    });
    expect(rows(opened.content!)).toEqual([
      ["name", "x"],
      ["count", "3"],
    ]);
  });

  it("shows every property in the feature's order for an empty list", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP()));
    map.features = [feature("a", 1, { b: 1, a: 2 })];
    click();
    expect(rows(popup()[0].content!)).toEqual([
      ["b", "1"],
      ["a", "2"],
    ]);
  });

  it("formats values and truncates cells", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP()));
    map.features = [
      feature("a", 1, {
        s: "text",
        n: 1.5,
        z: null,
        o: { k: [1, 2] },
        l: [1, "a"],
        long: "x".repeat(300),
        b: false,
      }),
    ];
    click();
    expect(rows(popup()[0].content!)).toEqual([
      ["s", "text"],
      ["n", "1.5"],
      ["z", ""],
      ["o", '{"k":[1,2]}'],
      ["l", '[1,"a"]'],
      ["long", "x".repeat(200)],
      ["b", "false"],
    ]);
  });

  it("inserts text, never HTML", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP("name")));
    map.features = [feature("a", 1, { name: "<img src=x onerror=alert(1)>" })];
    click();
    expect(rows(popup()[0].content!)).toEqual([
      ["name", "<img src=x onerror=alert(1)>"],
    ]);
    expect(popup()[0].htmlCalls).toBe(0);
  });

  it("opens nothing without a row, or without a hit", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP("name")));
    map.features = [feature("a", 1, { other: 1 })];
    click();
    map.features = [];
    click();
    expect(popup()).toEqual([]);
  });

  it("replaces the popup with a new one", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 1, POPUP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    click();
    map.features = [feature("a", 1, { name: "y" })];
    click();
    expect(popup().map((p) => p.open)).toEqual([false, true]);
  });

  it("takes the top feature among layers with a popup, and queries only those", () => {
    const { map, declare, click, popup } = setup();
    declare(
      layer("plain", 1, TOOLTIP("n")),
      layer("a", 1, POPUP("name")),
      layer("b", 1, POPUP("name"))
    );
    map.features = [
      feature("b", 1, { name: "top" }),
      feature("a", 1, { name: "under" }),
    ];
    click();
    expect(map.queries[0].layers.sort()).toEqual(
      [`${sid("a", 1)}:circle`, `${sid("b", 1)}:circle`].sort()
    );
    expect(rows(popup()[0].content!)).toEqual([["name", "top"]]);
  });

  it("ignores a feature of an instance that is no longer declared", () => {
    const { map, declare, click, popup } = setup();
    declare(layer("a", 2, POPUP("name")));
    map.features = [feature("a", 1, { name: "old" })];
    click();
    expect(popup()).toEqual([]);
  });

  it("does nothing while drawing is interactive", () => {
    const { map, declare, click, popup, setDrawing } = setup();
    declare(layer("a", 1, POPUP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    setDrawing(true);
    click();
    expect(popup()).toEqual([]);
    expect(map.queries).toEqual([]);
  });

  it("forgets a popup the user closed", () => {
    const { map, declare, click, model, popup } = setup();
    declare(layer("a", 1, POPUP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    click();
    popup()[0].remove();
    model.set({ layers: [] });
    expect(popup()[0].open).toBe(false);
  });
});

describe("a popup closes with its layer", () => {
  function open() {
    const ctx = setup();
    ctx.declare(layer("a", 1, POPUP("name")));
    ctx.map.features = [feature("a", 1, { name: "x" })];
    ctx.click();
    expect(ctx.popup()[0].open).toBe(true);
    return ctx;
  }

  it("when the layer is hidden", () => {
    const { declare, popup } = open();
    declare(layer("a", 1, POPUP("name"), false));
    expect(popup()[0].open).toBe(false);
  });

  it("when the layer is removed", () => {
    const { model, popup } = open();
    model.set({ layers: [] });
    expect(popup()[0].open).toBe(false);
  });

  it("when a new instance replaces it under the same id", () => {
    const { declare, popup } = open();
    declare(layer("a", 2, POPUP("name")));
    expect(popup()[0].open).toBe(false);
  });

  it("when the layer loses its popup", () => {
    const { declare, popup } = open();
    declare(layer("a", 1, TOOLTIP("name")));
    expect(popup()[0].open).toBe(false);
  });

  it("but not when its popup fields only change", () => {
    const { declare, popup } = open();
    declare(layer("a", 1, POPUP("other")));
    expect(popup()[0].open).toBe(true);
  });
});

describe("tooltip", () => {
  it("shows a single named property as its value alone", () => {
    const { map, declare, move, tooltip } = setup();
    declare(layer("a", 1, TOOLTIP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    move(5, 6);
    const [shown] = tooltip();
    expect(shown.open).toBe(true);
    expect(shown.lngLat).toEqual([5, 6]);
    expect(shown.options).toEqual({
      className: "psm-tooltip",
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      focusAfterOpen: false,
    });
    expect(shown.content!.textContent).toBe("x");
  });

  it("shows one name: value line each otherwise", () => {
    const { map, declare, move, tooltip } = setup();
    declare(layer("a", 1, TOOLTIP("a", "missing", "b")));
    map.features = [feature("a", 1, { b: 2, a: "x" })];
    move();
    expect(tooltip()[0].lines).toEqual(["a: x", "b: 2"]);
  });

  it("shows every property for an empty list", () => {
    const { map, declare, move, tooltip } = setup();
    declare(layer("a", 1, TOOLTIP()));
    map.features = [feature("a", 1, { b: 2, a: "x" })];
    move();
    expect(tooltip()[0].lines).toEqual(["b: 2", "a: x"]);
  });

  it("updates once per animation frame, with the latest pointer", () => {
    const { map, declare, frames, flush, tooltip } = setup();
    declare(layer("a", 1, TOOLTIP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    for (const lng of [1, 2, 3]) {
      map.emit("mousemove", { point: [0, 0], lngLat: { lng, lat: 0 } });
    }
    expect(frames).toHaveLength(1);
    expect(map.queries).toEqual([]);
    flush();
    expect(map.queries).toHaveLength(1);
    expect(tooltip()[0].lngLat).toEqual([3, 0]);
  });

  it("hides when nothing is hit, and on mouseout", () => {
    const { map, declare, move, tooltip } = setup();
    declare(layer("a", 1, TOOLTIP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    move();
    map.features = [];
    move();
    expect(tooltip().map((t) => t.open)).toEqual([false]);
    map.features = [feature("a", 1, { name: "x" })];
    move();
    map.emit("mouseout");
    expect(tooltip().map((t) => t.open)).toEqual([false, false]);
  });

  it("does not show after the pointer left", () => {
    const { map, declare, tooltip, flush } = setup();
    declare(layer("a", 1, TOOLTIP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    map.emit("mousemove", { point: [0, 0], lngLat: { lng: 0, lat: 0 } });
    map.emit("mouseout");
    flush();
    expect(tooltip()).toEqual([]);
  });

  it("closes when its layer is hidden, removed, replaced or loses it", () => {
    const changes: ((c: Ctx) => void)[] = [
      (c) => c.declare(layer("a", 1, TOOLTIP("name"), false)),
      (c) => c.model.set({ layers: [] }),
      (c) => c.declare(layer("a", 2, TOOLTIP("name"))),
      (c) => c.declare(layer("a", 1, POPUP("name"))),
    ];
    for (const change of changes) {
      const ctx = setup();
      ctx.declare(layer("a", 1, TOOLTIP("name")));
      ctx.map.features = [feature("a", 1, { name: "x" })];
      ctx.move();
      expect(ctx.tooltip()[0].open).toBe(true);
      change(ctx);
      expect(ctx.tooltip()[0].open).toBe(false);
    }
  });

  it("is off while drawing is interactive", () => {
    const { map, declare, move, tooltip, setDrawing } = setup();
    declare(layer("a", 1, TOOLTIP("name")));
    map.features = [feature("a", 1, { name: "x" })];
    move();
    setDrawing(true);
    move();
    expect(tooltip()[0].open).toBe(false);
    expect(tooltip()).toHaveLength(1);
  });

  it("queries only layers with a tooltip", () => {
    const { map, declare, move } = setup();
    declare(layer("a", 1, TOOLTIP("name")), layer("b", 1, POPUP("name")));
    move();
    expect(map.queries[0].layers).toEqual([`${sid("a", 1)}:circle`]);
  });
});

describe("clickable", () => {
  it("is true for a layer with a popup or a tooltip", () => {
    const { declare, popups } = setup();
    declare(
      layer("p", 1, POPUP()),
      layer("t", 1, TOOLTIP()),
      layer("n", 1, null),
      layer("off", 1, { popup: null, tooltip: null })
    );
    expect(
      ["p", "t", "n", "off", "none"].map((id) => popups.clickable(id))
    ).toEqual([true, true, false, false, false]);
  });
});

describe("dispose", () => {
  it("closes both, and stops listening", () => {
    const { map, model, declare, click, move, popups, popup, tooltip } =
      setup();
    declare(layer("a", 1, { popup: ["name"], tooltip: ["name"] }));
    map.features = [feature("a", 1, { name: "x" })];
    click();
    move();
    popups.dispose();
    expect(popup()[0].open).toBe(false);
    expect(tooltip()[0].open).toBe(false);
    expect(model.size).toBe(0);
    for (const type of ["click", "mousemove", "mouseout"]) {
      expect(map.count(type)).toBe(0);
    }
  });
});
