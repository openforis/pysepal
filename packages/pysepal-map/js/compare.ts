/// <reference types="geojson" />
import type { Map as MapLibreMap } from "maplibre-gl";

import { installImages } from "./images";
import { MapSync, type ViewModel } from "./maplive";
import { StatusReporter, ViewPresence } from "./status";
import type { MapState, ViewSide } from "./types";

const RIGHT = "right";

/** What a view root holds while its right map exists, for tests and the harness. */
export interface CompareRoot {
  psmCompare?: { map: MapLibreMap; status: StatusReporter; sync: MapSync };
}

const stateOf = (model: { get(name: "state"): unknown }): Partial<MapState> => {
  const state = model.get("state");
  return state && typeof state === "object" ? (state as MapState) : {};
};

/**
 * Owns a view root's `data-psm-revision`, from what each side's sync marked.
 *
 * The root shows revision R only when the main sync marked R and, if the
 * state at R compares, the right sync marked R too. Whether to wait for the
 * right side is read from the state, never from whether the right map exists
 * yet: a right map still loading holds the mark back, and disposing the right
 * sync never clears a mark the main sync made.
 */
export class RevisionMark {
  private readonly marked: Record<ViewSide, number | null> = {
    main: null,
    right: null,
  };

  constructor(
    private readonly root: HTMLElement,
    private readonly model: { get(name: "state"): unknown }
  ) {}

  /** What the sync of `side` marked last; null when it stopped holding. */
  set(side: ViewSide, revision: number | null): void {
    this.marked[side] = revision;
    const { revision: latest, compare } = stateOf(this.model);
    const shown =
      typeof latest === "number" &&
      this.marked.main === latest &&
      (compare !== true || this.marked.right === latest);
    if (shown) this.root.dataset.psmRevision = String(latest);
    else delete this.root.dataset.psmRevision;
  }
}

export interface CompareViewOptions {
  root: HTMLElement;
  main: MapLibreMap;
  model: ViewModel;
  viewId: string;
  send(content: unknown): boolean;
  mark: RevisionMark;
  /** The payload the main map holds for a digest. */
  lookup(digest: string): GeoJSON.GeoJSON | undefined;
  /** A MapLibre map in `container`, which takes no input. */
  createMap(container: HTMLElement): MapLibreMap;
}

interface Right {
  container: HTMLElement;
  map: MapLibreMap;
  /** Its first style loaded: before that a redraw has nothing to paint. */
  styled: boolean;
  removeImages(): void;
  reporter: StatusReporter;
  presence: ViewPresence;
  sync: MapSync;
}

/**
 * The right map of a compare view, there while the state compares.
 *
 * It only renders: it sits inside the main map's canvas container, right
 * after the canvas, so the main map's markers and popups paint above it,
 * takes no input and follows the main map's camera. It has its own images,
 * status reports, presence and sync, all on side `right`, and takes the
 * payloads the main map holds instead of pulling them.
 */
export class CompareView {
  private right: Right | null = null;
  private disposed = false;

  constructor(private readonly options: CompareViewOptions) {
    options.model.on("change:state", this.onState);
    this.sync();
  }

  /** Build or drop the right map, as the latest state's `compare` says. */
  sync(): void {
    if (this.disposed) return;
    const compare = stateOf(this.options.model).compare === true;
    if (compare && !this.right) this.open();
    else if (!compare && this.right) this.close();
  }

  /** Whether the right map is settled, or the state does not compare. */
  settled(): boolean {
    if (stateOf(this.options.model).compare !== true) return true;
    return this.right?.sync.settled() ?? false;
  }

  /** Measure the right map's container again, as the root resized. */
  resize(): void {
    this.right?.map.resize();
  }

  /** The comm came back: open the right side again and resend its reports. */
  reconnect(): void {
    const right = this.right;
    if (!right) return;
    right.presence.reopen();
    right.reporter.replay();
    right.sync.reconnect();
  }

  /** What the right map holds, for tests; null while there is none. */
  inspect() {
    return this.right?.sync.inspect() ?? null;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.options.model.off("change:state", this.onState);
    this.close();
  }

  private readonly onState = () => this.sync();

  private open(): void {
    const { root, main, model, viewId, send, mark, lookup, createMap } =
      this.options;
    const document = root.ownerDocument;
    const container = document.createElement("div");
    container.className = "psm-compare-right";
    // Tree order paints the canvas, this map, then the main map's markers.
    main.getCanvas().after(container);
    const map = createMap(container);
    const removeImages = installImages(map);
    const reporter = new StatusReporter({
      viewId,
      side: RIGHT,
      send,
      current: (id) => map.getSource(id),
    });
    const presence = new ViewPresence({
      viewId,
      side: RIGHT,
      send,
      page: document.defaultView ?? window,
    });
    // Open before the first report, so Python counts the side in.
    presence.start();
    const sync = new MapSync(
      map,
      model,
      (revision) => mark.set(RIGHT, revision),
      reporter,
      { viewId, side: RIGHT, lookup }
    );
    const right: Right = {
      container,
      map,
      styled: false,
      removeImages,
      reporter,
      presence,
      sync,
    };
    // MapLibre loads a style a frame later at the earliest.
    map.on("style.load", () => {
      right.styled = true;
    });
    this.right = right;
    (root as CompareRoot).psmCompare = { map, status: reporter, sync };
    main.on("move", this.follow);
    this.follow();
  }

  private close(): void {
    const right = this.right;
    if (!right) return;
    this.right = null;
    const { root, main } = this.options;
    main.off("move", this.follow);
    delete (root as CompareRoot).psmCompare;
    right.sync.dispose();
    // Its view_close drops the side's reports in Python.
    right.presence.dispose();
    right.removeImages();
    right.map.remove();
    right.container.remove();
  }

  private readonly follow = () => {
    const right = this.right;
    if (!right) return;
    const { main } = this.options;
    right.map.jumpTo({
      center: main.getCenter(),
      zoom: main.getZoom(),
      padding: main.getPadding(),
    });
    // Gesture and ease moves fire inside the main map's render: paint now,
    // in the same frame, rather than in the next one.
    if (right.styled) right.map.redraw();
  };
}
