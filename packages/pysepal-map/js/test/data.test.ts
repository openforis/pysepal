/// <reference types="geojson" />
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  IN_FLIGHT_MS,
  MAX_IN_FLIGHT_MS,
  MAX_RETRY_MS,
  PayloadCache,
  RETRY_MS,
} from "../data";

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

/** `sent` decides whether each pull reaches Python. */
function setup(sent: () => boolean = () => true) {
  const requests: string[][] = [];
  const arrived = vi.fn();
  const failed = vi.fn();
  const cache = new PayloadCache({
    request: (digests) => {
      requests.push([...digests]);
      return sent();
    },
    arrived,
    failed,
  });
  return { cache, requests, arrived, failed };
}

// Pulls go out once the current task's wants are in.
const settle = () => Promise.resolve();

/** Advance in `step` ms until a new pull goes out; return how long it took. */
function nextPull(requests: string[][], step: number): number {
  const count = requests.length;
  const start = Date.now();
  while (requests.length === count) {
    if (Date.now() - start > 3_600_000) return Infinity;
    vi.advanceTimersByTime(step);
  }
  return Date.now() - start;
}

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

  it("does not pull an in-flight digest again before 30 s", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a", "b"]);
    await settle();
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(IN_FLIGHT_MS - 1);
    expect(requests).toEqual([["a", "b"]]);

    // An unanswered pull may be lost after all: send it again, without a draw.
    vi.advanceTimersByTime(1);
    expect(requests).toEqual([
      ["a", "b"],
      ["a", "b"],
    ]);
    cache.receive(data("a"), [buffer(A)]);
    expect(nextPull(requests, 1000)).toBe(2 * IN_FLIGHT_MS);
    expect(requests.at(-1)).toEqual(["b"]);

    cache.receive(data("b"), [buffer(B)]);
    expect(cache.get("b")).toEqual(B);
    expect(arrived).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10 * MAX_IN_FLIGHT_MS);
    expect(requests).toHaveLength(3);
  });

  it("caps the wait for an unanswered pull", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    const waits = [1, 2, 3, 4, 5].map(() => nextPull(requests, 1000));
    expect(waits).toEqual([
      IN_FLIGHT_MS,
      2 * IN_FLIGHT_MS,
      MAX_IN_FLIGHT_MS,
      MAX_IN_FLIGHT_MS,
      MAX_IN_FLIGHT_MS,
    ]);
  });

  it("retries fast after a missing reply, with capped backoff", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    const waits = [];
    for (let i = 0; i < 7; i++) {
      cache.receive(missing("a"), []);
      waits.push(nextPull(requests, 100));
    }
    expect(waits).toEqual([
      RETRY_MS,
      2 * RETRY_MS,
      4 * RETRY_MS,
      8 * RETRY_MS,
      MAX_RETRY_MS,
      MAX_RETRY_MS,
      MAX_RETRY_MS,
    ]);
    expect(cache.has("a")).toBe(false);
  });

  it("retries only the missing digest, not one still in flight", async () => {
    const { cache, requests } = setup();
    cache.want(["a", "b"]);
    await settle();
    cache.receive(missing("b"), []);
    vi.advanceTimersByTime(RETRY_MS);
    expect(requests).toEqual([["a", "b"], ["b"]]);
    expect(vi.getTimerCount()).toBe(1);
    vi.advanceTimersByTime(IN_FLIGHT_MS - RETRY_MS);
    expect(requests.at(-1)).toEqual(["a"]);
  });

  it("retries fast a pull that could not be sent", async () => {
    let up = false;
    const { cache, requests } = setup(() => up);
    cache.want(["a"]);
    await settle();
    expect(nextPull(requests, 100)).toBe(RETRY_MS);
    up = true;
    expect(nextPull(requests, 100)).toBe(2 * RETRY_MS);
    expect(nextPull(requests, 1000)).toBe(IN_FLIGHT_MS);
  });

  it("pulls a missing digest again at once when a new state wants it", async () => {
    const { cache, requests } = setup();
    cache.want(["a"]);
    await settle();
    cache.receive(missing("a"), []);
    cache.want(["a", "b"]);
    await settle();
    expect(requests).toEqual([["a"], ["a", "b"]]);
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
    vi.advanceTimersByTime(10 * MAX_IN_FLIGHT_MS);
    expect(requests).toHaveLength(1);
  });

  it("stops retrying once the last reference is removed", async () => {
    const { cache, requests, arrived } = setup();
    cache.want(["a", "b"]);
    await settle();
    cache.receive(missing("b"), []);
    cache.want([]);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10 * MAX_IN_FLIGHT_MS);
    expect(requests).toEqual([["a", "b"]]);

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

  it("pulls in-flight and missing digests at once on reconnect", async () => {
    const { cache, requests } = setup();
    cache.want(["a", "b", "c"]);
    await settle();
    cache.receive(data("a"), [buffer(A)]);
    cache.receive(missing("c"), []);
    vi.advanceTimersByTime(IN_FLIGHT_MS + RETRY_MS);
    const count = requests.length;
    cache.reconnect();
    expect(requests.length).toBe(count + 1);
    expect(requests.at(-1)).toEqual(["b", "c"]);
    expect(vi.getTimerCount()).toBe(1);
    // The waits start over.
    expect(nextPull(requests, 1000)).toBe(IN_FLIGHT_MS);
  });

  it("does not retry a payload that fails to decode, and says why", async () => {
    const { cache, requests, arrived, failed } = setup();
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    cache.want(["a"]);
    await settle();
    cache.receive(data("a"), [
      new DataView(new TextEncoder().encode("{").buffer),
    ]);
    expect(error).toHaveBeenCalledOnce();
    expect(cache.has("a")).toBe(false);
    expect(arrived).not.toHaveBeenCalled();
    expect(failed).toHaveBeenCalledExactlyOnceWith("a");
    expect(cache.failure("a")).toMatch(/^the payload is not GeoJSON: /);
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(10 * MAX_IN_FLIGHT_MS);
    expect(requests).toHaveLength(1);
    cache.want([]);
    expect(cache.failure("a")).toBeUndefined();
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
