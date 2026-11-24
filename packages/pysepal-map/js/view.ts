/** How long a view gathers camera moves into one report. */
export const REPORT_DELAY_MS = 250;

/**
 * MapLibre options for the Phase 1 camera: north-up and flat, so that a
 * center and a zoom describe it, while panning and zooming still work.
 */
export const CAMERA_OPTIONS = {
  // MapLibre's own minimum, -2, lets a short map reach zooms Python rejects.
  minZoom: 0,
  maxZoom: 24,
  maxPitch: 0,
  pitchWithRotate: false,
  dragRotate: false,
  touchPitch: false,
} as const;

/** Turn off the rotation no map option reaches: two fingers and Shift+arrows. */
export function lockRotation(map: {
  touchZoomRotate: { disableRotation(): void };
  keyboard: { disableRotation(): void };
}): void {
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
}

type LngLat = [number, number];
type Bounds = [number, number, number, number];

/** The CSS pixels other UI covers on each side of the map element. */
export interface Insets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const NO_INSETS: Insets = { left: 0, right: 0, top: 0, bottom: 0 };

/** A camera change Python asks for; `seq` only ever grows. */
export interface ViewRequest {
  seq: number;
  center?: LngLat;
  zoom?: number | null;
  bounds?: Bounds;
  padding?: number;
  /** Null fits up to the map's maximum zoom. */
  max_zoom?: number | null;
  /** Fly there rather than jump. */
  animate: boolean;
}

/**
 * How a request flies: MapLibre's flight, a little faster than its default.
 * A flight longer than `maxDuration` jumps instead, and MapLibre jumps for a
 * user whose system asks for reduced motion.
 */
export const FLIGHT = {
  speed: 1.6,
  maxDuration: 3000,
  essential: false,
} as const;

/**
 * What moved the camera: a user gesture or its inertia, applying or
 * acknowledging a request, a linked map's move that no user made, or
 * anything else, such as a resize.
 */
export type Cause = "user" | "request" | "resize" | "link";

/** Within one report the strongest cause wins. */
const RANK: Record<Cause, number> = { resize: 0, request: 1, link: 2, user: 3 };

export interface ViewReport {
  type: "view_report";
  view_id: string;
  center: LngLat;
  zoom: number;
  bounds: Bounds;
  /** The request the view last applied; other moves count as moves on it. */
  request_seq: number;
  cause: Cause;
}

/** The eventData key that marks a move a request made, with its `seq`. */
export const REQUEST = "psmRequest";

/**
 * The eventData key that marks a jump a linked map made, with a `LinkMark`:
 * `"frame"` for each frame of its movement, which the camera ignores, then,
 * as the movement ends, `"user"` when a user made it and `"link"` otherwise.
 */
export const LINK = "psmLink";

export type LinkMark = "frame" | "user" | "link";

/**
 * The eventData key that marks the jump keeping the map in place on screen
 * while the insets change: linked maps do not follow it, and the camera
 * reports it as a resize.
 */
export const PLACE = "psmPlace";

interface MoveEvent {
  [REQUEST]?: unknown;
  [LINK]?: unknown;
  [PLACE]?: unknown;
  /** Set by MapLibre on the moves of a user gesture. */
  originalEvent?: unknown;
}

/** What the camera reads and moves of a MapLibre map. */
export interface CameraMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  unproject(point: [number, number]): { lng: number; lat: number };
  project(lngLat: { lng: number; lat: number }): { x: number; y: number };
  setPadding(padding: Insets): unknown;
  jumpTo(options: object, eventData?: object): unknown;
  flyTo(options: object, eventData?: object): unknown;
  isMoving(): boolean;
  resize(eventData?: object): unknown;
  /** MapLibre caps the zoom at NaN for a `maxZoom` key that holds undefined. */
  cameraForBounds(
    bounds: Bounds,
    options?: { padding?: number; maxZoom?: number }
  ): { zoom?: number } | undefined;
  on(type: "moveend" | "resize", listener: (event: MoveEvent) => void): unknown;
  off(
    type: "moveend" | "resize",
    listener: (event: MoveEvent) => void
  ): unknown;
}

