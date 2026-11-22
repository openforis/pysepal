import type {
  FilterSpecification,
  Map as MapLibreMap,
  MapEventType,
  Source,
} from "maplibre-gl";

import { PayloadCache, type Buffer } from "./data";
import { OWNED_PREFIX, apply, plan, type LiveMap, type Op } from "./reconcile";
import {
  messageOf,
  type LayerRef,
  type SourceErrorEvent,
  type StatusReporter,
} from "./status";
import { parseSourceId, sourceId, toOwnedStyle } from "./translate";
import type { MapState, OwnedStyle } from "./types";

type Layout = Parameters<MapLibreMap["setLayoutProperty"]>;
type Paint = Parameters<MapLibreMap["setPaintProperty"]>;

/** A MapLibre map as the reconciler reads and changes it. */
export function liveMap(map: MapLibreMap): LiveMap {
  return {
    layerOrder: () => map.getLayersOrder(),
    // serialize() returns definitions as set, without defaults filled in.
    layer: (id) => map.getLayer(id)?.serialize(),
    source: (id) => map.getSource(id)?.serialize(),
    sourceIds: () => Object.keys(map.style?.tileManagers ?? {}),
    addSource: (id, spec) => void map.addSource(id, spec),
    removeSource: (id) => void map.removeSource(id),
    setTiles: (id, tiles) => {
      const source = map.getSource(id) as
        | { setTiles?: (tiles: string[]) => unknown }
        | undefined;
      if (!source?.setTiles) throw new Error(`Source "${id}" has no tiles.`);
      source.setTiles(tiles);
    },
    addLayer: (spec, beforeId) => void map.addLayer(spec, beforeId),
    removeLayer: (id) => void map.removeLayer(id),
    moveLayer: (id, beforeId) => void map.moveLayer(id, beforeId),
    // Names and values come from layer specs, which MapLibre validates.
    setLayout: (id, name, value) =>
      void map.setLayoutProperty(id, name as Layout[1], value as Layout[2]),
    setPaint: (id, name, value) =>
      void map.setPaintProperty(id, name as Paint[1], value as Paint[2]),
    setFilter: (id, filter) =>
      void map.setFilter(id, filter as FilterSpecification | null),
    // A missing max keeps the current one, as in Style.setLayerZoomRange.
    setZoomRange: (id, min, max) =>
      void map.setLayerZoomRange(id, min, max as number),
  };
}

/** A style operation MapLibre rejected, by throwing or by an error event. */
export interface Rejection {
  /** The logical layer id, or null for the basemap. */
  layer: string | null;
  revision: number | null;
  message: string;
}

/** The part of the anywidget model a view uses. */
export interface ViewModel {
  get(name: "state"): unknown;
  on(name: string, callback: (...args: any[]) => void): void;
  off(name: string, callback: (...args: any[]) => void): void;
  send(content: unknown): void;
}

/** Which view and side a MapSync keeps, named in its pulls. */
export interface ViewIdentity {
  viewId: string;
  side: string;
}

/** A GeoJSON source this view added, and whether its worker load finished. */
interface Applied {
  digest: string;
  generation: number;
  source?: Source;
  done: boolean;
}

/** The logical layer of an owned style id; ids are built in translate.ts. */
const ownerOf = (id: string): string | null => parseSourceId(id)?.id ?? null;

const opId = (op: Op): string => (op.kind === "addLayer" ? op.layer.id : op.id);

function digestsOf(state: Partial<MapState>): string[] {
  return (state.layers ?? []).flatMap((layer) =>
    layer.kind === "geojson" ? [layer.source.digest] : []
  );
}

/** A layer instance of the state, by the id of its owned source. */
interface Wanted {
  ref: LayerRef;
  geojson: boolean;
  digest?: string;
}

