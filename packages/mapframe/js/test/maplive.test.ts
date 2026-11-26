import type { Map as MapLibreMap } from "maplibre-gl";
import { describe, expect, it } from "vitest";

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

async function setup(
  initial: MapState,
  prepare: (map: FakeMapLibre) => void = () => {},
  payloads: Record<string, unknown> = PAYLOADS,
  side: "main" | "right" = "main"
) {
  const map = new FakeMapLibre();
  prepare(map);
  const model = new FakeModel(initial);
  const marks: (number | null)[] = [];
  const reporter = new StatusReporter({
    viewId: "view-1",
    side,
    send: () => {},
    current: (id) => map.getSource(id),
  });
  const sync = new MapSync(
    map as unknown as MapLibreMap,
    model,
    (revision) => marks.push(revision),
    reporter,
    { viewId: "view-1", side }
  );
  map.emit("style.load");
  await settle();
  model.answer(payloads);
  map.loadAll();
  await settle();
  /** The revision the sync marked last, or null. */
  const marked = () => marks.at(-1) ?? null;
  return { map, model, marks, marked, sync };
}

describe("MapSync", () => {
  it("names its view and side in each pull", async () => {
    const { model, marked } = await setup(state(1, geojson("a", 1, "x")));
    expect(marked()).toBe(1);
    expect(model.pulls).toEqual([
      { type: "pull", view_id: "view-1", side: "main", digests: ["x"] },
    ]);
  });

  it("re-adds a GeoJSON source whose digest changed under the same id", async () => {
    const { map, model, marked, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y"))
    );
    expect(marked()).toBe(1);
    const before = map.getSource("mapframe:a:1");

    // Python broke the contract: instance 1 of "a" now names other bytes.
    model.set(state(2, geojson("a", 1, "y")));
    await settle();
    map.loadAll();
    await settle();

    expect(map.getSource("mapframe:a:1")).not.toBe(before);
    expect(map.fake.payload("mapframe:a:1")).toEqual(PAYLOADS.y);
    expect(map.fake.sourceIds()).toEqual(["mapframe:a:1"]);
    expect(marked()).toBe(2);
    expect(sync.inspect().rejections).toEqual([]);
    sync.dispose();
  });

  it("settles without a layer whose style operation was rejected", async () => {
    const { marked, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y")),
      (map) => {
        const add = map.addLayer;
        map.addLayer = (spec: any, beforeId?: string) => {
          if (spec.id.startsWith("mapframe:b:")) throw new Error("bad layer");
          add(spec, beforeId);
        };
      }
    );
    expect(sync.inspect().rejections.map((r) => r.layer)).toContain("b");
    expect(sync.settled()).toBe(true);
    expect(marked()).toBeNull();
    sync.dispose();
  });

  it("settles without a layer whose payload failed", async () => {
    const { marked, sync } = await setup(
      state(1, geojson("a", 1, "x"), geojson("b", 2, "y")),
      () => {},
      { x: PAYLOADS.x } // y encodes as invalid JSON
    );
    expect(sync.inspect().payloads).toEqual(["x"]);
    expect(sync.settled()).toBe(true);
    expect(marked()).toBeNull();
    sync.dispose();
  });

  it("keeps only the layers its side draws", async () => {
    const layers = [
      geojson("l", 1, "x", "left"),
      geojson("r", 2, "y", "right"),
      geojson("b", 3, "z", "both"),
    ];
    const compare = { ...state(1, ...layers), compare: true };
    const payloads = { ...PAYLOADS, z: PAYLOADS.x };
    for (const [side, kept, digests] of [
      ["main", ["l", "b"], ["x", "z"]],
      ["right", ["r", "b"], ["y", "z"]],
    ] as const) {
      const { map, model, marked, sync } = await setup(
        compare,
        () => {},
        payloads,
        side
      );
      expect(model.pulls.flatMap((pull) => pull.digests)).toEqual(digests);
      const owners = map.fake.sourceIds().map((id) => id.split(":")[1]);
      expect(owners.sort()).toEqual([...kept].sort());
      expect(marked()).toBe(1);
      expect(sync.settled()).toBe(true);
      sync.dispose();
    }
  });

  it("draws every layer on main and none on right outside compare", async () => {
    const layers = [
      geojson("l", 1, "x", "left"),
      geojson("r", 2, "y", "right"),
    ];
    const main = await setup(state(1, ...layers));
    expect(main.map.fake.sourceIds().sort()).toEqual([
      "mapframe:l:1",
      "mapframe:r:2",
    ]);
    const right = await setup(state(1, ...layers), () => {}, PAYLOADS, "right");
    expect(right.model.pulls).toEqual([]);
    expect(right.map.fake.sourceIds()).toEqual([]);
    expect(right.marked()).toBe(1);
    main.sync.dispose();
    right.sync.dispose();
  });

  it("serves the payloads it holds and looks a digest up before pulling it", async () => {
    const main = await setup(state(1, geojson("a", 1, "x")));
    expect(main.sync.payload("x")).toEqual(PAYLOADS.x);
    expect(main.sync.payload("y")).toBeUndefined();

    const map = new FakeMapLibre();
    const model = new FakeModel(state(1, geojson("a", 1, "x")));
    const reporter = new StatusReporter({
      viewId: "view-1",
      side: "main",
      send: () => {},
      current: (id) => map.getSource(id),
    });
    const sync = new MapSync(
      map as unknown as MapLibreMap,
      model,
      () => {},
      reporter,
      { viewId: "view-1", side: "main", lookup: (d) => main.sync.payload(d) }
    );
    map.emit("style.load");
    await settle();
    expect(model.pulls).toEqual([]);
    expect(map.fake.payload("mapframe:a:1")).toEqual(PAYLOADS.x);
    sync.dispose();
    main.sync.dispose();
  });

  it("marks null as it is disposed", async () => {
    const { marks, sync } = await setup(state(1, geojson("a", 1, "x")));
    expect(marks.at(-1)).toBe(1);
    sync.dispose();
    expect(marks.at(-1)).toBeNull();
    expect(sync.settled()).toBe(false);
  });
});