/** The part of the anywidget model the camera uses. */
export interface CameraModel {
  get(name: "view" | "view_request"): unknown;
  on(name: "change:view_request", callback: () => void): void;
  off(name: "change:view_request", callback: () => void): void;
}

export interface ViewCameraOptions {
  map: CameraMap;
  model: CameraModel;
  viewId: string;
  /**
   * The element the map fills. Fits and reports wait while the insets leave
   * none of it.
   */
  host: { readonly clientWidth: number; readonly clientHeight: number };
  /** Send a report; false if the comm refused it. */
  send(report: ViewReport): boolean;
}

const isNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const isSeq = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0;

const numbers = (value: unknown, count: number): boolean =>
  Array.isArray(value) && value.length === count && value.every(isNumber);

/** The `insets` trait; a side that is not a positive number is 0. */
export function insetsOf(value: unknown): Insets {
  const sides = (value && typeof value === "object" ? value : {}) as Record<
    string,
    unknown
  >;
  const side = (name: keyof Insets) => {
    const px = sides[name];
    return isNumber(px) && px > 0 ? px : 0;
  };
  return {
    left: side("left"),
    right: side("right"),
    top: side("top"),
    bottom: side("bottom"),
  };
}

const sameInsets = (a: Insets, b: Insets): boolean =>
  a.left === b.left &&
  a.right === b.right &&
  a.top === b.top &&
  a.bottom === b.bottom;

function requestOf(value: unknown): ViewRequest | null {
  if (!value || typeof value !== "object") return null;
  const { seq, center, zoom, bounds, padding, max_zoom, animate } =
    value as Record<string, unknown>;
  if (!isSeq(seq)) return null;
  const flies = animate === true;
  if (numbers(bounds, 4)) {
    return {
      seq,
      bounds: bounds as Bounds,
      padding: isNumber(padding) ? padding : 0,
      max_zoom: isNumber(max_zoom) ? max_zoom : null,
      animate: flies,
    };
  }
  if (numbers(center, 2) && (zoom == null || isNumber(zoom))) {
    return {
      seq,
      center: center as LngLat,
      zoom: zoom ?? null,
      animate: flies,
    };
  }
  return null;
}

function savedOf(
  value: unknown
): { center: LngLat; zoom: number; seq: number } | null {
  if (!value || typeof value !== "object") return null;
  const { center, zoom, request_seq } = value as Record<string, unknown>;
  if (!numbers(center, 2) || !isNumber(zoom) || !isSeq(request_seq)) {
    return null;
  }
  return { center: center as LngLat, zoom, seq: request_seq };
}

/**
 * The camera of one mounted view, which the browser owns.
 *
 * Python asks for changes through `view_request`, whose `seq` only grows,
 * and mirrors the last report it accepted in `view`. A view restores that
 * camera and its sequence on mount, then applies each request newer than
 * the one it applied itself. Another view's acknowledgement in `view` never
 * counts as this view's, and moves in another view never move this one.
 *
 * Every move is reported, with the sequence of the request the view last
 * applied: a move a request made is tagged with it, and any other move
 * counts as a move on it. A newer request drops the report an older one
 * still owed, so Python never gets a camera under a sequence it did not
 * come from. Each report says what moved the camera, so that Python can
 * keep the last user or link move over a later acknowledgement or resize.
 *
 * The insets are the map's padding: the camera centers, fits and reports
 * inside the area they leave. When they change, as a panel opens over the
 * map, the map keeps its place on screen and the center moves with the area.
 *
 * A request with `animate` flies there once the view runs, and is reported
 * when the flight ends: a user who takes the map meanwhile ends it, and a
 * newer request replaces it. The request a view finds on mount, and a fit
 * that waited for a usable area, jump: nobody saw the map before.
 */
export class ViewCamera {
  /** The sequence of the last request this view applied. */
  private applied = 0;
  private insets: Insets = NO_INSETS;
  private started = false;
  /** A fit waiting for a usable area; only the latest is kept. */
  private pending: ViewRequest | null = null;
  /** The request whose flight is under way, reported when it ends. */
  private flying: number | null = null;
  /** Requests arriving now may fly: the view has applied the one it found. */
  private live = false;
  /** The sequence a report is owed for, and what moved the camera. */
  private owed: number | null = null;
  private cause: Cause = "resize";
  /** A report the comm refused, sent again on reconnect. */
  private refused: { seq: number; cause: Cause } | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  constructor(private readonly options: ViewCameraOptions) {}

