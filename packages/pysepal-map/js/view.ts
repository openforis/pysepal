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

/** A camera change Python asks for; `seq` only ever grows. */
export interface ViewRequest {
  seq: number;
  center?: LngLat;
  zoom?: number | null;
  bounds?: Bounds;
  padding?: number;
}

/**
 * What moved the camera: a user gesture or its inertia, applying or
 * acknowledging a request, or anything else, such as a resize.
 */
export type Cause = "user" | "request" | "resize";

/** Within one report the strongest cause wins. */
const RANK: Record<Cause, number> = { resize: 0, request: 1, user: 2 };

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
const REQUEST = "psmRequest";

interface MoveEvent {
  [REQUEST]?: unknown;
  /** Set by MapLibre on the moves of a user gesture. */
  originalEvent?: unknown;
}

/** What the camera reads and moves of a MapLibre map. */
export interface CameraMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  getBounds(): {
    getWest(): number;
    getSouth(): number;
    getEast(): number;
    getNorth(): number;
  };
  jumpTo(options: object, eventData?: object): unknown;
  resize(eventData?: object): unknown;
  cameraForBounds(
    bounds: Bounds,
    options?: { padding?: number }
  ): object | undefined;
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
  /** The element the map fills: fits and reports wait while it has no size. */
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

function requestOf(value: unknown): ViewRequest | null {
  if (!value || typeof value !== "object") return null;
  const { seq, center, zoom, bounds, padding } = value as Record<
    string,
    unknown
  >;
  if (!isSeq(seq)) return null;
  if (numbers(bounds, 4)) {
    const pad = isNumber(padding) ? padding : 0;
    return { seq, bounds: bounds as Bounds, padding: pad };
  }
  if (numbers(center, 2) && (zoom == null || isNumber(zoom))) {
    return { seq, center: center as LngLat, zoom: zoom ?? null };
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
 * keep the last user move over a later acknowledgement or resize.
 */
export class ViewCamera {
  /** The sequence of the last request this view applied. */
  private applied = 0;
  /** A fit waiting for the host to have a size; only the latest is kept. */
  private pending: ViewRequest | null = null;
  /** The sequence a report is owed for, and what moved the camera. */
  private owed: number | null = null;
  private cause: Cause = "resize";
  /** A report the comm refused, sent again on reconnect. */
  private refused: { seq: number; cause: Cause } | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private disposed = false;

  constructor(private readonly options: ViewCameraOptions) {}

  start(): void {
    const { map, model } = this.options;
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
    this.onRequest();
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
    this.apply(request);
  };

  private apply(request: ViewRequest): void {
    const { map } = this.options;
    let camera: object | undefined;
    if (request.bounds) {
      // MapLibre measures a container without size as 400 x 300, so a fit
      // there would frame the box for a size nobody sees. A container that
      // just got its size may not have told the map yet, so measure it now.
      if (this.hasSize()) {
        map.resize({ [REQUEST]: request.seq });
        camera = map.cameraForBounds(request.bounds, {
          padding: request.padding,
        });
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
    try {
      map.jumpTo(
        { ...camera, bearing: 0, pitch: 0 },
        { [REQUEST]: request.seq }
      );
    } catch (error) {
      console.error(`pysepal-map: view request ${request.seq} failed`, error);
      return;
    }
    this.applied = request.seq;
    // A jump that changes nothing need not fire a move, so acknowledge here.
    this.owe(request.seq, "request");
  }

  private readonly onMoveEnd = (event: MoveEvent) => {
    // A request's own move is acknowledged by apply().
    if (event[REQUEST] !== undefined) return;
    this.owe(this.applied, event.originalEvent ? "user" : "resize");
  };

  private readonly onResize = (event: MoveEvent) => {
    // apply() measuring the host itself.
    if (event[REQUEST] !== undefined) return;
    if (this.disposed || !this.hasSize()) return;
    const pending = this.pending;
    this.pending = null;
    if (pending) this.apply(pending);
    // A report held while the host had no size goes out now.
    if (this.owed !== null) this.owe(this.owed, this.cause);
  };

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
    if (this.disposed || this.owed === null || !this.hasSize()) return;
    const seq = this.owed;
    this.owed = null;
    this.transmit(this.report(seq, this.cause));
  };

  private cancel(): void {
    if (this.timer !== undefined) clearTimeout(this.timer);
    this.timer = undefined;
    this.owed = null;
  }

  private hasSize(): boolean {
    const { host } = this.options;
    return host.clientWidth > 0 && host.clientHeight > 0;
  }

  private report(seq: number, cause: Cause): ViewReport {
    const { map, viewId } = this.options;
    const center = map.getCenter();
    const bounds = map.getBounds();
    return {
      type: "view_report",
      view_id: viewId,
      center: [center.lng, center.lat],
      zoom: map.getZoom(),
      bounds: [
        bounds.getWest(),
        bounds.getSouth(),
        bounds.getEast(),
        bounds.getNorth(),
      ],
      request_seq: seq,
      cause,
    };
  }
}
