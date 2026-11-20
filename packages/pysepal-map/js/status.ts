/** How often a mounted view repeats `view_open`; Python expires one after 60 s. */
export const HEARTBEAT_MS = 20_000;

export type Status = "loading" | "ready" | "error";

/** A layer's current instance, as the state names it. */
export interface LayerRef {
  id: string;
  token: number;
  instance: number;
}

export interface StatusMessage extends LayerRef {
  type: "status";
  view_id: string;
  side: string;
  status: Status;
  error: string | null;
  /** Set on a rejected style operation: the draw revision it belongs to. */
  style_revision?: number;
}

/** What the reporter reads of a MapLibre tile. */
interface TileLike {
  state?: string;
  tileID?: { key?: string; canonical?: { key?: string } };
}

/** The fields of a map `sourcedata` event the reporter reads. */
export interface SourceEvent {
  sourceId?: string;
  isSourceLoaded?: boolean;
  sourceDataType?: string;
  tile?: TileLike;
}

/** The fields of a map `error` event the reporter reads. */
export interface SourceErrorEvent {
  sourceId?: string;
  error?: unknown;
  tile?: TileLike;
  isSourceLoaded?: boolean;
}

export interface StatusReporterOptions {
  viewId: string;
  side: string;
  send(message: StatusMessage): void;
  /** The source object the map holds under `id` now (`map.getSource`). */
  current(id: string): unknown;
}

/** One owned source, keyed by its id, which names a single layer instance. */
interface Entry {
  ref: LayerRef;
  geojson: boolean;
  /** The source object added under this id; events from any other are stale. */
  source?: unknown;
  /** Loaded; for GeoJSON, only a load after its data was applied counts. */
  loaded: boolean;
  /** A GeoJSON source applied its data (its digest is fixed per instance). */
  content: boolean;
  /** The source failed as a whole; nothing clears it but a new instance. */
  sourceError?: string;
  /** Failed tiles by canonical key, cleared only when that tile loads. */
  failedTiles: Map<string, string>;
  style?: { revision: number; message: string };
  /** The last report sent, to send each change once. */
  last?: string;
}

export function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  const message = (error as { message?: unknown } | null)?.message;
  return message === undefined ? String(error) : String(message);
}

// Tiles of every overscaled and wrapped copy share one URL, the resource.
const tileKey = (tile: TileLike): string =>
  tile.tileID?.canonical?.key ?? tile.tileID?.key ?? "?";

/**
 * Reports the status of each owned source of one view and side to Python.
 *
 * The view registers a source before adding it and retires it before
 * removing it. MapLibre stops forwarding a source's events once it is
 * removed, and every event is checked against the source object this view
 * added under that id, so a late report from a removed or replaced source
 * never reaches its successor.
 */
export class StatusReporter {
  private readonly entries = new Map<string, Entry>();
  private disposed = false;

  constructor(private readonly options: StatusReporterOptions) {}

  /** Register a source about to be added; it is loading until it loads. */
  track(id: string, ref: LayerRef, geojson: boolean): void {
    const style = this.entries.get(id)?.style;
    const last = this.entries.get(id)?.last;
    this.entries.set(id, { ...this.fresh(ref, geojson), style, last });
    this.update(id);
  }

  /** The source object `track` announced, or undefined if none was added. */
  bind(id: string, source: unknown): void {
    const entry = this.entries.get(id);
    if (!entry) return;
    if (source === undefined) this.retire(id);
    else entry.source = source;
  }

  /** Forget a source about to be removed. */
  retire(id: string): void {
    this.entries.delete(id);
  }

  /** A `sourcedata` event. */
  sourceData(event: SourceEvent): void {
    const entry = this.verified(event.sourceId);
    if (!entry) return;
    if (entry.geojson && event.sourceDataType === "content") {
      entry.content = true;
    }
    // A failed tile clears only when that same tile later loads.
    if (event.tile?.state === "loaded") {
      entry.failedTiles.delete(tileKey(event.tile));
    }
    if (event.isSourceLoaded) this.markLoaded(entry);
    this.update(event.sourceId!);
  }

  /** An `error` event outside a style operation; true if it was ours. */
  sourceError(event: SourceErrorEvent): boolean {
    const entry = this.verified(event.sourceId);
    if (!entry) return false;
    const message = messageOf(event.error);
    if (event.tile) entry.failedTiles.set(tileKey(event.tile), message);
    else entry.sourceError ??= message;
    if (event.isSourceLoaded) this.markLoaded(entry);
    this.update(event.sourceId!);
    return true;
  }

  /**
   * The map is idle, so every source finished loading. This never clears
   * an error: an errored tile counts as loaded in MapLibre.
   */
  idle(): void {
    for (const [id, entry] of this.entries) {
      if (!this.isCurrent(id, entry)) continue;
      this.markLoaded(entry);
      this.update(id);
    }
  }

  /** A GeoJSON payload that cannot be decoded, so is never added. */
  payloadFailed(id: string, ref: LayerRef, message: string): void {
    const entry = this.entries.get(id) ?? this.fresh(ref, true);
    entry.sourceError ??= message;
    this.entries.set(id, entry);
    this.update(id);
  }

  /** A style operation on this source's layer failed in draw `revision`. */
  styleFailed(
    id: string,
    ref: LayerRef,
    revision: number,
    message: string
  ): void {
    const entry = this.entries.get(id) ?? this.fresh(ref, false);
    if (entry.style?.revision !== revision) entry.style = { revision, message };
    this.entries.set(id, entry);
    this.update(id);
  }