  /**
   * Restore the saved camera and apply a newer request; return the `seq` of
   * the request that moved it past the saved camera, else null.
   */
  start(): number | null {
    const { map, model } = this.options;
    this.started = true;
    // The saved center is the middle of the area inside the insets.
    map.setPadding(this.insets);
    const saved = savedOf(model.get("view"));
    if (saved) {
      map.jumpTo({
        center: saved.center,
        zoom: saved.zoom,
        bearing: 0,
        pitch: 0,
      });
      this.applied = saved.seq;
    }
    // Listen only now: Python already knows the camera it saved.
    map.on("moveend", this.onMoveEnd);
    map.on("resize", this.onResize);
    model.on("change:view_request", this.onRequest);
    const restored = this.applied;
    this.onRequest();
    this.live = true;
    return this.applied > restored ? this.applied : null;
  }

  /**
   * Use `insets` from now on; before `start`, they wait for it. The map
   * keeps its place on screen, unless `keepPlace` is false, as when the view
   * enters or leaves fullscreen: then the center keeps its place in the area.
   */
  setInsets(insets: Insets, keepPlace = true): void {
    if (this.disposed || sameInsets(insets, this.insets)) return;
    const before = this.insets;
    this.insets = { ...insets };
    if (!this.started) return;
    const { map } = this.options;
    if (keepPlace) {
      // The area's middle moves by half of what each side gained.
      const at = map.project(map.getCenter());
      const x =
        at.x + (insets.left - before.left - insets.right + before.right) / 2;
      const y =
        at.y + (insets.top - before.top - insets.bottom + before.bottom) / 2;
      const { lng, lat } = map.unproject([x, y]);
      map.jumpTo(
        { center: [lng, lat], padding: this.insets },
        { [PLACE]: true }
      );
    } else {
      map.setPadding(this.insets);
    }
    this.resume();
  }

  /** The comm came back: send again a report it refused meanwhile. */
  reconnect(): void {
    if (this.disposed || this.refused === null) return;
    const { seq, cause } = this.refused;
    this.refused = null;
    this.owe(seq, cause);
  }

  /** What the camera waits for, for tests. */
  inspect() {
    return {
      applied: this.applied,
      pending: this.pending?.seq ?? null,
      owed: this.owed,
    };
  }

  /** The single exit for reports; the browser harness may hold them here. */
  transmit(report: ViewReport): void {
    const { request_seq: seq, cause } = report;
    this.refused = this.options.send(report) ? null : { seq, cause };
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.cancel();
    const { map, model } = this.options;
    map.off("moveend", this.onMoveEnd);
    map.off("resize", this.onResize);
    model.off("change:view_request", this.onRequest);
  }

  private readonly onRequest = () => {
    if (this.disposed) return;
    const request = requestOf(this.options.model.get("view_request"));
    if (!request || request.seq <= this.applied) return;
    if (this.pending && request.seq <= this.pending.seq) return;
    this.cancel();
    this.refused = null;
    this.pending = null;
    this.apply(request, request.animate && this.live);
  };

  private apply(request: ViewRequest, animate = false): void {
    const { map } = this.options;
    let camera: object | undefined;
    if (request.bounds) {
      // MapLibre measures a container without size as 400 x 300, so a fit
      // there would frame the box for a size nobody sees. A container that
      // just got its size may not have told the map yet, so measure it now.
      if (this.hasSize()) {
        map.resize({ [REQUEST]: request.seq });
        const { max_zoom } = request;
        const fit = map.cameraForBounds(request.bounds, {
          padding: this.fitPadding(request.padding ?? 0),
          ...(max_zoom == null ? {} : { maxZoom: max_zoom }),
        });
        if (fit?.zoom !== undefined) {
          camera = fit;
        }
      }
      if (!camera) {
        this.pending = request;
        return;
      }
    } else if (request.zoom == null) {
      camera = { center: request.center };
    } else {
      camera = { center: request.center, zoom: request.zoom };
    }
    const target = { ...camera, bearing: 0, pitch: 0 };
    const data = { [REQUEST]: request.seq };
    // Before the call: it ends a flight under way, whose report is then due.
    this.flying = animate ? request.seq : null;
    try {
      if (animate) map.flyTo({ ...target, ...FLIGHT }, data);
      else map.jumpTo(target, data);
    } catch (error) {
      this.flying = null;
      console.error(`pysepal-map: view request ${request.seq} failed`, error);
      return;
    }
    this.applied = request.seq;
    // A flight reports as it ends; one MapLibre made a jump has ended already.
    if (this.flying === request.seq && map.isMoving()) return;
    this.flying = null;
    // A jump that changes nothing need not fire a move, so acknowledge here.
    this.owe(request.seq, "request");
  }

