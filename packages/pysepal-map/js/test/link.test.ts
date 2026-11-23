import { describe, expect, it, vi } from "vitest";

import { ViewLink, pageRegistry, type LinkRegistry } from "../link";
import { LINK } from "../view";

type Listener = (event: any) => void;

/** A map that fires `move` on every jump that changes its camera, like MapLibre. */
class FakeMap {
  center = { lng: 0, lat: 0 };
  zoom = 2;
  jumps: { options: any; eventData: any }[] = [];
  private readonly listeners = new Set<Listener>();

  getCenter() {
    return { ...this.center };
  }

  getZoom() {
    return this.zoom;
  }

  jumpTo(options: any, eventData: any = {}) {
    this.jumps.push({ options, eventData });
    const [lng, lat] = options.center;
    if (
      lng === this.center.lng &&
      lat === this.center.lat &&
      options.zoom === this.zoom
    )
      return;
    this.center = { lng, lat };
    this.zoom = options.zoom;
    this.fire(eventData);
  }

  on(_type: string, listener: Listener) {
    this.listeners.add(listener);
  }

  off(_type: string, listener: Listener) {
    this.listeners.delete(listener);
  }

  count() {
    return this.listeners.size;
  }

  /** A user gesture moves the map. */
  userMove(lng: number, lat: number, zoom = this.zoom) {
    this.center = { lng, lat };
    this.zoom = zoom;
    this.fire({ originalEvent: new Event("mousemove") });
  }

  fire(data: object = {}) {
    for (const listener of [...this.listeners])
      listener({ type: "move", ...data });
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

describe("ViewLink", () => {
  it("jumps the other map in the same call as a user move", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    a.map.userMove(10, 20, 5);
    expect(camera(b.map)).toEqual([10, 20, 5]);
    expect(b.map.jumps.at(-1)?.eventData).toEqual({ [LINK]: "user" });
  });

  it("passes a move that is not a user's as other", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    a.map.jumpTo({ center: [3, 4], zoom: 6 }, { psmRequest: 2 });
    expect(camera(b.map)).toEqual([3, 4, 6]);
    expect(b.map.jumps.at(-1)?.eventData).toEqual({ [LINK]: "other" });
  });

  it("does not pass on the jump it got", () => {
    const registry: LinkRegistry = new Map();
    const a = view(registry);
    const b = view(registry);
    a.map.jumps.length = 0;
    b.map.jumps.length = 0;
    a.map.userMove(10, 20);
    expect(a.map.jumps).toEqual([]);
    expect(b.map.jumps).toHaveLength(1);
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
    expect(error).toHaveBeenCalledOnce();
    error.mockRestore();
  });

  it("shares one registry across the bundles of a page", () => {
    expect(pageRegistry()).toBe(pageRegistry());
    expect((globalThis as any)[Symbol.for("pysepal-map.links")]).toBe(
      pageRegistry()
    );
  });
});
