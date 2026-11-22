import type { Map as MapLibreMap } from "maplibre-gl";
import { afterEach, describe, expect, it } from "vitest";

import { CompareView, RevisionMark, dividerX } from "../compare";
import { MapSync } from "../maplive";
import { StatusReporter } from "../status";
import type { MapState } from "../types";
import { NO_INSETS, type Insets } from "../view";
import {
  FakeMapLibre,
  FakeModel,
  PAYLOADS,
  geojson,
  settle,
  state,
} from "./fake-maplibre";

type Listener = (event: any) => void;

class FakeElement {
  readonly dataset: Record<string, string> = {};
  readonly style: Record<string, string> = {};
  readonly attributes = new Map<string, string>();
  /** The pointers it holds captured. */
  readonly captured = new Set<number>();
  className = "";
  removed = false;
  private readonly listeners = new Map<string, Set<Listener>>();

  remove() {
    this.removed = true;
  }

  setAttribute(name: string, value: string) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name: string) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  setPointerCapture(id: number) {
    this.captured.add(id);
  }

  releasePointerCapture(id: number) {
    this.captured.delete(id);
  }

  hasPointerCapture(id: number) {
    return this.captured.has(id);
  }

  /** Dispatch an event to its listeners; true if one prevented its default. */
  fire(type: string, init: Record<string, unknown> = {}): boolean {
    let prevented = false;
    const event = {
      type,
      button: 0,
      preventDefault: () => {
        prevented = true;
      },
      stopPropagation: () => {},
      ...init,
    };
    for (const listener of [...(this.listeners.get(type) ?? [])]) {
      listener(event);
    }
    return prevented;
  }
}

class FakeDocument {
  readonly created: FakeElement[] = [];
  readonly defaultView = new EventTarget();

  createElement(_tag: string) {
    const element = new FakeElement();
    this.created.push(element);
    return element;
  }
}

/** A map with a camera, a canvas and the image resolver, over FakeMapLibre. */
class FakeViewMap extends FakeMapLibre {
  center = { lng: 0, lat: 0 };
  zoom = 2;
  padding = { top: 0, bottom: 0, left: 0, right: 0 };
  /** The camera and paint calls, in order. */
  readonly calls: string[] = [];
  readonly jumps: any[] = [];
  removed = false;
  /** What was inserted right after the canvas. */
  readonly afterCanvas: FakeElement[] = [];

  constructor(readonly container?: FakeElement) {
    super();
  }

  getCenter = () => ({ ...this.center });
  getZoom = () => this.zoom;
  getPadding = () => ({ ...this.padding });
  getCanvas = () => ({
    after: (element: FakeElement) => this.afterCanvas.push(element),
  });
  jumpTo = (options: any) => {
    this.calls.push("jumpTo");
    this.jumps.push(structuredClone(options));
  };
  redraw = () => void this.calls.push("redraw");
  resize = () => void this.calls.push("resize");
  remove = () => {
    this.removed = true;
  };
  setMissingStyleImageResolver = () => {};
  hasImage = () => false;
  addImage = () => {};
}

const compareState = (revision: number, ...layers: any[]): MapState => ({
  ...state(revision, ...layers),
  compare: true,
});

const disposers: (() => void)[] = [];

afterEach(() => {
  for (const dispose of disposers.splice(0)) dispose();
});

function rightReporter(map: FakeMapLibre, side: "main" | "right") {
  return new StatusReporter({
    viewId: "view-1",
    side,
    send: () => {},
    current: (id) => map.getSource(id),
  });
}

