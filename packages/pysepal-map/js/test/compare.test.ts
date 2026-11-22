import type { Map as MapLibreMap } from "maplibre-gl";
import { afterEach, describe, expect, it } from "vitest";

import { CompareView, RevisionMark } from "../compare";
import { MapSync } from "../maplive";
import { StatusReporter } from "../status";
import type { MapState } from "../types";
import {
  FakeMapLibre,
  FakeModel,
  PAYLOADS,
  geojson,
  settle,
  state,
} from "./fake-maplibre";

class FakeElement {
  readonly dataset: Record<string, string> = {};
  className = "";
  removed = false;

  remove() {
    this.removed = true;
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
  return { model, root, main, sync, compare, maps, right, messages, settled };
}

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
});