function wantedOf(state: Partial<MapState>): Map<string, Wanted> {
  const wanted = new Map<string, Wanted>();
  if (!Array.isArray(state.layers)) return wanted;
  for (const layer of state.layers) {
    const { id, token, instance } = layer ?? {};
    if (typeof id !== "string" || typeof instance !== "number") continue;
    const geojson = layer.kind === "geojson";
    wanted.set(sourceId(layer), {
      ref: { id, token, instance },
      geojson,
      digest: geojson ? layer.source?.digest : undefined,
    });
  }
  return wanted;
}

/**
 * Keeps one view's map at the state Python declares.
 *
 * Every trigger runs the same pass on the latest model state: reconcile
 * everything whose payload is at hand, then publish `data-psm-revision`
 * once a fresh diff of the full state is empty and every GeoJSON source
 * has finished its worker load in the current style generation.
 */
export class MapSync {
  private readonly map: MapLibreMap;
  private readonly model: ViewModel;
  private readonly root: HTMLElement;
  private readonly reporter: StatusReporter;
  private readonly live: LiveMap;
  private readonly cache: PayloadCache;
  private readonly applied = new Map<string, Applied>();
  private rejected: Rejection[] = [];
  /** The style has loaded; `isStyleLoaded()` also waits for tiles. */
  private ready = false;
  /** Counts style loads, so work done on an earlier style is never trusted. */
  private generation = 0;
  /** A rejected pass, retried only on new input, not on style events. */
  private blocked: {
    revision: number | null;
    generation: number;
    /** The layers in error, when the rest of the state can still settle. */
    failed: Set<string> | null;
  } | null = null;
  /** The pass in progress, which error events are attributed to. */
  private context: {
    revision: number | null;
    id: string;
    errors: Rejection[];
  } | null = null;
  private running = false;
  private pending: boolean | null = null;
  private checkQueued = false;
  private disposed = false;

  constructor(
    map: MapLibreMap,
    model: ViewModel,
    root: HTMLElement,
    reporter: StatusReporter,
    { viewId, side }: ViewIdentity
  ) {
    this.map = map;
    this.model = model;
    this.root = root;
    this.reporter = reporter;
    this.live = liveMap(map);
    this.cache = new PayloadCache({
      // Named, so a pull also tells Python the view is still there.
      request: (digests) =>
        this.send({ type: "pull", view_id: viewId, side, digests }),
      arrived: () => this.sync(true),
      failed: () => this.sync(true),
    });
    model.on("change:state", this.onState);
    model.on("msg:custom", this.onMessage);
    // In place before the first style load, which waits for a frame.
    map.on("styledataloading", this.onStyleLoading);
    map.on("style.load", this.onStyleLoad);
    map.on("styledata", this.onStyleChange);
    map.on("sourcedata", this.onSourceData);
    map.on("error", this.onError);
    map.on("idle", this.onIdle);
    this.onState();
  }

  /** What the view holds, for tests. */
  inspect() {
    return {
      payloads: this.cache.digests(),
      sources: [...this.applied.keys()],
      rejections: this.rejected.map((rejection) => ({ ...rejection })),
      statuses: this.reporter.inspect(),
    };
  }

  /** Whether the root is marked with the revision of the latest state. */
  settled(): boolean {
    const { revision } = this.state();
    return (
      typeof revision === "number" &&
      this.root.dataset.psmRevision === String(revision)
    );
  }

  /** The comm came back: pull every payload still lacking now. */
  reconnect(): void {
    if (!this.disposed) this.cache.reconnect();
  }

  dispose(): void {
    this.disposed = true;
    this.model.off("change:state", this.onState);
    this.model.off("msg:custom", this.onMessage);
    this.map.off("styledataloading", this.onStyleLoading);
    this.map.off("style.load", this.onStyleLoad);
    this.map.off("styledata", this.onStyleChange);
    this.map.off("sourcedata", this.onSourceData);
    this.map.off("error", this.onError);
    this.map.off("idle", this.onIdle);
    this.cache.dispose();
    this.reporter.dispose();
    this.applied.clear();
    this.clearMarker();
  }