/** A main map and its sync, as index.ts builds them, and a CompareView. */
async function setup(initial: MapState) {
  const model = new FakeModel(initial);
  const document = new FakeDocument();
  const root = {
    dataset: {} as Record<string, string>,
    ownerDocument: document,
    clientWidth: 1000,
    clientHeight: 400,
    /** What the view appended to the root, in order. */
    appended: [] as FakeElement[],
    append(...elements: FakeElement[]) {
      root.appended.push(...elements);
    },
    getBoundingClientRect: () => ({ left: 50, top: 20 }),
  };
  const element = root as unknown as HTMLElement;
  const messages: any[] = [];
  const send = (content: any) => {
    messages.push(content);
    model.send(content);
    return true;
  };
  const main = new FakeViewMap();
  const mark = new RevisionMark(element, model);
  const sync = new MapSync(
    main as unknown as MapLibreMap,
    model,
    (revision) => mark.set("main", revision),
    rightReporter(main, "main"),
    { viewId: "view-1", side: "main" }
  );
  const maps: FakeViewMap[] = [];
  const compare = new CompareView({
    root: element,
    main: main as unknown as MapLibreMap,
    model,
    viewId: "view-1",
    send,
    mark,
    lookup: (digest) => sync.payload(digest),
    createMap: (container) => {
      const map = new FakeViewMap(container as unknown as FakeElement);
      maps.push(map);
      return map as unknown as MapLibreMap;
    },
  });
  disposers.push(() => {
    compare.dispose();
    sync.dispose();
  });
  main.emit("style.load");
  await settle();
  model.answer(PAYLOADS);
  main.loadAll();
  await settle();
  const right = () => maps.at(-1)!;
  const settled = () => sync.settled() && compare.settled();
  const shown = (className: string) =>
    root.appended.find((e) => e.className === className && !e.removed);
  const handle = () => shown("psm-compare-handle")!;
  const divider = () => shown("psm-compare-divider")!;
  const clip = () => right().container!.style.clipPath;
  return {
    model,
    root,
    main,
    sync,
    compare,
    maps,
    right,
    messages,
    settled,
    handle,
    divider,
    clip,
  };
}

const INSETS: Insets = { left: 300, right: 100, top: 10, bottom: 40 };

const views = (messages: any[], side: string) =>
  messages
    .filter((m) => m.type === "view_open" || m.type === "view_close")
    .filter((m) => m.side === side)
    .map((m) => m.type);

describe("RevisionMark", () => {
  const make = (initial: MapState) => {
    const model = new FakeModel(initial);
    const root = { dataset: {} as Record<string, string> };
    const mark = new RevisionMark(root as unknown as HTMLElement, model);
    return { model, root, mark };
  };

  it("shows no mark in compare until the right map marked too", () => {
    const { root, mark } = make(compareState(3));
    mark.set("main", 3);
    expect(root.dataset.psmRevision).toBeUndefined();
    mark.set("right", 3);
    expect(root.dataset.psmRevision).toBe("3");
    mark.set("right", null);
    expect(root.dataset.psmRevision).toBeUndefined();
  });

  it("keeps the main mark as the right sync is disposed", async () => {
    const { model, root, mark } = make(state(4, geojson("a", 1, "x")));
    const map = new FakeMapLibre();
    const right = new MapSync(
      map as unknown as MapLibreMap,
      model,
      (revision) => mark.set("right", revision),
      rightReporter(map, "right"),
      { viewId: "view-1", side: "right" }
    );
    map.emit("style.load");
    await settle();
    mark.set("main", 4);
    expect(root.dataset.psmRevision).toBe("4");
    right.dispose();
    expect(root.dataset.psmRevision).toBe("4");
  });

  it("marks on the main sync alone outside compare", () => {
    const { root, mark } = make(state(5));
    mark.set("main", 5);
    expect(root.dataset.psmRevision).toBe("5");
    mark.set("main", null);
    expect(root.dataset.psmRevision).toBeUndefined();
  });

  it("shows no mark for a revision that is not the latest", () => {
    const { model, root, mark } = make(state(5));
    mark.set("main", 5);
    model.set(state(6));
    mark.set("right", null);
    expect(root.dataset.psmRevision).toBeUndefined();
  });
});

