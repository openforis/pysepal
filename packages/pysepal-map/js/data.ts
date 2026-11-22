/// <reference types="geojson" />

/** Retry of a `missing` reply or an unsent pull; it doubles per retry. */
export const RETRY_MS = 500;
export const MAX_RETRY_MS = 8000;
/** How long a sent pull waits for its reply before it is sent again. */
export const IN_FLIGHT_MS = 30_000;
export const MAX_IN_FLIGHT_MS = 120_000;

export type Buffer = ArrayBuffer | ArrayBufferView;

export interface PayloadCacheOptions {
  /** Ask Python for these digests (a `pull`); false if it was not sent. */
  request(digests: string[]): boolean;
  /** New payloads are at hand: re-read the latest desired state. */
  arrived(): void;
  /** A payload failed to decode; `failure` now names why. */
  failed?(digest: string): void;
  /** A payload held elsewhere, read before a digest is pulled. */
  lookup?(digest: string): GeoJSON.GeoJSON | undefined;
}

/** A digest that was pulled and still lacks bytes. */
interface Pull {
  /** Sent and awaiting its reply, rather than waiting for a retry. */
  inFlight: boolean;
  /** When to pull it again. */
  due: number;
  retries: number;
  timeouts: number;
}

const backoff = (base: number, max: number, count: number) =>
  Math.min(base * 2 ** count, max);

function decode(buffer: Buffer): GeoJSON.GeoJSON {
  const bytes = ArrayBuffer.isView(buffer)
    ? new Uint8Array(buffer.buffer, buffer.byteOffset, buffer.byteLength)
    : new Uint8Array(buffer);
  return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
}

/**
 * The GeoJSON payloads one view needs, pulled from Python by digest.
 *
 * `want` names the digests the latest state references. Bytes no longer
 * wanted are released, replies for them are ignored, and a decoded payload
 * is never replaced or evicted by a later reply for its digest.
 *
 * One timer pulls again what still lacks bytes, so a lost pull cannot leave
 * the view waiting for a draw that may never come. A pull that was sent is
 * most likely just slow, and each one makes Python send the whole payload,
 * so it is repeated only after a long wait or on reconnect. A `missing`
 * reply or a pull that could not be sent is retried soon. A digest the
 * `lookup` holds is taken from it instead of being pulled.
 */
export class PayloadCache {
  private wanted = new Set<string>();
  private readonly payloads = new Map<string, GeoJSON.GeoJSON>();
  private readonly pulls = new Map<string, Pull>();
  private readonly queued = new Set<string>();
  /** Undecodable payloads, never pulled again while wanted, and why. */
  private readonly failed = new Map<string, string>();
  private flushing = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private timerDue = Infinity;
  private disposed = false;

  constructor(private readonly options: PayloadCacheOptions) {}

  has(digest: string): boolean {
    return this.payloads.has(digest);
  }

  get(digest: string): GeoJSON.GeoJSON | undefined {
    return this.payloads.get(digest);
  }

  /** The digests whose payloads are held. */
  digests(): string[] {
    return [...this.payloads.keys()];
  }

  /** Why a wanted payload could not be decoded, if it could not. */
  failure(digest: string): string | undefined {
    return this.failed.get(digest);
  }

  /** Replace the wanted digests; several sources may share one. */
  want(digests: Iterable<string>): void {
    if (this.disposed) return;
    this.wanted = new Set(digests);
    for (const set of [this.payloads, this.pulls, this.queued, this.failed]) {
      for (const digest of set.keys()) {
        if (!this.wanted.has(digest)) set.delete(digest);
      }
    }
    // A new state may now answer what was missing; its reply is on the way.
    for (const digest of this.outstanding()) {
      if (this.adopt(digest)) continue;
      if (!this.pulls.get(digest)?.inFlight) this.queued.add(digest);
    }
    this.scheduleFlush();
    this.schedule();
  }

