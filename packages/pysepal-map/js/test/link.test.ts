import { describe, expect, it, vi } from "vitest";

import { ViewLink, pageRegistry, type LinkRegistry } from "../link";
import { LINK } from "../view";

type Listener = (event: any) => void;

const MOVE = ["movestart", "move", "moveend"];

/** A map that fires movestart, move and moveend on every jump, like MapLibre. */
class FakeMap {
  center = { lng: 0, lat: 0 };
  zoom = 2;
  jumps: { options: any; eventData: any }[] = [];
  private readonly listeners = new Map<string, Set<Listener>>();

  getCenter() {
    return { ...this.center };
  }

  getZoom() {
    return this.zoom;
  }

  jumpTo(options: any, eventData: any = {}) {
    this.jumps.push({ options, eventData });
    const [lng, lat] = options.center;
    this.center = { lng, lat };
    this.zoom = options.zoom;
    for (const type of MOVE) this.fire(type, eventData);
  }

  on(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  off(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  count() {
    return [...this.listeners.values()].reduce((n, s) => n + s.size, 0);
  }

  /** A user drags the map through `steps`, each `[lng, lat]` or `[lng, lat, zoom]`. */
  drag(...steps: number[][]) {
    const originalEvent = new Event("mousemove");
    this.fire("movestart", { originalEvent });
    for (const [lng, lat, zoom = this.zoom] of steps) {
      this.center = { lng, lat };
      this.zoom = zoom;
      this.fire("move", { originalEvent });
    }
    this.fire("moveend", { originalEvent: new Event("mouseup") });
  }

  userMove(lng: number, lat: number, zoom = this.zoom) {
    this.drag([lng, lat, zoom]);
  }

  /** A resize: the camera stays, and nothing marks the move. */
  resize() {
    for (const type of MOVE) this.fire(type);
  }

  fire(type: string, data: object = {}) {
    for (const listener of [...(this.listeners.get(type) ?? [])])
      listener({ type, ...data });
  }
}

class FakeModel {
  private readonly listeners = new Set<() => void>();
  link: unknown;

  constructor(group = "", seq = 1) {
    this.link = group ? { group, seq } : {};
  }

  get(_name: string) {
    return this.link;
  }

  set(group: string, seq = 1) {
    this.link = group ? { group, seq } : {};
    for (const listener of [...this.listeners]) listener();
  }

  on(_name: string, listener: () => void) {
    this.listeners.add(listener);
  }

  off(_name: string, listener: () => void) {
    this.listeners.delete(listener);
  }

  count() {
    return this.listeners.size;
  }
}

function view(
  registry: LinkRegistry,
  model = new FakeModel("g"),
  moved: number | null = null
) {
  const map = new FakeMap();
  const link = new ViewLink({ map, model, registry });
  link.start(moved);
  return { map, model, link };
}

const camera = (map: FakeMap) => [map.center.lng, map.center.lat, map.zoom];

/** The link mark of each jump a map got. */
const marks = (map: FakeMap) => map.jumps.map((j) => j.eventData[LINK]);

describe("ViewLink", () => {
  it("jumps the other map within the move of the one a user moves", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    const originalEvent = new Event("mousemove");
    a.map.fire("movestart", { originalEvent });
    a.map.center = { lng: 10, lat: 20 };
    a.map.zoom = 5;
    a.map.fire("move", { originalEvent });
    expect(camera(b.map)).toEqual([10, 20, 5]);
    expect(b.map.jumps.at(-1)?.eventData).toEqual({ [LINK]: "frame" });
  });

  it("pushes frames the camera ignores, then passes the moveend on once", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    b.map.jumps.length = 0;
    a.map.drag([1, 1], [2, 2], [3, 3]);
    expect(marks(b.map)).toEqual(["frame", "frame", "frame", "user"]);
    expect(camera(b.map)).toEqual([3, 3, 2]);
  });

  it("a resize moves no peer and passes nothing on", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    b.map.jumps.length = 0;
    a.map.resize();
    expect(b.map.jumps).toEqual([]);
  });

