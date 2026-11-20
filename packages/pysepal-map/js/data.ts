/// <reference types="geojson" />

/** First retry of an unanswered pull; each further retry doubles it. */
export const RETRY_MS = 500;
export const MAX_RETRY_MS = 8000;

export type Buffer = ArrayBuffer | ArrayBufferView;

export interface PayloadCacheOptions {
  /** Ask Python for the bytes of these digests (a `pull` message). */
  request(digests: string[]): void;
  /** New payloads are at hand: re-read the latest desired state. */
  arrived(): void;
}

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
 * is never replaced or evicted by a later reply for its digest. Every
 * digest still lacking bytes is pulled again by one timer with capped
 * exponential backoff, so a lost request or reply cannot leave the view
 * waiting for a draw that may never come.
 */
export class PayloadCache {
  private wanted = new Set<string>();
  private readonly payloads = new Map<string, GeoJSON.GeoJSON>();
  private readonly inFlight = new Set<string>();
  private readonly queued = new Set<string>();
  private readonly failed = new Set<string>();
  private flushing = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private attempt = 0;
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

  /** Replace the wanted digests; several sources may share one. */
  want(digests: Iterable<string>): void {
    if (this.disposed) return;
    this.wanted = new Set(digests);
    for (const set of [
      this.payloads,
      this.inFlight,
      this.queued,
      this.failed,
    ]) {
      for (const digest of set.keys()) {
        if (!this.wanted.has(digest)) set.delete(digest);
      }
    }
    for (const digest of this.outstanding()) {
      if (!this.inFlight.has(digest)) this.queued.add(digest);
    }
    this.scheduleFlush();
    this.updateTimer();
  }

  /** Handle a `data` reply: one UTF-8 GeoJSON buffer, or `missing`. */
  receive(reply: unknown, buffers: readonly Buffer[] = []): void {
    if (this.disposed || !reply || typeof reply !== "object") return;
    const { type, digest, missing } = reply as Record<string, unknown>;
    if (type !== "data" || typeof digest !== "string") return;
    if (!this.wanted.has(digest) || this.payloads.has(digest)) return;
    if (missing === true) {
      // Python dropped it, so a newer state is on its way; retry meanwhile.
      this.inFlight.delete(digest);
      return;
    }
    if (buffers.length !== 1) return;
    this.inFlight.delete(digest);
    try {
      this.payloads.set(digest, decode(buffers[0]));
    } catch (error) {
      this.failed.add(digest);
      console.error(`pysepal-map: payload ${digest} is not GeoJSON`, error);
      this.updateTimer();
      return;
    }
    this.updateTimer();
    this.options.arrived();
  }

  /** The comm came back: pull everything still lacking bytes now. */
  reconnect(): void {
    if (this.disposed) return;
    this.restart();
  }

  dispose(): void {
    this.disposed = true;
    this.cancelTimer();
    this.wanted.clear();
    this.payloads.clear();
    this.inFlight.clear();
    this.queued.clear();
  }

  private outstanding(): string[] {
    return [...this.wanted].filter(
      (d) => !this.payloads.has(d) && !this.failed.has(d)
    );
  }

  private scheduleFlush(): void {
    if (this.flushing || !this.queued.size) return;
    this.flushing = true;
    queueMicrotask(() => {
      this.flushing = false;
      this.flush();
    });
  }

  private flush(): void {
    if (this.disposed || !this.queued.size) return;
    const digests = [...this.queued];
    this.queued.clear();
    for (const digest of digests) this.inFlight.add(digest);
    this.options.request(digests);
    this.updateTimer();
  }

  private restart(): void {
    this.cancelTimer();
    this.attempt = 0;
    for (const digest of this.outstanding()) this.queued.add(digest);
    this.flush();
  }

  private updateTimer(): void {
    if (!this.outstanding().length) {
      this.cancelTimer();
      this.attempt = 0;
      return;
    }
    if (this.timer !== undefined || this.disposed) return;
    const delay = Math.min(RETRY_MS * 2 ** this.attempt, MAX_RETRY_MS);
    this.timer = setTimeout(() => {
      this.timer = undefined;
      this.attempt += 1;
      for (const digest of this.outstanding()) this.queued.add(digest);
      this.flush();
    }, delay);
  }

  private cancelTimer(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
  }
}