  private readonly onState = () => {
    // Pull first, so bytes are on their way while the rest is applied.
    this.cache.want(digestsOf(this.state()));
    this.sync(true);
  };

  private readonly onMessage = (content: unknown, buffers?: Buffer[]) => {
    this.cache.receive(content, buffers);
    this.reporter.receive(content);
  };

  private readonly onStyleLoading = () => {
    // A new style replaces this one; nothing applied to it survives.
    this.ready = false;
    this.clearMarker();
  };

  private readonly onStyleLoad = () => {
    // Fired for the first style, a replaced one, and a diffed setStyle.
    this.ready = true;
    this.generation += 1;
    this.applied.clear();
    this.blocked = null;
    this.clearMarker();
    this.sync(true);
  };

  private readonly onStyleChange = () => {
    // Our own changes notify too: check once per burst, on the latest state.
    if (this.checkQueued) return;
    this.checkQueued = true;
    queueMicrotask(() => {
      this.checkQueued = false;
      this.sync(false);
    });
  };

  private readonly onSourceData = (event: MapEventType["sourcedata"]) => {
    this.reporter.sourceData(event);
    if (event.sourceDataType !== "content") return;
    const record = this.applied.get(event.sourceId);
    // Only the source object this generation added acknowledges its digest.
    if (!record || record.done || !this.isApplied(event.sourceId)) return;
    record.done = true;
    this.sync(false);
  };

  private readonly onError = (event: MapEventType["error"]) => {
    const context = this.context;
    if (context) {
      context.errors.push({
        layer: ownerOf(context.id),
        revision: context.revision,
        message: messageOf(event.error),
      });
      return;
    }
    // A source error (a tile, a TileJSON or a GeoJSON worker failure)
    // carries the id of the source it came from.
    this.reporter.sourceError(event as SourceErrorEvent);
    // Listening for errors turns off MapLibre's own logging of them.
    console.error(event.error);
  };

  private readonly onIdle = () => this.reporter.idle();

  /** Run a pass; `input` is new state, payloads or style, not a style event. */
  private sync(input: boolean): void {
    if (this.disposed || !this.ready) return;
    if (this.running) {
      this.pending = (this.pending ?? false) || input;
      return;
    }
    this.running = true;
    try {
      let next: boolean | null = input;
      while (next !== null) {
        this.pending = null;
        this.pass(next);
        next = this.pending;
      }
    } finally {
      this.running = false;
    }
  }

  private pass(input: boolean): void {
    const state = this.state();
    const revision = typeof state.revision === "number" ? state.revision : null;
    const blocked = this.blocked;
    // A repeatable rejection would otherwise retry on every style event.
    if (
      !input &&
      blocked?.revision === revision &&
      blocked.generation === this.generation
    ) {
      // The rest may have finished loading since: that alone can settle it.
      if (blocked.failed) this.settleRest(state, revision, blocked.failed);
      return;
    }
    const wanted = wantedOf(state);
    let desired: OwnedStyle | undefined;
    const errors = this.capture(revision, () => {
      desired = toOwnedStyle(state as MapState);
      this.reconcileAvailable(desired, wanted);
    });
    this.prune();
    this.reporter.sweep(new Set(wanted.keys()));
    // A layer in error does not hold the revision back: the rest is settled.
    const failed = new Set<string>();
    for (const [id, { ref, digest }] of wanted) {
      const failure =
        digest === undefined ? undefined : this.cache.failure(digest);
      if (failure === undefined) continue;
      this.reporter.payloadFailed(id, ref, failure);
      failed.add(ref.id);
    }
    if (errors.length || !desired) {
      this.reject(errors, revision, wanted);
      // A basemap or whole-state error leaves nothing to call settled.
      if (desired && errors.every((e) => e.layer !== null)) {
        for (const { layer } of errors) failed.add(layer!);
        this.blocked!.failed = failed;
        this.publish(desired, revision, failed);
      }
      return;
    }
    this.blocked = null;
    this.rejected = [];
    if (revision !== null) this.reporter.reconciled(revision);
    this.publish(desired, revision, failed);
  }