  it("a resize after following a peer passes nothing on", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    a.map.userMove(10, 20);
    expect(camera(b.map)).toEqual([10, 20, 2]);
    a.map.jumps.length = 0;
    b.map.resize();
    expect(a.map.jumps).toEqual([]);
  });

  it("passes a programmatic move on as link", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    b.map.jumps.length = 0;
    a.map.jumpTo({ center: [3, 4], zoom: 6 }, { psmRequest: 2 });
    expect(camera(b.map)).toEqual([3, 4, 6]);
    expect(marks(b.map)).toEqual(["frame", "link"]);
  });

  it("does not pass on the jumps it got", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    a.map.jumps.length = 0;
    b.map.jumps.length = 0;
    a.map.userMove(10, 20);
    expect(a.map.jumps).toEqual([]);
    expect(marks(b.map)).toEqual(["frame", "user"]);
  });

  it("moves every other map of a group of three", () => {
    const registry: LinkRegistry = new Map();
    const [a, b, c] = [view(registry), view(registry), view(registry)];
    b.map.userMove(7, 8, 9);
    expect([camera(a.map), camera(c.map)]).toEqual([
      [7, 8, 9],
      [7, 8, 9],
    ]);
  });

  it("leaves maps of other groups alone", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry, new FakeModel("other"));
    const free = view(registry, new FakeModel(""));
    a.map.userMove(10, 20);
    expect(camera(b.map)).toEqual([0, 0, 2]);
    expect(camera(free.map)).toEqual([0, 0, 2]);
  });

  it("never moves another view of the same widget", () => {
    const registry: LinkRegistry = new Map();
    const model = new FakeModel("g");
    const one = view(registry, model);
    const two = view(registry, model);
    one.map.userMove(10, 20);
    expect(camera(two.map)).toEqual([0, 0, 2]);
  });

  it("takes the camera of the group when it joins", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    a.map.userMove(10, 20, 5);
    const b = view(registry);
    expect(camera(b.map)).toEqual([10, 20, 5]);
    expect(camera(a.map)).toEqual([10, 20, 5]);
  });

  it.each([
    ["no request", null],
    ["the link's own request", 3],
  ])("takes the group's camera when it joins after %s", (_, moved) => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    a.map.userMove(10, 20, 5);
    const map = new FakeMap();
    new ViewLink({ map, model: new FakeModel("g", 3), registry }).start(moved);
    expect(camera(map)).toEqual([10, 20, 5]);
  });

  it("moves the group to a request newer than the link that moved it", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const map = new FakeMap();
    map.center = { lng: 30, lat: 40 };
    map.zoom = 8;
    new ViewLink({ map, model: new FakeModel("g", 3), registry }).start(4);
    expect(camera(a.map)).toEqual([30, 40, 8]);
    expect(camera(map)).toEqual([30, 40, 8]);
  });

  it("marks the join jump link", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    expect(marks(b.map)).toEqual(["link"]);
    a.map.jumps.length = 0;
    view(registry, new FakeModel("g", 3), 4);
    expect(marks(a.map)).toEqual(["link"]);
  });

  it("a request not newer than the link moves no peer and takes the peers' camera", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    a.map.userMove(10, 20, 5);
    const b = view(registry, new FakeModel("g", 3));
    a.map.jumps.length = 0;
    b.map.jumpTo({ center: [30, 40], zoom: 8 }, { psmRequest: 3 });
    expect(a.map.jumps).toEqual([]);
    expect(camera(a.map)).toEqual([10, 20, 5]);
    expect(camera(b.map)).toEqual([10, 20, 5]);
    expect(b.map.jumps.at(-1)?.eventData).toEqual({ [LINK]: "link" });
  });

  it("reads the link seq at the time of the move", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    // As when view_request and _link change in one message, before their events.
    b.model.link = { group: "g", seq: 4 };
    a.map.jumps.length = 0;
    b.map.jumpTo({ center: [30, 40], zoom: 8 }, { psmRequest: 4 });
    expect(a.map.jumps).toEqual([]);
    expect(camera(b.map)).toEqual([0, 0, 2]);
  });

  it.each([
    ["no group", {}],
    ["an empty group", { group: "", seq: 1 }],
    ["a text seq", { group: "g", seq: "1" }],
    ["a text", "g"],
  ])("stays alone with %s", (_, link) => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const model = new FakeModel();
    model.link = link;
    const b = view(registry, model);
    a.map.userMove(10, 20);
    expect(camera(b.map)).toEqual([0, 0, 2]);
  });

  it("follows a group change and stops when unlinked", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry, new FakeModel(""));
    b.model.set("g");
    a.map.userMove(10, 20);
    expect(camera(b.map)).toEqual([10, 20, 2]);
    b.model.set("");
    a.map.userMove(30, 40);
    expect(camera(b.map)).toEqual([10, 20, 2]);
    expect(registry.get("g")?.size).toBe(1);
  });

  it("leaves the group and drops its listeners once disposed", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    b.link.dispose();
    b.link.dispose();
    a.map.userMove(10, 20);
    expect(camera(b.map)).toEqual([0, 0, 2]);
    expect([b.map.count(), b.model.count()]).toEqual([0, 0]);
    a.link.dispose();
    expect(registry.size).toBe(0);
  });

  it("keeps moving the others when one cannot follow", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const broken = view(registry);
    const c = view(registry);
    broken.map.jumpTo = () => {
      throw new Error("removed");
    };
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    a.map.userMove(10, 20);
    expect(camera(c.map)).toEqual([10, 20, 2]);
    // The frame and the moveend passed on.
    expect(error).toHaveBeenCalledTimes(2);
    error.mockRestore();
  });

  it("shares one registry across the bundles of a page", () => {
    expect(pageRegistry()).toBe(pageRegistry());
    expect((globalThis as any)[Symbol.for("pysepal-map.links")]).toBe(
      pageRegistry()
    );
  });
});
