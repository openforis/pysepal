import { describe, expect, it, vi } from "vitest";

import {
  installImages,
  parseImageId,
  parsePinId,
  sizeOf,
  type Drawing,
  type ImageMap,
  type Pixels,
} from "../images";

describe("image ids", () => {
  it("reads the colour of a pin id", () => {
    expect(parsePinId("psm-pin:%2300ff00")).toBe("#00ff00");
    expect(parsePinId("psm-pin:rgb(1%2C2%2C3)")).toBe("rgb(1,2,3)");
    expect(parsePinId("psm-pin:")).toBeNull();
    expect(parsePinId("psm-pin:%E0%A4%A")).toBeNull();
    expect(parsePinId("psm-count:%23fff:3")).toBeNull();
    expect(parsePinId("other")).toBeNull();
  });

  it("sorts an id into a drawing", () => {
    expect(parseImageId("psm-pin:%23fff")).toEqual({
      kind: "pin",
      color: "#fff",
    });
    expect(parseImageId("sprite-icon")).toBeNull();
  });

  it("generated images are pins only", () => {
    expect(parseImageId("psm-count:%23f00:5")).toBeNull();
  });
});

/** A map honouring MapLibre 6.19's contract: the resolver's image serves the request that missed. */
class FakeImageMap implements ImageMap {
  images = new Map<string, { image: Pixels; pixelRatio: number }>();
  resolver: ((id: string) => void | Promise<void>) | null = null;
  hasImage = (id: string) => this.images.has(id);
  addImage = (id: string, image: Pixels, options: { pixelRatio: number }) =>
    void this.images.set(id, { image, pixelRatio: options.pixelRatio });
  setMissingStyleImageResolver = (
    resolver: ((id: string) => void | Promise<void>) | null
  ) => void (this.resolver = resolver);

  /** What `imageManager.getImages` returns for ids the style needs. */
  async getImages(ids: string[]) {
    const out: Record<string, Pixels | undefined> = {};
    for (const id of ids) {
      if (!this.images.has(id)) await this.resolver?.(id);
      out[id] = this.images.get(id)?.image;
    }
    return out;
  }
}

const fakeDraw = (drawing: Drawing, ratio: number): Pixels => {
  const { width, height } = sizeOf(drawing);
  return {
    width: width * ratio,
    height: height * ratio,
    data: new Uint8ClampedArray(width * ratio * height * ratio * 4).fill(255),
  };
};

describe("installImages", () => {
  it("gives the first request for a missing id its pixels, once", async () => {
    const map = new FakeImageMap();
    const draw = vi.fn(fakeDraw);
    installImages(map, { draw, ratio: () => 2 });
    const first = await map.getImages(["psm-pin:%23ff0000"]);
    expect(first["psm-pin:%23ff0000"]?.width).toBe(40);
    expect(map.images.get("psm-pin:%23ff0000")?.pixelRatio).toBe(2);
    await map.getImages(["psm-pin:%23ff0000"]);
    expect(draw).toHaveBeenCalledTimes(1);
    await map.getImages(["psm-pin:%2300ff00"]);
    expect(draw).toHaveBeenCalledTimes(2);
  });

  it("does not draw an image that is already there", async () => {
    const map = new FakeImageMap();
    const draw = vi.fn(fakeDraw);
    installImages(map, { draw });
    map.images.set("psm-pin:%23fff", {
      image: fakeDraw({ kind: "pin", color: "#fff" }, 1),
      pixelRatio: 1,
    });
    await map.resolver!("psm-pin:%23fff");
    expect(draw).not.toHaveBeenCalled();
  });

  it("ignores ids that do not parse", async () => {
    const map = new FakeImageMap();
    const draw = vi.fn(fakeDraw);
    installImages(map, { draw });
    const out = await map.getImages(["sprite", "psm-pin:", "psm-count:x"]);
    expect(Object.values(out)).toEqual([undefined, undefined, undefined]);
    expect(draw).not.toHaveBeenCalled();
    expect(map.images.size).toBe(0);
  });

  it("removes the resolver on dispose", () => {
    const map = new FakeImageMap();
    const remove = installImages(map);
    expect(map.resolver).not.toBeNull();
    remove();
    expect(map.resolver).toBeNull();
  });
});