  /** Apply the desired sources whose payloads are at hand, and their layers. */
  private reconcileAvailable(
    desired: OwnedStyle,
    wanted: Map<string, Wanted>
  ): void {
    const sources = desired.sources.filter(
      (s) => s.digest === undefined || this.cache.has(s.digest)
    );
    const ids = new Set(sources.map((s) => s.id));
    const available = {
      sources,
      layers: desired.layers.filter((l) =>
        ids.has((l as { source?: string }).source ?? "")
      ),
    };
    const digests = new Map(
      sources.flatMap((s) => (s.digest ? [[s.id, s.digest] as const] : []))
    );
    const live = this.tracked(digests, wanted);
    this.dropUnapplied(live, digests);
    apply(live, plan(live, available), (digest) => this.cache.get(digest)!);
    if (this.context!.errors.length) return;
    // An operation MapLibre ignored without an error would be retried on
    // every style event; reject it instead.
    const rest = plan(live, available);
    if (rest.length) {
      this.context!.id = opId(rest[0]);
      throw new Error(`MapLibre did not take: ${rest.map((op) => op.kind)}`);
    }
  }

  /**
   * Remove owned GeoJSON sources this view did not add in this style
   * generation, such as ones a diffed setStyle kept: their worker state is
   * unknown, so the plan adds them again. So is one added with other bytes
   * than `digests` now names for its id, which the contract rules out but
   * would otherwise never settle.
   */
  private dropUnapplied(live: LiveMap, digests: Map<string, string>): void {
    const stale = new Set(
      live
        .sourceIds()
        .filter(
          (id) =>
            id.startsWith(OWNED_PREFIX) &&
            live.source(id)?.type === "geojson" &&
            (!this.isApplied(id) ||
              (digests.has(id) &&
                this.applied.get(id)!.digest !== digests.get(id)))
        )
    );
    if (!stale.size) return;
    for (const id of live.layerOrder()) {
      // Never read a foreign layer: a custom one throws on serialize().
      if (!id.startsWith(OWNED_PREFIX)) continue;
      const source = (live.layer(id) as { source?: string } | undefined)
        ?.source;
      if (source && stale.has(source)) live.removeLayer(id);
    }
    for (const id of stale) live.removeSource(id);
  }

  /**
   * The live map, noting each operation and each GeoJSON source added. A
   * layer's source is registered for status before the add starts loading
   * it, and retired before it is removed.
   */
  private tracked(
    digests: Map<string, string>,
    wanted: Map<string, Wanted>
  ): LiveMap {
    const live = this.live;
    const note = (id: string) => {
      if (this.context) this.context.id = id;
    };
    const add = (id: string, spec: Parameters<LiveMap["addSource"]>[1]) => {
      const digest = digests.get(id);
      if (spec.type !== "geojson" || digest === undefined) {
        live.addSource(id, spec);
        return;
      }
      // Its completion listener, `sourcedata`, is on since mount.
      const record: Applied = {
        digest,
        generation: this.generation,
        done: false,
      };
      this.applied.set(id, record);
      live.addSource(id, spec);
      record.source = this.map.getSource(id);
    };
    return {
      ...live,
      addSource: (id, spec) => {
        note(id);
        const want = wanted.get(id);
        if (!want) {
          add(id, spec);
          return;
        }
        this.reporter.track(id, want.ref, want.geojson);
        try {
          add(id, spec);
        } catch (error) {
          this.reporter.retire(id);
          throw error;
        }
        // MapLibre adds nothing, without throwing, for a spec it rejects.
        this.reporter.bind(id, this.map.getSource(id));
      },
      removeSource: (id) => {
        note(id);
        this.reporter.retire(id);
        live.removeSource(id);
      },
      setTiles: (id, tiles) => {
        note(id);
        live.setTiles(id, tiles);
      },
      addLayer: (spec, beforeId) => {
        note(spec.id);
        live.addLayer(spec, beforeId);
      },
      removeLayer: (id) => {
        note(id);
        live.removeLayer(id);
      },
      moveLayer: (id, beforeId) => {
        note(id);
        live.moveLayer(id, beforeId);
      },
      setLayout: (id, name, value) => {
        note(id);
        live.setLayout(id, name, value);
      },
      setPaint: (id, name, value) => {
        note(id);
        live.setPaint(id, name, value);
      },
      setFilter: (id, filter) => {
        note(id);
        live.setFilter(id, filter);
      },
      setZoomRange: (id, min, max) => {
        note(id);
        live.setZoomRange(id, min, max);
      },
    };
  }

