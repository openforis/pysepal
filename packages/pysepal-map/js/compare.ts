/// <reference types="geojson" />
import type { Map as MapLibreMap } from "maplibre-gl";

import { installImages } from "./images";
import { MapSync, type ViewModel } from "./maplive";
import { StatusReporter, ViewPresence } from "./status";
import type { MapState, ViewSide } from "./types";
import { NO_INSETS, type Insets } from "./view";

const RIGHT = "right";

/** How far an arrow key moves the divider, as a fraction of the usable width. */
const STEP = 0.05;

const HANDLE_ATTRIBUTES: Record<string, string> = {
  role: "separator",
  "aria-orientation": "vertical",
  "aria-valuemin": "0",
  "aria-valuemax": "100",
  "aria-label": "Compare divider",
  tabindex: "0",
};

const clamp = (fraction: number) => Math.min(1, Math.max(0, fraction));

/**
 * The divider's x in a view `width` px wide: `fraction` of the way across the
 * area inside the insets, the fraction clamped to [0, 1].
 */
export function dividerX(
  width: number,
  insets: Insets,
  fraction: number
): number {
  const f = clamp(fraction);
  return insets.left + f * (width - insets.left - insets.right);
}

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
  /** The divider line and the handle that moves it, children of the root. */
  divider: HTMLElement;
  handle: HTMLElement;
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
 *
 * A divider clips it to the area right of `dividerX`. Its position is a
 * fraction of the area inside the insets, which the user moves with the
 * handle and which stays here as compare turns off and on.
 */
export class CompareView {
  private right: Right | null = null;
  private disposed = false;
  private fraction = 0.5;
  private insets: Insets = NO_INSETS;
  /** The pointer dragging the handle, and where it took hold of the divider. */
  private grab: { pointerId: number; offset: number } | null = null;

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
    this.place();
  }

  /** The insets the view uses, which the divider stays inside. */
  setInsets(insets: Insets): void {
    this.insets = insets;
    this.place();
  }

  /** The map shown at `point`, in px from the view's top left. */
  pick(point: { x: number; y: number }): MapLibreMap {
    const right = this.right;
    return right && point.x >= this.x() ? right.map : this.options.main;
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
    const divider = document.createElement("div");
    divider.className = "psm-compare-divider";
    const handle = document.createElement("div");
    handle.className = "psm-compare-handle";
    for (const [name, value] of Object.entries(HANDLE_ATTRIBUTES)) {
      handle.setAttribute(name, value);
    }
    handle.addEventListener("pointerdown", this.onPress);
    handle.addEventListener("pointermove", this.onDrag);
    handle.addEventListener("pointerup", this.onRelease);
    handle.addEventListener("pointercancel", this.onRelease);
    handle.addEventListener("lostpointercapture", this.onRelease);
    handle.addEventListener("keydown", this.onKey);
    // Out of the canvas container, where MapLibre's drag and keyboard
    // handlers listen: moving the divider never moves the map.
    root.append(divider, handle);
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
      divider,
      handle,
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
    this.place();
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
    this.grab = null;
    right.divider.remove();
    right.handle.remove();
  }

  /** The divider's x in the view now. */
  private x(): number {
    return dividerX(this.options.root.clientWidth, this.insets, this.fraction);
  }

  /** Clip the right map at the divider and put the line and handle there. */
  private place(): void {
    const right = this.right;
    if (!right) return;
    const { root } = this.options;
    const x = this.x();
    right.container.style.clipPath = `inset(0 0 0 ${x}px)`;
    right.divider.style.left = `${x}px`;
    right.handle.style.left = `${x}px`;
    const { top, bottom } = this.insets;
    right.handle.style.top = `${
      top + (root.clientHeight - top - bottom) / 2
    }px`;
    right.handle.setAttribute(
      "aria-valuenow",
      String(Math.round(this.fraction * 100))
    );
  }

  private moveTo(fraction: number): void {
    this.fraction = clamp(fraction);
    this.place();
  }

  /** The pointer's x in the view. */
  private pointerX(event: PointerEvent): number {
    return event.clientX - this.options.root.getBoundingClientRect().left;
  }

  private readonly onPress = (event: PointerEvent) => {
    const right = this.right;
    if (!right || event.button !== 0) return;
    // No text selection, and no compatibility mouse events.
    event.preventDefault();
    right.handle.setPointerCapture(event.pointerId);
    this.grab = {
      pointerId: event.pointerId,
      offset: this.pointerX(event) - this.x(),
    };
  };

  private readonly onDrag = (event: PointerEvent) => {
    const grab = this.grab;
    if (!grab || event.pointerId !== grab.pointerId) return;
    const { left, right } = this.insets;
    const usable = this.options.root.clientWidth - left - right;
    if (usable <= 0) return;
    const x = this.pointerX(event) - grab.offset;
    this.moveTo((x - left) / usable);
  };

  private readonly onRelease = (event: PointerEvent) => {
    if (event.pointerId === this.grab?.pointerId) this.grab = null;
  };

  private readonly onKey = (event: KeyboardEvent) => {
    const to = keyTarget(event.key, this.fraction);
    if (to === null) return;
    event.preventDefault();
    // The page's own shortcuts would act on the same key.
    event.stopPropagation();
    this.moveTo(to);
  };

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

/** Where a key moves the divider from `fraction`; null for other keys. */
function keyTarget(key: string, fraction: number): number | null {
  switch (key) {
    case "ArrowLeft":
      return fraction - STEP;
    case "ArrowRight":
      return fraction + STEP;
    case "Home":
      return 0;
    case "End":
      return 1;
    default:
      return null;
  }
}