describe("dividerX", () => {
  it("places the fraction across the area inside the insets", () => {
    expect(dividerX(1000, NO_INSETS, 0.5)).toBe(500);
    expect(dividerX(1000, NO_INSETS, 0.25)).toBe(250);
    expect(dividerX(1000, INSETS, 0.5)).toBe(600);
    expect(dividerX(1000, INSETS, 0)).toBe(300);
    expect(dividerX(1000, INSETS, 1)).toBe(900);
  });

  it("clamps the fraction to the ends", () => {
    expect(dividerX(1000, INSETS, -0.5)).toBe(300);
    expect(dividerX(1000, INSETS, 1.5)).toBe(900);
  });
});

describe("CompareView", () => {
  it("builds one right map and its sync as compare turns on", async () => {
    const { model, root, main, maps, right, messages } = await setup(
      state(1, geojson("b", 1, "x"))
    );
    expect(maps).toHaveLength(0);
    expect((root as any).psmCompare).toBeUndefined();

    model.set(compareState(2, geojson("b", 1, "x")));
    expect(maps).toHaveLength(1);
    const container = right().container!;
    expect(container.className).toBe("psm-compare-right");
    expect(main.afterCanvas).toEqual([container]);
    expect((root as any).psmCompare.map).toBe(right());
    expect((root as any).psmCompare.sync).toBeInstanceOf(MapSync);
    expect((root as any).psmCompare.status).toBeInstanceOf(StatusReporter);
    expect(views(messages, "right")).toEqual(["view_open"]);

    const compare = (root as any).psmCompare;
    model.set(compareState(3, geojson("b", 1, "x")));
    expect(maps).toHaveLength(1);
    expect((root as any).psmCompare).toBe(compare);
  });

  it("builds nothing on a second sync while compare stays on", async () => {
    const { model, compare, maps } = await setup(compareState(1));
    expect(maps).toHaveLength(1);
    compare.sync();
    compare.sync();
    model.set(compareState(2));
    expect(maps).toHaveLength(1);
  });

  it("disposes the right side as compare turns off", async () => {
    const { model, root, main, right, messages, compare } = await setup(
      compareState(1, geojson("b", 1, "x"))
    );
    const listening = model.listening("change:state");
    const map = right();
    expect(main.listening("move")).toBe(1);

    model.set(state(2, geojson("b", 1, "x")));
    expect(views(messages, "right")).toEqual(["view_open", "view_close"]);
    expect(messages.at(-1)).toEqual({
      type: "view_close",
      view_id: "view-1",
      side: "right",
    });
    expect(map.removed).toBe(true);
    expect(map.container!.removed).toBe(true);
    expect((root as any).psmCompare).toBeUndefined();
    expect(main.listening("move")).toBe(0);
    // The right sync no longer listens; the main sync and the view still do.
    expect(model.listening("change:state")).toBe(listening - 1);
    expect(compare.inspect()).toBeNull();
    // The main map is never rebuilt.
    expect(main.removed).toBe(false);
  });

  it("jumps the right map to the main camera and redraws it on a move", async () => {
    const { main, right, model } = await setup(state(1));
    main.center = { lng: 10, lat: 5 };
    main.zoom = 4;
    main.padding = { top: 1, bottom: 2, left: 300, right: 4 };
    model.set(compareState(2));
    expect(right().jumps).toEqual([
      { center: { lng: 10, lat: 5 }, zoom: 4, padding: main.padding },
    ]);
    // No style yet, so nothing to paint.
    expect(right().calls).toEqual(["jumpTo"]);

    right().emit("style.load");
    main.center = { lng: -30, lat: 12 };
    main.zoom = 6.5;
    main.padding = { top: 0, bottom: 0, left: 0, right: 0 };
    main.emit("move");
    expect(right().jumps.at(-1)).toEqual({
      center: { lng: -30, lat: 12 },
      zoom: 6.5,
      padding: { top: 0, bottom: 0, left: 0, right: 0 },
    });
    expect(right().calls.slice(-2)).toEqual(["jumpTo", "redraw"]);
  });

  it("is settled once both sides are, and marks the root only then", async () => {
    const { model, root, right, messages, sync, compare, settled } =
      await setup(state(1, geojson("b", 1, "x")));
    expect(root.dataset.psmRevision).toBe("1");
    expect(settled()).toBe(true);

    model.set(compareState(2, geojson("b", 1, "x")));
    // The main map holds b already; the right one has not loaded yet.
    expect(sync.settled()).toBe(true);
    expect(compare.settled()).toBe(false);
    expect(settled()).toBe(false);
    expect(root.dataset.psmRevision).toBeUndefined();

    right().emit("style.load");
    await settle();
    expect(settled()).toBe(false);
    expect(root.dataset.psmRevision).toBeUndefined();
    right().loadAll();
    await settle();
    expect(settled()).toBe(true);
    expect(root.dataset.psmRevision).toBe("2");
    // The payload came from the main map's cache.
    expect(right().fake.payload("psm:b:1")).toEqual(PAYLOADS.x);
    expect(
      messages.filter((m) => m.type === "pull" && m.side === "right")
    ).toEqual([]);

    model.set(state(3, geojson("b", 1, "x")));
    expect(settled()).toBe(true);
    expect(root.dataset.psmRevision).toBe("3");
  });

  it("resizes, reconnects and disposes the right side", async () => {
    const { model, right, messages, compare } = await setup(compareState(1));
    compare.resize();
    expect(right().calls).toContain("resize");

    compare.reconnect();
    expect(views(messages, "right")).toEqual(["view_open", "view_open"]);

    const map = right();
    compare.dispose();
    expect(views(messages, "right")).toEqual([
      "view_open",
      "view_open",
      "view_close",
    ]);
    expect(map.removed).toBe(true);
    model.set(compareState(2));
    compare.sync();
    expect(right()).toBe(map);
  });

  it("clips the right map at the divider, inside the insets", async () => {
    const { root, compare, clip, divider, handle } = await setup(
      compareState(1)
    );
    expect(clip()).toBe("inset(0 0 0 500px)");
    expect(divider().style.left).toBe("500px");
    expect(handle().style.left).toBe("500px");
    expect(handle().style.top).toBe("200px");

    compare.setInsets(INSETS);
    expect(clip()).toBe("inset(0 0 0 600px)");
    expect(divider().style.left).toBe("600px");
    expect(handle().style.left).toBe("600px");
    // Halfway down the area inside the insets.
    expect(handle().style.top).toBe("185px");

    root.clientWidth = 600;
    compare.resize();
    expect(clip()).toBe("inset(0 0 0 400px)");
    expect(handle().style.left).toBe("400px");
  });

  it("uses the insets set before compare turned on", async () => {
    const { model, compare, clip } = await setup(state(1));
    compare.setInsets(INSETS);
    model.set(compareState(2));
    expect(clip()).toBe("inset(0 0 0 600px)");
  });

  it("picks the map shown at a point", async () => {
    const { model, main, right, compare } = await setup(state(1));
    expect(compare.pick({ x: 999, y: 10 })).toBe(main);

    model.set(compareState(2));
    expect(compare.pick({ x: 499, y: 10 })).toBe(main);
    expect(compare.pick({ x: 500, y: 10 })).toBe(right());
    expect(compare.pick({ x: 900, y: 10 })).toBe(right());

    compare.setInsets(INSETS);
    expect(compare.pick({ x: 599, y: 10 })).toBe(main);
    expect(compare.pick({ x: 600, y: 10 })).toBe(right());

    model.set(state(3));
    expect(compare.pick({ x: 900, y: 10 })).toBe(main);
  });

  it("puts the divider and its handle on the root, outside the canvas container", async () => {
    const { model, root, main, handle, divider } = await setup(compareState(1));
    expect(root.appended).toEqual([divider(), handle()]);
    expect(main.afterCanvas).toHaveLength(1);
    expect(Object.fromEntries(handle().attributes)).toEqual({
      role: "separator",
      "aria-orientation": "vertical",
      "aria-valuemin": "0",
      "aria-valuemax": "100",
      "aria-valuenow": "50",
      "aria-label": "Compare divider",
      tabindex: "0",
    });

    const [line, knob] = root.appended;
    model.set(state(2));
    expect(line.removed).toBe(true);
    expect(knob.removed).toBe(true);
  });

  it("moves the divider with the arrow keys, Home and End", async () => {
    const { handle, clip } = await setup(compareState(1));
    const press = (key: string) => handle().fire("keydown", { key });
    const now = () => Number(handle().getAttribute("aria-valuenow"));

    expect(press("ArrowLeft")).toBe(true);
    expect(now()).toBe(45);
    expect(clip()).toBe("inset(0 0 0 450px)");
    press("ArrowRight");
    press("ArrowRight");
    expect(now()).toBe(55);

    expect(press("Home")).toBe(true);
    expect(now()).toBe(0);
    expect(clip()).toBe("inset(0 0 0 0px)");
    press("ArrowLeft");
    expect(now()).toBe(0);
    expect(clip()).toBe("inset(0 0 0 0px)");

    expect(press("End")).toBe(true);
    expect(now()).toBe(100);
    expect(clip()).toBe("inset(0 0 0 1000px)");
    press("ArrowRight");
    expect(now()).toBe(100);

    // Other keys are left to the page.
    expect(press("a")).toBe(false);
    expect(press("ArrowUp")).toBe(false);
    expect(now()).toBe(100);
  });

  it("drags the divider with the pointer it captured", async () => {
    const { compare, handle, clip } = await setup(compareState(1));
    compare.setInsets(INSETS);
    // The root starts at 50 px; the press lands 4 px right of the divider.
    expect(
      handle().fire("pointerdown", { pointerId: 7, clientX: 50 + 600 + 4 })
    ).toBe(true);
    expect(handle().captured).toEqual(new Set([7]));

    handle().fire("pointermove", { pointerId: 7, clientX: 554 });
    expect(clip()).toBe("inset(0 0 0 500px)");
    expect(handle().getAttribute("aria-valuenow")).toBe("33");
    handle().fire("pointermove", { pointerId: 8, clientX: 900 });
    expect(clip()).toBe("inset(0 0 0 500px)");
    // Past an end, it stops there.
    handle().fire("pointermove", { pointerId: 7, clientX: 5000 });
    expect(clip()).toBe("inset(0 0 0 900px)");

    handle().fire("pointerup", { pointerId: 7 });
    handle().fire("pointermove", { pointerId: 7, clientX: 554 });
    expect(clip()).toBe("inset(0 0 0 900px)");
  });

  it("ignores a press of another button and a move after the capture is lost", async () => {
    const { handle, clip } = await setup(compareState(1));
    expect(
      handle().fire("pointerdown", { pointerId: 1, button: 2, clientX: 550 })
    ).toBe(false);
    expect(handle().captured.size).toBe(0);
    handle().fire("pointermove", { pointerId: 1, clientX: 300 });
    expect(clip()).toBe("inset(0 0 0 500px)");

    handle().fire("pointerdown", { pointerId: 2, clientX: 550 });
    handle().fire("lostpointercapture", { pointerId: 2 });
    handle().fire("pointermove", { pointerId: 2, clientX: 300 });
    expect(clip()).toBe("inset(0 0 0 500px)");
  });

  it("keeps the divider where it was as compare turns off and on", async () => {
    const { model, handle, clip } = await setup(compareState(1));
    handle().fire("keydown", { key: "ArrowLeft" });
    model.set(state(2));
    model.set(compareState(3));
    expect(handle().getAttribute("aria-valuenow")).toBe("45");
    expect(clip()).toBe("inset(0 0 0 450px)");
  });
});