  private readonly onMoveEnd = (event: MoveEvent) => {
    const seq = event[REQUEST];
    if (seq !== undefined) {
      // A flight ended, landed or taken over by a user; a jump's move was
      // acknowledged by apply(), as was a flight a newer request replaced.
      if (seq === this.flying) {
        this.flying = null;
        this.owe(seq as number, "request");
      }
      return;
    }
    if (event[LINK] === "frame") return;
    const user = event.originalEvent || event[LINK] === "user";
    const link = event[LINK] === "link";
    this.owe(this.applied, user ? "user" : link ? "link" : "resize");
  };

  private readonly onResize = (event: MoveEvent) => {
    // apply() measuring the host itself.
    if (event[REQUEST] !== undefined) return;
    this.resume();
  };

  /** The usable area changed: run the fit and send the report it held. */
  private resume(): void {
    if (this.disposed || !this.hasSize()) return;
    const pending = this.pending;
    this.pending = null;
    if (pending) this.apply(pending);
    if (this.owed !== null) this.owe(this.owed, this.cause);
  }

  /** Owe a report on `seq`; moves within one delay share a trailing one. */
  private owe(seq: number, cause: Cause): void {
    if (this.owed === null || seq > this.owed) {
      this.owed = seq;
      this.cause = cause;
    } else if (seq === this.owed && RANK[cause] > RANK[this.cause]) {
      this.cause = cause;
    }
    this.timer ??= setTimeout(this.flush, REPORT_DELAY_MS);
  }

  private readonly flush = () => {
    this.timer = undefined;
    // Held while a request flies: its end owes the report again.
    if (this.disposed || this.owed === null || !this.hasSize()) return;
    if (this.flying !== null) return;
    const seq = this.owed;
    this.owed = null;
    this.transmit(this.report(seq, this.cause));
  };

  private cancel(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.owed = null;
  }

  /** The padding, reduced so the usable area keeps 1 px each way. */
  private fitPadding(padding: number): number {
    const { clientWidth, clientHeight } = this.options.host;
    const { left, right, top, bottom } = this.insets;
    const room = Math.min(
      Math.floor((clientWidth - left - right - 1) / 2),
      Math.floor((clientHeight - top - bottom - 1) / 2)
    );
    return Math.max(0, Math.min(padding, room));
  }

  /** Whether the insets leave some of the host. */
  private hasSize(): boolean {
    const { clientWidth, clientHeight } = this.options.host;
    const { left, right, top, bottom } = this.insets;
    return clientWidth - left - right > 0 && clientHeight - top - bottom > 0;
  }

  private report(seq: number, cause: Cause): ViewReport {
    const { map, viewId, host } = this.options;
    const center = map.getCenter();
    // What map.getBounds() does for the whole map, inside the insets.
    const { left, right, top, bottom } = this.insets;
    const [x0, x1] = [left, host.clientWidth - right];
    const [y0, y1] = [top, host.clientHeight - bottom];
    const corners: [number, number][] = [
      [x0, y0],
      [x1, y0],
      [x1, y1],
      [x0, y1],
    ];
    const points = corners.map((corner) => map.unproject(corner));
    const lngs = points.map((p) => p.lng);
    const lats = points.map((p) => p.lat);
    return {
      type: "view_report",
      view_id: viewId,
      center: [center.lng, center.lat],
      zoom: map.getZoom(),
      bounds: [
        Math.min(...lngs),
        Math.min(...lats),
        Math.max(...lngs),
        Math.max(...lats),
      ],
      request_seq: seq,
      cause,
    };
  }
}