  /**
   * A pass at `revision` applied every operation, so a style failure from
   * that revision or an earlier one is over. Source ids name instances, so
   * this only ever clears the instance that failed.
   */
  reconciled(revision: number): void {
    for (const [id, entry] of this.entries) {
      if (!entry.style || entry.style.revision > revision) continue;
      entry.style = undefined;
      this.update(id);
    }
  }

  /**
   * Forget sources the state no longer holds, and reset those whose source
   * object went away without a removal, as on a style reload.
   */
  sweep(wanted: ReadonlySet<string>): void {
    for (const [id, entry] of [...this.entries]) {
      if (!wanted.has(id)) {
        this.entries.delete(id);
      } else if (entry.source !== undefined && !this.isCurrent(id, entry)) {
        this.entries.set(id, {
          ...this.fresh(entry.ref, entry.geojson),
          style: entry.style,
          last: entry.last,
        });
        this.update(id);
      }
    }
  }

  /** A message from Python; a `status_request` for this view replays all. */
  receive(content: unknown): void {
    if (this.disposed || !content || typeof content !== "object") return;
    const { type, view_id, side } = content as Record<string, unknown>;
    if (type !== "status_request") return;
    if (view_id !== this.options.viewId || side !== this.options.side) return;
    for (const id of this.entries.keys()) this.update(id, true);
  }

  /** The current report of every source, for tests. */
  inspect(): StatusMessage[] {
    return [...this.entries.values()].map((entry) => this.report(entry));
  }

  dispose(): void {
    this.disposed = true;
    this.entries.clear();
  }

  /** The single exit for reports; the browser harness may hold them here. */
  transmit(message: StatusMessage): void {
    this.options.send(message);
  }

  private fresh(ref: LayerRef, geojson: boolean): Entry {
    return {
      ref: { ...ref },
      geojson,
      loaded: false,
      content: false,
      failedTiles: new Map(),
    };
  }

  private markLoaded(entry: Entry): void {
    if (!entry.geojson || entry.content) entry.loaded = true;
  }

  private isCurrent(id: string, entry: Entry): boolean {
    return (
      entry.source !== undefined && this.options.current(id) === entry.source
    );
  }

  private verified(id: string | undefined): Entry | undefined {
    if (this.disposed || id === undefined) return undefined;
    const entry = this.entries.get(id);
    return entry && this.isCurrent(id, entry) ? entry : undefined;
  }

  /**
   * A source error is reported before a style error: it holds for the whole
   * instance, while Python takes a style error only for its current draw.
   */
  private report(entry: Entry): StatusMessage {
    const base = {
      type: "status" as const,
      view_id: this.options.viewId,
      side: this.options.side,
      ...entry.ref,
    };
    const failed = entry.sourceError ?? entry.failedTiles.values().next().value;
    if (failed !== undefined) {
      return { ...base, status: "error", error: failed };
    }
    if (entry.style) {
      return {
        ...base,
        status: "error",
        error: entry.style.message,
        style_revision: entry.style.revision,
      };
    }
    return { ...base, status: entry.loaded ? "ready" : "loading", error: null };
  }

  private update(id: string, replay = false): void {
    const entry = this.entries.get(id);
    if (this.disposed || !entry) return;
    const message = this.report(entry);
    const key = JSON.stringify([
      message.status,
      message.error,
      message.style_revision,
    ]);
    if (!replay && key === entry.last) return;
    entry.last = key;
    this.transmit(message);
  }
}

export interface ViewPresenceOptions {
  viewId: string;
  side: string;
  send(message: {
    type: "view_open" | "view_close";
    view_id: string;
    side: string;
  }): void;
  /** Where `pagehide` and `pageshow` fire: the window. */
  page: EventTarget;
}

/**
 * Tells Python a view is mounted. A page can die without unmounting its
 * views, so the view repeats its open and Python expires a silent one.
 */
export class ViewPresence {
  private heartbeat: ReturnType<typeof setInterval> | undefined;
  private disposed = false;

  constructor(private readonly options: ViewPresenceOptions) {}

  start(): void {
    this.options.page.addEventListener("pagehide", this.onHide);
    this.options.page.addEventListener("pageshow", this.onShow);
    this.resume();
  }

  /** The comm came back; Python may have expired this view meanwhile. */
  reopen(): void {
    if (!this.disposed) this.send("view_open");
  }

  dispose(): void {
    if (this.disposed) return;
    this.pause();
    this.options.page.removeEventListener("pagehide", this.onHide);
    this.options.page.removeEventListener("pageshow", this.onShow);
    this.send("view_close");
    this.disposed = true;
  }

  private readonly onHide = () => {
    this.pause();
    this.send("view_close");
  };

  private readonly onShow = () => this.resume();

  private resume(): void {
    if (this.disposed) return;
    this.pause();
    this.send("view_open");
    this.heartbeat = setInterval(() => this.send("view_open"), HEARTBEAT_MS);
  }

  private pause(): void {
    if (this.heartbeat !== undefined) clearInterval(this.heartbeat);
    this.heartbeat = undefined;
  }

  private send(type: "view_open" | "view_close"): void {
    this.options.send({
      type,
      view_id: this.options.viewId,
      side: this.options.side,
    });
  }
}

/** A random id for one mounted view; `getRandomValues` works off HTTPS too. */
export function newViewId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}
