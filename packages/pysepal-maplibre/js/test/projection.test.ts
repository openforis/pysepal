import { describe, expect, it } from "vitest";

import { ViewProjection, type ProjectionName } from "../projection";

class FakeEvents {
  private readonly listeners = new Map<string, Set<() => void>>();

  on(type: string, listener: () => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  off(type: string, listener: () => void) {
    this.listeners.get(type)?.delete(listener);
  }

  emit(type: string) {
    for (const listener of [...(this.listeners.get(type) ?? [])]) listener();
  }

  count() {
    return [...this.listeners.values()].reduce((n, set) => n + set.size, 0);
  }
}

class FakeMap extends FakeEvents {
  projection: { type: ProjectionName } | undefined = undefined;
  loading = true;

  getProjection() {
    return this.projection;
  }

  setProjection(projection: { type: ProjectionName }) {
    if (this.loading) throw new Error("Style is not done loading.");
    this.projection = projection;
    this.emit("projectiontransition");
  }
}

class FakeModel extends FakeEvents {
  constructor(public projection: string) {
    super();
  }

  get(_name: "projection") {
    return this.projection;
  }

  set(projection: string) {
    this.projection = projection;
    this.emit("change:projection");
  }
}

function setup(projection = "mercator") {
  const map = new FakeMap();
  const model = new FakeModel(projection);
  const sent: unknown[] = [];
  const view = new ViewProjection({
    map,
    model,
    viewId: "v",
    send: (content) => sent.push(content) > 0,
  });
  const load = () => {
    map.loading = false;
    map.emit("style.load");
  };
  return { map, model, sent, view, load };
}

describe("ViewProjection", () => {
  it("starts in the model's projection once the style loaded", () => {
    const { map, model, sent, load } = setup("globe");
    model.set("globe");
    expect(map.projection).toBeUndefined();
    load();
    expect(map.projection).toEqual({ type: "globe" });
    expect(sent).toEqual([]);
  });

  it("follows the model and reports only a projection a user picked", () => {
    const { map, model, sent, load } = setup();
    load();
    model.set("globe");
    expect(map.projection).toEqual({ type: "globe" });
    expect(sent).toEqual([]);

    // The globe button.
    map.setProjection({ type: "mercator" });
    expect(sent).toEqual([
      { type: "projection", view_id: "v", projection: "mercator" },
    ]);
  });

  it.each(["styledataloading", "webglcontextlost"])(
    "waits from %s for the next style load",
    (event) => {
      const { map, model, sent, load } = setup();
      load();
      map.emit(event);
      map.loading = true;
      model.set("globe");
      // The style being rebuilt sets its own projection.
      map.projection = { type: "mercator" };
      map.emit("projectiontransition");
      expect(sent).toEqual([]);
      load();
      expect(map.projection).toEqual({ type: "globe" });
    }
  );

  it("stops listening on dispose", () => {
    const { map, model, view } = setup();
    view.dispose();
    expect(map.count() + model.count()).toBe(0);
  });
});