  private isApplied(id: string): boolean {
    const record = this.applied.get(id);
    return (
      record !== undefined &&
      record.generation === this.generation &&
      record.source !== undefined &&
      record.source === this.map.getSource(id)
    );
  }

  /** Forget records of sources that are gone or were replaced. */
  private prune(): void {
    for (const id of [...this.applied.keys()]) {
      if (!this.isApplied(id)) this.applied.delete(id);
    }
  }

  private settleRest(
    state: Partial<MapState>,
    revision: number | null,
    failed: Set<string>
  ): void {
    try {
      this.publish(toOwnedStyle(state as MapState), revision, failed);
    } catch {
      this.clearMarker();
    }
  }

  private publish(
    desired: OwnedStyle,
    revision: number | null,
    failed: Set<string>
  ): void {
    const left = (id: string) => !failed.has(ownerOf(id) ?? "");
    const loaded = desired.sources.every(
      (s) =>
        !left(s.id) ||
        s.digest === undefined ||
        (this.isApplied(s.id) &&
          this.applied.get(s.id)!.digest === s.digest &&
          this.applied.get(s.id)!.done)
    );
    const todo = plan(this.live, desired).filter((op) =>
      left("layer" in op ? op.layer.id : op.id)
    );
    if (revision !== null && loaded && !todo.length) {
      this.root.dataset.psmRevision = String(revision);
    } else {
      this.clearMarker();
    }
  }

  private reject(
    errors: Rejection[],
    revision: number | null,
    wanted: Map<string, Wanted>
  ): void {
    this.rejected = errors;
    this.blocked = { revision, generation: this.generation, failed: null };
    this.clearMarker();
    for (const { layer, message } of errors) {
      console.error(
        `pysepal-map: revision ${revision} failed on layer ${layer}: ${message}`
      );
      if (layer === null || revision === null) continue;
      for (const [id, want] of wanted) {
        if (want.ref.id === layer) {
          this.reporter.styleFailed(id, want.ref, revision, message);
        }
      }
    }
  }

  /** Run `body`, collecting what it throws and the error events it fires. */
  private capture(revision: number | null, body: () => void): Rejection[] {
    const context = { revision, id: "", errors: [] as Rejection[] };
    this.context = context;
    try {
      body();
    } catch (error) {
      context.errors.push({
        layer: ownerOf(context.id),
        revision,
        message: messageOf(error),
      });
    } finally {
      this.context = null;
    }
    return context.errors;
  }

  private clearMarker(): void {
    delete this.root.dataset.psmRevision;
  }

  private state(): Partial<MapState> {
    const state = this.model.get("state");
    return state && typeof state === "object" ? (state as MapState) : {};
  }

  private send(content: unknown): boolean {
    try {
      this.model.send(content);
      return true;
    } catch (error) {
      // A closed comm; the retry timer or a reconnect pulls again.
      console.error("pysepal-map: could not send", error);
      return false;
    }
  }
}
