/// <reference types="geojson" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_RETRY_MS, PayloadCache, RETRY_MS } from "../data";

const point = (x: number): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {},
      geometry: { type: "Point", coordinates: [x, 0] },
    },
  ],
});
const A = point(1);
const B = point(2);

/** The payload as a slice of a larger buffer, like a websocket frame. */
function buffer(payload: unknown, pad = 7): DataView {
  const body = new TextEncoder().encode(JSON.stringify(payload));
  const whole = new Uint8Array(body.length + 2 * pad).fill(0x5d); // "]"
  whole.set(body, pad);
  return new DataView(whole.buffer, pad, body.length);
}

const data = (digest: string) => ({ type: "data", digest });
const missing = (digest: string) => ({ type: "data", digest, missing: true });

function setup() {
  const requests: string[][] = [];
  const arrived = vi.fn();
  const cache = new PayloadCache({
    request: (digests) => requests.push([...digests]),
    arrived,
  });
  return { cache, requests, arrived };
}

// Pulls go out once the current task's wants are in.
const settle = () => Promise.resolve();

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("PayloadCache", () => {
  it("coalesces simultaneous wants into one pull per digest", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    cache.want(["a", "b"]);
    cache.want(["b", "a", "a"]);
    await settle();
    expect(requests).toEqual([["a", "b"]]);

    cache.want(["a", "b"]);
    await settle();
    expect(requests).toHaveLength(1);
  });

  it("decodes the buffer slice it was given", async () => {
    const { cache, arrived } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(data("a"), [buffer(A)]);
    expect(cache.get("a")).toEqual(A);
    expect(arrived).toHaveBeenCalledTimes(1);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("recovers from a dropped reply without another draw", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a", "b"]);
    await settle();
    expect(vi.getTimerCount()).toBe(1);

    vi.advanceTimersByTime(RETRY_MS - 1);
    expect(requests).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(requests).toEqual([
      ["a", "b"],
      ["a", "b"],
    ]);
    vi.advanceTimersByTime(2 * RETRY_MS);
    expect(requests).toHaveLength(3);

    cache.receive(data("a"), [buffer(A)]);
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(4 * RETRY_MS);
    expect(requests.at(-1)).toEqual(["b"]);

    cache.receive(data("b"), [buffer(B)]);
    expect(cache.get("b")).toEqual(B);
    expect(arrived).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10 * MAX_RETRY_MS);
    expect(requests).toHaveLength(4);
  });

  it("caps the retry backoff", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    vi.advanceTimersByTime(100 * MAX_RETRY_MS);
    const count = requests.length;
    vi.advanceTimersByTime(MAX_RETRY_MS);
    expect(requests.length).toBe(count + 1);
  });

  it("retries a digest answered missing while it is still wanted", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(missing("a"), []);
    expect(cache.has("a")).toBe(false);
    vi.advanceTimersByTime(RETRY_MS);
    expect(requests).toEqual([["a"], ["a"]]);
  });

  it("keeps the bytes when a missing or duplicate reply comes after success", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(data("a"), [buffer(A)]);
    const payload = cache.get("a");

    cache.receive(missing("a"), []);
    cache.receive(data("a"), [buffer(B)]);
    expect(cache.get("a")).toBe(payload);
    expect(arrived).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(10 * MAX_RETRY_MS);
    expect(requests).toHaveLength(1);
  });

  it("stops retrying once the last reference is removed", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a"]);
    await settle();
    cache.want([]);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10 * MAX_RETRY_MS);
    expect(requests).toEqual([["a"]]);

    cache.receive(data("a"), [buffer(A)]);
    expect(cache.has("a")).toBe(false);
    expect(arrived).not.toHaveBeenCalled();
  });

  it("releases bytes that are no longer wanted and pulls them again later", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(data("a"), [buffer(A)]);
    cache.want(["b"]);
    expect(cache.has("a")).toBe(false);
    expect(cache.digests()).toEqual([]);
    await settle();
    cache.want(["a", "b"]);
    await settle();
    expect(requests).toEqual([["a"], ["b"], ["a"]]);
  });

  it("retries outstanding digests at once on reconnect", async () => {
    const { cache, requests } = setup();
    cache.want(["a", "b"]);
    await settle();
    cache.receive(data("a"), [buffer(A)]);
    cache.reconnect();
    expect(requests).toEqual([["a", "b"], ["b"]]);
    expect(vi.getTimerCount()).toBe(1);
  });

  it("does not retry a payload that fails to decode", async () => {
    const { cache, requests, arrived } = setup();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    cache.want(["a"]);
    await settle();
    cache.receive(data("a"), [
      new DataView(new TextEncoder().encode("{").buffer),
    ]);
    expect(error).toHaveBeenCalledOnce();
    expect(cache.has("a")).toBe(false);
    expect(arrived).not.toHaveBeenCalled();
    vi.advanceTimersByTime(10 * MAX_RETRY_MS);
    expect(requests).toHaveLength(1);
    error.mockRestore();
  });

  it("ignores malformed replies", async () => {
    const { cache, arrived } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(null, []);
    cache.receive({ type: "pull", digest: "a" }, [buffer(A)]);
    cache.receive({ type: "data" }, [buffer(A)]);
    cache.receive(data("a"), []);
    expect(cache.has("a")).toBe(false);
    expect(arrived).not.toHaveBeenCalled();
  });

  it("cancels its timer and ignores replies after dispose", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a"]);
    cache.dispose();
    await settle();
    expect(requests).toEqual([]);
    expect(vi.getTimerCount()).toBe(0);
    cache.receive(data("a"), [buffer(A)]);
    cache.want(["a"]);
    cache.reconnect();
    await settle();
    expect(requests).toEqual([]);
    expect(arrived).not.toHaveBeenCalled();
  });
});
