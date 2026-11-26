import { describe, expect, it, vi } from "vitest";

import { ViewLink, pageRegistry, type LinkRegistry } from "../link";
import { LINK, PLACE } from "../view";

type Listener = (event: any) => void;

const MOVE = ["movestart", "move", "moveend"];

/**
 * A map that fires movestart, move and moveend on every jump, like MapLibre.
 * As in MapLibre 6.19, a jump moves the camera at once, but a jump made by a
 * listener of this map's jump fires its events after the event being fired.
 */
class FakeMap {
  center = { lng: 0, lat: 0 };
  zoom = 2;
  jumps: { options: any; eventData: any }[] = [];
  private readonly listeners = new Map<string, Set<Listener>>();
  private readonly pending: [string, object][] = [];
  private delivering = false;

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
    for (const type of MOVE) this.pending.push([type, eventData]);
    if (this.delivering) return;
    this.delivering = true;
    try {
      while (this.pending.length) this.fire(...this.pending.shift()!);
    } catch (error) {
      this.pending.length = 0;
      throw error;
    } finally {
      this.delivering = false;
    }
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

let widgets = 0;

/** A widget's model, which all its views share. */
class FakeModel {
  private readonly listeners = new Set<() => void>();
  readonly member = `widget-${++widgets}`;
  link: unknown;

  constructor(group = "", seq = 1) {
    this.write(group, seq);
  }

  get(_name: string) {
    return this.link;
  }

  /** Write `_link` as Python does, before its change event. */
  write(group: string, seq = 1) {
    this.link = group ? { group, seq, member: this.member } : {};
  }

  set(group: string, seq = 1) {
    this.write(group, seq);
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

/** What anywidget 0.11 gives each view: an object of its own over the model. */
function proxy(model: FakeModel) {
  return {
    get: (name: "_link") => model.get(name),
    on: (name: "change:_link", listener: () => void) =>
      model.on(name, listener),
    off: (name: "change:_link", listener: () => void) =>
      model.off(name, listener),
  };
}

function view(
  registry: LinkRegistry,
  model = new FakeModel("g"),
  moved: number | null = null
) {
  const map = new FakeMap();
  const link = new ViewLink({ map, model: proxy(model), registry });
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

  it("a map keeping its place as its insets change moves no peer", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    b.map.jumps.length = 0;
    a.map.jumpTo({ center: [3, 4], zoom: 2 }, { [PLACE]: true });
    expect(b.map.jumps).toEqual([]);
    // The next move passes on the camera from there.
    a.map.userMove(5, 6);
    expect(camera(b.map)).toEqual([5, 6, 2]);
    expect(marks(b.map)).toEqual(["frame", "user"]);
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
    a.map.jumpTo({ center: [3, 4], zoom: 6 }, { mapframeRequest: 2 });
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

  it("never moves another view of the same widget, and both follow the others", () => {
    const registry: LinkRegistry = new Map();
    const model = new FakeModel("g");
    const one = view(registry, model);
    const two = view(registry, model);
    const other = view(registry);
    one.map.userMove(10, 20);
    expect(camera(two.map)).toEqual([0, 0, 2]);
    expect(camera(other.map)).toEqual([10, 20, 2]);
    other.map.userMove(30, 40);
    expect([camera(one.map), camera(two.map)]).toEqual([
      [30, 40, 2],
      [30, 40, 2],
    ]);
  });

  it("a view of a widget alone in its group takes no camera from another view of it", () => {
    const registry: LinkRegistry = new Map();
    const model = new FakeModel("g");
    const one = view(registry, model);
    one.map.userMove(10, 20);
    const two = view(registry, model);
    expect(camera(two.map)).toEqual([0, 0, 2]);
    expect(two.map.jumps).toEqual([]);
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
    const model = proxy(new FakeModel("g", 3));
    new ViewLink({ map, model, registry }).start(moved);
    expect(camera(map)).toEqual([10, 20, 5]);
  });

  it("moves the group to a request newer than the link that moved it", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const map = new FakeMap();
    map.center = { lng: 30, lat: 40 };
    map.zoom = 8;
    const model = proxy(new FakeModel("g", 3));
    new ViewLink({ map, model, registry }).start(4);
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
    b.map.jumpTo({ center: [30, 40], zoom: 8 }, { mapframeRequest: 3 });
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
    b.model.write("g", 4);
    a.map.jumps.length = 0;
    b.map.jumpTo({ center: [30, 40], zoom: 8 }, { mapframeRequest: 4 });
    expect(a.map.jumps).toEqual([]);
    expect(camera(b.map)).toEqual([0, 0, 2]);
  });

  it.each([
    ["the request", false],
    ["the link change", true],
  ])(
    "takes the request of a relink to a group with no peer shown when %s comes first",
    (_, linkFirst) => {
      const registry: LinkRegistry = new Map();
      const a = view(registry);
      const b = view(registry);
      a.map.jumps.length = 0;
      // view_request and _link change in one message, their events in either order.
      if (linkFirst) b.model.set("h", 3);
      else b.model.write("h", 3);
      b.map.jumpTo({ center: [30, 40], zoom: 8 }, { mapframeRequest: 3 });
      if (!linkFirst) b.model.set("h", 3);
      expect(a.map.jumps).toEqual([]);
      expect(camera(b.map)).toEqual([30, 40, 8]);
      expect(registry.get("h")?.size).toBe(1);
    }
  );

  it.each([
    ["no group", {}],
    ["an empty group", { group: "", seq: 1 }],
    ["a text seq", { group: "g", seq: "1", member: "m" }],
    ["no member", { group: "g", seq: 1 }],
    ["an empty member", { group: "g", seq: 1, member: "" }],
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
    expect((globalThis as any)[Symbol.for("mapframe.links")]).toBe(
      pageRegistry()
    );
  });
});