  /** Handle a `data` reply: one UTF-8 GeoJSON buffer, or `missing`. */
  receive(reply: unknown, buffers: readonly Buffer[] = []): void {
    if (this.disposed || !reply || typeof reply !== "object") return;
    const { type, digest, missing } = reply as Record<string, unknown>;
    if (type !== "data" || typeof digest !== "string") return;
    if (!this.wanted.has(digest) || this.payloads.has(digest)) return;
    if (missing === true) {
      // Python dropped it, so a newer state is on its way; retry meanwhile.
      this.retryLater(digest);
      this.schedule();
      return;
    }
    if (buffers.length !== 1) return;
    this.pulls.delete(digest);
    try {
      this.payloads.set(digest, decode(buffers[0]));
    } catch (error) {
      const why = error instanceof Error ? error.message : String(error);
      this.failed.set(digest, `the payload is not GeoJSON: ${why}`);
      console.error(`pysepal-map: payload ${digest} is not GeoJSON`, error);
      this.schedule();
      this.options.failed?.(digest);
      return;
    }
    this.schedule();
    this.options.arrived();
  }

  /** The comm came back: pull everything still lacking bytes now. */
  reconnect(): void {
    if (this.disposed) return;
    for (const pull of this.pulls.values()) {
      pull.retries = 0;
      pull.timeouts = 0;
    }
    for (const digest of this.outstanding()) this.queued.add(digest);
    this.flush();
  }

  dispose(): void {
    this.disposed = true;
    this.cancelTimer();
    this.wanted.clear();
    this.payloads.clear();
    this.pulls.clear();
    this.queued.clear();
  }

  private outstanding(): string[] {
    return [...this.wanted].filter(
      (d) => !this.payloads.has(d) && !this.failed.has(d)
    );
  }

  private pull(digest: string): Pull {
    let pull = this.pulls.get(digest);
    if (!pull) {
      pull = { inFlight: false, due: 0, retries: 0, timeouts: 0 };
      this.pulls.set(digest, pull);
    }
    return pull;
  }

  private retryLater(digest: string): void {
    const pull = this.pull(digest);
    pull.inFlight = false;
    pull.due = Date.now() + backoff(RETRY_MS, MAX_RETRY_MS, pull.retries);
    pull.retries += 1;
  }

  private scheduleFlush(): void {
    if (this.flushing || !this.queued.size) return;
    this.flushing = true;
    queueMicrotask(() => {
      this.flushing = false;
      this.flush();
    });
  }

  /** Take a wanted digest from `lookup` rather than pull it; true if held. */
  private adopt(digest: string): boolean {
    const payload = this.options.lookup?.(digest);
    if (payload === undefined) return false;
    this.payloads.set(digest, payload);
    this.pulls.delete(digest);
    this.queued.delete(digest);
    return true;
  }

  private flush(): void {
    if (this.disposed || !this.queued.size) return;
    const queued = [...this.queued];
    this.queued.clear();
    const digests = queued.filter((digest) => !this.adopt(digest));
    if (digests.length < queued.length) {
      this.schedule();
      this.options.arrived();
    }
    if (this.disposed || !digests.length) return;
    const sent = this.options.request(digests);
    const now = Date.now();
    for (const digest of digests) {
      if (!sent) {
        this.retryLater(digest);
        continue;
      }
      const pull = this.pull(digest);
      pull.inFlight = true;
      pull.due = now + backoff(IN_FLIGHT_MS, MAX_IN_FLIGHT_MS, pull.timeouts);
    }
    this.schedule();
  }

  /** Point the one timer at the earliest pull that is due again. */
  private schedule(): void {
    let due = Infinity;
    for (const pull of this.pulls.values()) due = Math.min(due, pull.due);
    if (this.disposed || due === Infinity) {
      this.cancelTimer();
      return;
    }
    if (this.timer !== undefined && this.timerDue === due) return;
    this.cancelTimer();
    this.timerDue = due;
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.timerDue = Infinity;
      const now = Date.now();
      for (const [digest, pull] of this.pulls) {
        if (pull.due > now) continue;
        if (pull.inFlight) pull.timeouts += 1;
        this.queued.add(digest);
      }
      this.flush();
      this.schedule();
    }, Math.max(0, due - Date.now()));
  }

  private cancelTimer(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.timerDue = Infinity;
  }
}
