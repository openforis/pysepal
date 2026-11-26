import type { LayerSpecification, Map as MapLibreMap } from "maplibre-gl";
import {
  TerraDraw,
  TerraDrawCircleMode,
  TerraDrawExtend,
  TerraDrawLineStringMode,
  TerraDrawPointMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
  TerraDrawSelectMode,
} from "terra-draw";
import { TerraDrawMapLibreGLAdapter } from "terra-draw-maplibre-gl-adapter";

import type {
  DrawFeature,
  DrawingState,
  DrawnState,
  DrawRequestState,
  DrawToolState,
} from "./types";

export type { DrawFeature } from "./types";

/** The drawing tools, as Python's `DRAW_MODES` names them. */
export const DRAW_MODES = [
  "polygon",
  "rectangle",
  "circle",
  "linestring",
  "point",
] as const;
const SELECT = "select";
const STATIC = "static";
const KNOWN = new Set<string>([...DRAW_MODES, SELECT, STATIC]);
const DEFAULT_COLOR = "#3388ff";

/** The decimals Terra Draw keeps: its adapter's coordinatePrecision. */
export const PRECISION = 9;

/**
 * The prefix of the sources and layers Terra Draw's adapter adds. It is not
 * `mapframe:`, so they are foreign layers that every owned layer stays below.
 */
export const DRAW_PREFIX = "mapframe-draw";
/** What adapter 1.5.0 adds on start (`register`) and removes on stop. */
export const ADAPTER_SOURCES = ["point", "linestring", "polygon"].map(
  (geometry) => `${DRAW_PREFIX}-${geometry}`
);
const ADAPTER_LAYERS = [
  "point",
  "point-marker",
  "linestring",
  "polygon",
  "polygon-outline",
].map((part) => `${DRAW_PREFIX}-${part}`);

/**
 * Properties that mark a feature Terra Draw adds for its own use, read in the
 * Terra Draw 1.39 source: `currentlyDrawing` on a feature still being drawn
 * (every drawing mode), `closingPoint` on the polygon and linestring modes'
 * closing points, `snappingPoint` on snapping guidance, `selectionPoint` and
 * `midPoint` on the select mode's vertex and midpoint handles,
 * `coordinatePoint` on coordinate points, and `edited` on the point a drawing
 * mode drags while editing (`GUIDANCE_POINT_PROPERTY_KEYS` in common.ts).
 */
const HELPER_FLAGS = [
  "currentlyDrawing",
  "closingPoint",
  "snappingPoint",
  "selectionPoint",
  "midPoint",
  "coordinatePoint",
  "edited",
];
/**
 * Terra Draw's reserved property names (`SELECT_PROPERTIES` and
 * `COMMON_PROPERTIES`) other than `mode`: flags of the moment, such as
 * `selected`, that a committed feature carries while it is edited. A feature
 * added with one could be taken for a helper or shown selected.
 */
const TRANSIENT = new Set([
  "selected",
  "midPoint",
  "selectionPointFeatureId",
  "selectionPoint",
  "currentlyDrawing",
  "edited",
  "closingPoint",
  "snappingPoint",
  "coordinatePoint",
  "coordinatePointFeatureId",
  "coordinatePointIds",
  "provisionalCoordinateCount",
  "committedCoordinateCount",
  // Select mode fetches its default marker image from raw.githubusercontent.com
  // for a point flagged `marker`, which breaks the no-CDN rule.
  "marker",
]);
/** The mode a geometry is drawn under when its own mode rejects it. */
const GEOMETRY_MODES: Record<string, string> = {
  Polygon: "polygon",
  LineString: "linestring",
  Point: "point",
};
/** The geometry each drawing mode draws. */
const MODE_GEOMETRIES: Record<string, string> = {
  polygon: "Polygon",
  rectangle: "Polygon",
  circle: "Polygon",
  linestring: "LineString",
  point: "Point",
};
const UUID4 =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

const FILL_OPACITY = 0.2;
const WHITE = "#ffffff";
/** Outlines, lines and point outlines. */
const LINE_WIDTH = 2;
/** Terra Draw 1.39's point radii, which the styles leave as they are. */
const POINT_WIDTH = 6;
const MIDPOINT_WIDTH = 4;

/** One mode Terra Draw is built with: its name and its constructor options. */
export interface ModeSpec {
  name: string;
  options: Record<string, unknown>;
}

/** Each mode's styles: outlines, lines and points in the colour, fills in it at 0.2. */
function stylesFor(name: string, color: string): Record<string, unknown> {
  const handles = {
    closingPointColor: color,
    closingPointOutlineColor: WHITE,
    snappingPointColor: color,
    snappingPointOutlineColor: WHITE,
    coordinatePointColor: color,
    coordinatePointOutlineColor: WHITE,
  };
  switch (name) {
    case "polygon":
    case "rectangle":
    case "circle":
      return {
        fillColor: color,
        fillOpacity: FILL_OPACITY,
        outlineColor: color,
        outlineWidth: LINE_WIDTH,
        ...handles,
      };
    case "linestring":
      return {
        lineStringColor: color,
        lineStringWidth: LINE_WIDTH,
        ...handles,
      };
    case "point":
      return {
        pointColor: color,
        pointOutlineColor: WHITE,
        pointOutlineWidth: LINE_WIDTH,
        snappingPointColor: color,
      };
    default:
      return {
        selectedPolygonColor: color,
        selectedPolygonFillOpacity: FILL_OPACITY,
        selectedPolygonOutlineColor: color,
        selectedPolygonOutlineWidth: LINE_WIDTH,
        selectedLineStringColor: color,
        selectedPointColor: color,
        selectedPointOutlineColor: WHITE,
        selectionPointColor: color,
        selectionPointOutlineColor: WHITE,
        midPointColor: color,
        midPointOutlineColor: WHITE,
      };
  }
}

/** What the select mode lets a user edit of each drawing mode's features. */
function selectFlags() {
  const vertices = { draggable: true, midpoints: true, deletable: true };
  return {
    polygon: { feature: { draggable: true, coordinates: { ...vertices } } },
    linestring: { feature: { draggable: true, coordinates: { ...vertices } } },
    // Resizing keeps a rectangle a rectangle and a circle round, which a
    // free vertex drag would not.
    rectangle: {
      feature: { draggable: true, coordinates: { resizable: "opposite" } },
    },
    circle: {
      feature: { draggable: true, coordinates: { resizable: "center-fixed" } },
    },
    point: { feature: { draggable: true } },
  };
}

/**
 * Every mode a view registers, whatever the toolbar offers, since a feature
 * drawn or seeded under any of them can come back. Terra Draw adds `static`.
 */
export function modeSpecs(color: string): ModeSpec[] {
  return [
    ...DRAW_MODES.map((name) => ({
      name,
      options: { styles: stylesFor(name, color) },
    })),
    {
      name: SELECT,
      options: { flags: selectFlags(), styles: stylesFor(SELECT, color) },
    },
  ];
}

/** `value` as Terra Draw keeps it, as its `limitPrecision` does. */
function round(value: number): number {
  const scale = 10 ** PRECISION;
  return Math.round(value * scale) / scale;
}

type Position = number[];

function positionsOf(geometry: DrawFeature["geometry"]): Position[] {
  const { type, coordinates } = geometry;
  if (type === "Point") return [coordinates as Position];
  if (type === "LineString") return coordinates as Position[];
  if (type === "Polygon") return (coordinates as Position[][]).flat();
  return [];
}

function movePositions(
  geometry: DrawFeature["geometry"],
  move: (position: Position) => Position
): DrawFeature["geometry"] {
  const { type, coordinates } = geometry;
  if (type === "Point")
    return { type, coordinates: move(coordinates as Position) };
  if (type === "LineString") {
    return { type, coordinates: (coordinates as Position[]).map(move) };
  }
  return {
    type,
    coordinates: (coordinates as Position[][]).map((ring) => ring.map(move)),
  };
}

const inRange = ([lng, lat]: Position) =>
  lng >= -180 && lng <= 180 && lat >= -90 && lat <= 90;

/**
 * `geometry` moved by whole turns so its first vertex lies in [-180, 180],
 * then rounded again (`360.1 - 360` is `0.10000000000002274`), or null if it
 * still does not fit: it crosses the antimeridian. MapLibre draws repeated
 * worlds and the adapter reports their longitudes, which Terra Draw rejects
 * when they are added back.
 */
export function onTheGlobe(
  geometry: DrawFeature["geometry"]
): DrawFeature["geometry"] | null {
  const first = positionsOf(geometry)[0];
  if (!first) return null;
  const lng = first[0];
  const turns = lng >= -180 && lng <= 180 ? 0 : Math.floor((lng + 180) / 360);
  const moved = movePositions(geometry, ([x, y]) => [
    round(x - 360 * turns),
    round(y),
  ]);
  return positionsOf(moved).every(inRange) ? moved : null;
}

/**
 * The committed features of a Terra Draw snapshot, as a view reports them:
 * no helpers, no feature still being drawn, no flags of the moment, and each
 * moved onto the globe. One that crosses the antimeridian is left out.
 */
export function snapshotOf(features: DrawFeature[]): DrawFeature[] {
  const out: DrawFeature[] = [];
  for (const feature of features) {
    const properties = feature.properties ?? {};
    if (HELPER_FLAGS.some((flag) => properties[flag])) continue;
    const geometry = onTheGlobe(feature.geometry);
    if (!geometry) {
      console.warn(
        `mapframe: drawing ${feature.id} crosses the antimeridian, which is not supported; it is left out`
      );
      continue;
    }
    out.push({
      type: "Feature",
      id: feature.id,
      geometry,
      properties: withoutTransient(properties),
    });
  }
  return out;
}

function withoutTransient(
  properties: Record<string, unknown>
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(properties).filter(([name]) => !TRANSIENT.has(name))
  );
}

/**
 * The id `prepareFeatures` gives the feature at `index` of the batch of
 * request `seq`: the seq in 8 hex digits and the index in 12, in the shape of
 * a UUID4, which Terra Draw takes.
 */
export function featureId(seq: number, index: number): string {
  const hex = (value: number, digits: number) =>
    value.toString(16).padStart(digits, "0").slice(-digits);
  return `${hex(seq, 8)}-0000-4000-8000-${hex(index, 12)}`;
}

/**
 * The features of the batch of request `seq` as Terra Draw takes them, the
 * same in every view: coordinates rounded to its 9 decimals, its reserved
 * property names dropped but `mode`, a `mode` that does not draw the geometry
 * replaced by the geometry's own, and an id that is not a UUID4 string, or
 * repeats one of the batch, replaced by `featureId(seq, index)`.
 */
export function prepareFeatures(
  features: DrawFeature[],
  seq: number
): DrawFeature[] {
  const used = new Set<string | number>();
  return features.map((feature, index) => {
    const { geometry } = feature;
    const properties = withoutTransient(feature.properties ?? {});
    const { mode } = properties;
    const own = GEOMETRY_MODES[geometry?.type];
    if (
      own &&
      (typeof mode !== "string" || MODE_GEOMETRIES[mode] !== geometry.type)
    ) {
      properties.mode = own;
    }
    let id = feature.id;
    if (typeof id !== "string" || !UUID4.test(id) || used.has(id)) {
      id = featureId(seq, index);
    }
    used.add(id);
    return {
      type: "Feature",
      id,
      geometry: own
        ? movePositions(geometry, (position) => position.map(round))
        : geometry,
      properties,
    };
  });
}

/** The point handles Terra Draw draws as vertices; `midPoint` is the other one. */
const VERTEX_FLAGS = [
  "selectionPoint",
  "closingPoint",
  "snappingPoint",
  "coordinatePoint",
  "edited",
];

function roleOf({ geometry, properties }: DrawFeature): string {
  if (geometry.type !== "Point") return "shape";
  const flags = properties ?? {};
  if (flags.midPoint) return "midpoint";
  return VERTEX_FLAGS.some((flag) => flags[flag]) ? "vertex" : "shape";
}

/**
 * What Terra Draw renders of a snapshot, shapes being drawn and handles
 * included, as plain features whose only property, `mapframeRole`, is `shape`,
 * `vertex` or `midpoint`. The coordinates stay as Terra Draw holds them.
 */
export function mirrorFeatures(snapshot: DrawFeature[]): DrawFeature[] {
  return snapshot.map((feature) => ({
    type: "Feature",
    id: feature.id,
    geometry: feature.geometry,
    properties: { mapframeRole: roleOf(feature) },
  }));
}

/** The source of a copy of the drawing on another map; not `mapframe:`, so no sync removes it. */
export const MIRROR_SOURCE = `${DRAW_PREFIX}-mirror`;

/** The layers that draw `mirrorFeatures` in `color` as `modeSpecs(color)` styles Terra Draw. */
export function mirrorLayers(color: string): LayerSpecification[] {
  const source = MIRROR_SOURCE;
  return [
    {
      id: `${source}-fill`,
      type: "fill",
      source,
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": color, "fill-opacity": FILL_OPACITY },
    },
    {
      id: `${source}-line`,
      type: "line",
      source,
      filter: ["!=", ["geometry-type"], "Point"],
      paint: { "line-color": color, "line-width": LINE_WIDTH },
    },
    {
      id: `${source}-point`,
      type: "circle",
      source,
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-color": color,
        "circle-radius": [
          "match",
          ["get", "mapframeRole"],
          "midpoint",
          MIDPOINT_WIDTH,
          POINT_WIDTH,
        ],
        "circle-stroke-color": WHITE,
        "circle-stroke-width": LINE_WIDTH,
      },
    },
  ];
}

/** A key that two snapshots share when they hold the same features. */
function keyOf(features: DrawFeature[]): string {
  const sorted = [...features].sort((a, b) =>
    String(a.id) < String(b.id) ? -1 : String(a.id) > String(b.id) ? 1 : 0
  );
  return JSON.stringify(sorted, (_key, value) =>
    value && typeof value === "object" && !Array.isArray(value)
      ? Object.fromEntries(
          Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        )
      : value
  );
}

/** The validation Terra Draw returns for each feature it was given. */
export interface DrawValidation {
  id?: string | number;
  valid: boolean;
  reason?: string;
}

type DrawEvent = "finish" | "change";

/** The part of Terra Draw a view uses. */
export interface DrawEngine {
  start(): void;
  stop(): void;
  setMode(mode: string): void;
  getMode(): string;
  addFeatures(features: DrawFeature[]): DrawValidation[];
  clear(): void;
  getSnapshot(): DrawFeature[];
  updateModeOptions(mode: string, options: object): void;
  on(event: DrawEvent, listener: (...args: any[]) => void): void;
  off(event: DrawEvent, listener: (...args: any[]) => void): void;
}

interface Toggle {
  isEnabled(): boolean;
  enable(): unknown;
  disable(): unknown;
}

type StyleEvent = "styledataloading" | "style.load" | "styledata";

/** The part of a MapLibre map the drawing view reads. */
export interface DrawMap {
  getSource(id: string): unknown;
  dragPan: Toggle;
  doubleClickZoom: Toggle;
  on(type: StyleEvent, listener: () => void): unknown;
  off(type: StyleEvent, listener: () => void): unknown;
}

/** The part of the anywidget model the drawing view uses. */
export interface DrawModel {
  get(name: "drawing" | "draw_request" | "drawn" | "draw_tool"): unknown;
  on(name: string, callback: () => void): void;
  off(name: string, callback: () => void): void;
}

const TOOLS = Symbol.for("mapframe.tools");

/**
 * The tool requests a view of the page applied, each to its seq: page state,
 * shared by every bundle loaded, as `pageRegistry` is. anywidget gives each
 * view its own model proxy, so the key is the `draw_tool` value, which every
 * view of one model reads until the next request replaces it.
 */
export function consumedTools(): WeakMap<object, number> {
  const scope = globalThis as { [TOOLS]?: WeakMap<object, number> };
  return (scope[TOOLS] ??= new WeakMap());
}

/** What changed a view's drawing: a user, or applying a request. */
export type DrawCause = "user" | "request";

export interface DrawReport {
  type: "draw_report";
  view_id: string;
  side: string;
  /** The request the view last applied; a user's edits count as edits on it. */
  request_seq: number;
  cause: DrawCause;
  features: DrawFeature[];
}

export interface ViewDrawOptions {
  map: DrawMap;
  model: DrawModel;
  viewId: string;
  side: string;
  /** Send a report; false if the comm refused it. */
  send(report: DrawReport): boolean;
  /** Build a Terra Draw with these modes; see `terraDraw`. */
  createDraw(modes: ModeSpec[]): DrawEngine;
  /** Drawing became interactive, or stopped being so. */
  onInteractiveChange?(): void;
  /**
   * What Terra Draw renders changed, or its colour: `mirrorFeatures` of its
   * snapshot, `[]` once it stopped. Told on each of its changes, the view's
   * own too, and after the view changed it.
   */
  onRendered?(features: DrawFeature[], color: string): void;
  /** The tools offered, their labels or the active one changed. */
  onToolsChange?(
    modes: string[],
    labels: Record<string, string>,
    active: string
  ): void;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

const isSeq = (value: unknown): value is number =>
  Number.isInteger(value) && (value as number) >= 0;

const featuresOf = (value: unknown): DrawFeature[] =>
  Array.isArray(value)
    ? (value.filter(isRecord) as unknown as DrawFeature[])
    : [];

function drawingOf(value: unknown): DrawingState {
  const { session, modes, color, labels } = isRecord(value) ? value : {};
  return {
    session: isSeq(session) ? session : 0,
    modes: Array.isArray(modes)
      ? modes.filter((m): m is string => typeof m === "string")
      : [],
    color: typeof color === "string" ? color : DEFAULT_COLOR,
    labels: Object.fromEntries(
      Object.entries(isRecord(labels) ? labels : {}).filter(
        (entry): entry is [string, string] => typeof entry[1] === "string"
      )
    ),
  };
}

function toolOf(value: unknown): DrawToolState {
  const { seq, session, mode } = isRecord(value) ? value : {};
  return {
    seq: isSeq(seq) ? seq : 0,
    session: isSeq(session) ? session : 0,
    mode: typeof mode === "string" ? mode : STATIC,
  };
}

function requestOf(value: unknown): DrawRequestState {
  const { seq, features } = isRecord(value) ? value : {};
  return { seq: isSeq(seq) ? seq : 0, features: featuresOf(features) };
}

function drawnOf(value: unknown): DrawnState {
  const { request_seq, features } = isRecord(value) ? value : {};
  return {
    request_seq: isSeq(request_seq) ? request_seq : 0,
    features: featuresOf(features),
  };
}

/**
 * The drawing of one mounted view, which the browser owns, as it owns the
 * camera.
 *
 * While `drawing` offers tools and the style has loaded, the view runs its own
 * Terra Draw for the session `drawing` names. Python asks for features through
 * `draw_request`, whose `seq` only grows, and mirrors the last report it
 * accepted in `drawn`. The view prepares every feature it adds with
 * `prepareFeatures`. On its first start it restores `drawn` when it is as new
 * as the request, else applies the request. A new session drops the features
 * and starts Terra Draw again, empty, then applies the request if it is newer
 * than the last one applied. An end, which leaves no tools, stops Terra Draw
 * and drops the features. A restart in one session, after a style
 * replacement, restores the view's own features unless a newer request came.
 * Views never follow each other.
 *
 * Applying a request replaces the features and acknowledges it with a report
 * of cause `request`. A user's finished drawing or edit, or deletion of a
 * drawn feature, sends a report of cause `user` on the request last applied,
 * unless the features are the ones last sent. Nothing Terra Draw fires while
 * the view itself changes it counts as a user's.
 *
 * The view holds the user's tool, `active`, apart from Terra Draw's mode:
 * `setMode` sets it, and a new session starts with none. A restart in one
 * session enters it again and reads no `draw_tool`. Only a first start in a
 * session reads `draw_tool`, and applies the request when it names that
 * session and no view of the page applied it (`consumedTools`). A running
 * view applies each request for its session newer than the last it applied.
 */
export class ViewDraw {
  private engine: DrawEngine | null = null;
  private wanted: DrawingState;
  /** The style has loaded; Terra Draw cannot add its layers before. */
  private ready = false;
  /** A start failed; only a new `drawing` tries again. */
  private failed = false;
  /** Whether the view started once: its first start may restore `drawn`. */
  private started = false;
  /** The session Terra Draw runs, or last ran, for. */
  private session = 0;
  /** The sequence of the last request this view applied. */
  private applied = 0;
  /** The view's committed features, kept while Terra Draw is stopped in a session. */
  private committed: DrawFeature[] = [];
  private committedIds = new Set<string | number>();
  private lastSent: string | null = null;
  /** A report the comm refused, sent again on reconnect. */
  private refused: DrawReport | null = null;
  /** Set while the view changes Terra Draw itself, whose events then count for nothing. */
  private quiet = 0;
  /** The user's tool in the session `wanted` names. */
  private active = STATIC;
  /** The seq of the last tool request this view applied, or saw at a first start. */
  private toolSeq = 0;
  private toldTools: string;
  /** The mode and colour Terra Draw has now. */
  private mode = STATIC;
  private color: string;
  /** Drag pan and double-click zoom as they were when Terra Draw started. */
  private navigation: { dragPan: boolean; doubleClickZoom: boolean } | null =
    null;
  private wasInteractive = false;
  private disposed = false;

  constructor(private readonly options: ViewDrawOptions) {
    const { map, model } = options;
    this.wanted = drawingOf(model.get("drawing"));
    this.color = this.wanted.color;
    // The host reads the first tools from `tools()` once it placed its controls.
    this.toldTools = JSON.stringify(this.tools());
    // In place before the first style load, which waits for a frame.
    map.on("styledataloading", this.onStyleLoading);
    map.on("style.load", this.onStyleLoad);
    map.on("styledata", this.onStyleData);
    model.on("change:drawing", this.onDrawing);
    model.on("change:draw_request", this.onRequest);
    model.on("change:draw_tool", this.onTool);
  }

  /** Whether drawing holds clicks, popups, tooltips and the cursor. */
  interactive(): boolean {
    return this.wanted.modes.length > 0 && this.active !== STATIC;
  }

  /** The tools offered, their labels and the active one, as the toolbar shows them. */
  tools(): { modes: string[]; labels: Record<string, string>; active: string } {
    const { modes, labels } = this.wanted;
    return { modes: [...modes], labels: { ...labels }, active: this.active };
  }

  /** Make `mode` the active tool, or none for `static`; a mode not offered is ignored. */
  setMode(mode: string): void {
    if (this.disposed || !this.choose(mode)) return;
    this.tell();
    this.tellTools();
  }

  /**
   * Remove every drawn feature, as a user would, and report it even when
   * nothing was drawn: a host may wait for a user report to drop a drawing
   * of its own.
   */
  clearAll(): void {
    if (this.disposed || !this.wanted.modes.length) return;
    const engine = this.engine;
    if (engine) {
      this.hush(() => engine.clear());
      this.commit();
    } else {
      this.drop();
    }
    this.report("user");
  }

  /** The comm came back: send again a report it refused meanwhile. */
  reconnect(): void {
    if (this.disposed || this.refused === null) return;
    const report = this.refused;
    this.refused = null;
    this.transmit(report);
  }

  /** The single exit for reports; the browser harness may hold them here. */
  transmit(report: DrawReport): void {
    this.refused = this.options.send(report) ? null : report;
  }

  /** What the view holds, for tests. */
  inspect() {
    return {
      running: this.engine !== null,
      session: this.session,
      mode: this.mode,
      active: this.active,
      color: this.color,
      applied: this.applied,
      committed: structuredClone(this.committed),
      store: this.engine ? this.engine.getSnapshot() : [],
    };
  }

  dispose(): void {
    if (this.disposed) return;
    this.halt();
    this.disposed = true;
    const { map, model } = this.options;
    map.off("styledataloading", this.onStyleLoading);
    map.off("style.load", this.onStyleLoad);
    map.off("styledata", this.onStyleData);
    model.off("change:drawing", this.onDrawing);
    model.off("change:draw_request", this.onRequest);
    model.off("change:draw_tool", this.onTool);
  }

  private readonly onDrawing = () => {
    if (this.disposed) return;
    const before = this.wanted.session;
    this.wanted = drawingOf(this.options.model.get("drawing"));
    this.failed = false;
    const { session, modes, color } = this.wanted;
    if (!modes.length || session !== before) this.active = STATIC;
    if (!modes.length) {
      // The session ended: its features go with it.
      this.halt();
      this.drop();
    } else if (!this.engine) {
      if (this.ready) this.begin();
    } else if (session !== this.session) {
      this.halt();
      this.begin();
    } else if (color !== this.color) {
      this.recolor(color);
    }
    this.tell();
    this.tellTools();
  };

  private readonly onTool = () => {
    if (this.disposed || !this.started) return;
    const { model } = this.options;
    // As in onRequest: a change of `drawing` in the same message may not have
    // been handled yet, and a first start reads the request itself.
    const { session, modes } = drawingOf(model.get("drawing"));
    if (session !== this.session || !modes.length) return;
    const value = model.get("draw_tool");
    const tool = toolOf(value);
    if (tool.session !== session || tool.seq <= this.toolSeq) return;
    this.toolSeq = tool.seq;
    if (isRecord(value)) consumedTools().set(value, tool.seq);
    if (!this.choose(tool.mode)) return;
    this.tell();
    this.tellTools();
  };

  private readonly onRequest = () => {
    if (this.disposed || !this.engine) return;
    const { model } = this.options;
    // A begin or an end writes `drawing` in the same message, and the order of
    // the change events is not fixed: that change starts the session, or ends
    // this one, and applies what it should.
    const { session, modes } = drawingOf(model.get("drawing"));
    if (session !== this.session || !modes.length) return;
    const request = requestOf(model.get("draw_request"));
    if (request.seq > this.applied) this.apply(request);
  };

  private readonly onStyleLoading = () => {
    // A full replacement: the adapter's sources and layers are already gone.
    this.ready = false;
    this.halt();
  };

  private readonly onStyleLoad = () => {
    this.ready = true;
    this.resume();
  };

  private readonly onStyleData = () => {
    if (this.ready) this.resume();
  };

  /** Start Terra Draw again where the style lost it, as after a diffed setStyle. */
  private resume(): void {
    if (this.disposed || this.quiet || this.failed) return;
    const { map } = this.options;
    if (this.engine && !ADAPTER_SOURCES.every((id) => map.getSource(id))) {
      this.halt();
    }
    if (!this.engine && this.wanted.modes.length) this.begin();
    this.tell();
    this.tellTools();
  }

  private tell(): void {
    const interactive = this.interactive();
    if (interactive === this.wasInteractive) return;
    this.wasInteractive = interactive;
    this.options.onInteractiveChange?.();
  }

  /** Start Terra Draw, then restore or apply, then enter the active mode. */
  private begin(): void {
    const { map, model, createDraw } = this.options;
    this.navigation = {
      dragPan: map.dragPan.isEnabled(),
      doubleClickZoom: map.doubleClickZoom.isEnabled(),
    };
    this.color = this.wanted.color;
    this.mode = STATIC;
    try {
      const engine = createDraw(modeSpecs(this.color));
      this.engine = engine;
      engine.on("finish", this.onFinish);
      engine.on("change", this.onChange);
      this.hush(() => engine.start());
    } catch (error) {
      console.error("mapframe: drawing could not start", error);
      this.failed = true;
      this.halt();
      return;
    }
    const request = requestOf(model.get("draw_request"));
    const firstStart = !this.started || this.wanted.session !== this.session;
    const newSession = this.started && firstStart;
    this.session = this.wanted.session;
    if (firstStart) this.takeTool();
    if (!this.started) {
      this.started = true;
      const drawn = drawnOf(model.get("drawn"));
      if (drawn.request_seq >= request.seq) {
        this.restore(drawn.features, drawn.request_seq);
      } else {
        this.apply(request);
      }
    } else {
      if (newSession) this.drop();
      if (request.seq > this.applied) {
        this.apply(request);
      } else {
        this.restore(this.committed, this.applied);
      }
    }
    this.switchTo(this.active);
  }

  /**
   * Take the session's tool request at a first start, unless a view of the
   * page did; `begin` enters it once the features are in.
   */
  private takeTool(): void {
    const value = this.options.model.get("draw_tool");
    const tool = toolOf(value);
    this.toolSeq = Math.max(this.toolSeq, tool.seq);
    if (!isRecord(value) || tool.session !== this.session) return;
    const consumed = consumedTools();
    if (tool.seq <= (consumed.get(value) ?? 0)) return;
    consumed.set(value, tool.seq);
    if (this.offers(tool.mode)) this.active = tool.mode;
  }

  private offers(mode: string): boolean {
    const { modes } = this.wanted;
    return modes.length > 0 && (mode === STATIC || modes.includes(mode));
  }

  /** Make `mode` the active tool if the session offers it. */
  private choose(mode: string): boolean {
    if (!this.offers(mode)) return false;
    this.active = mode;
    this.switchTo(mode);
    return true;
  }

  private tellTools(): void {
    const tools = this.tools();
    const key = JSON.stringify(tools);
    if (key === this.toldTools) return;
    this.toldTools = key;
    this.options.onToolsChange?.(tools.modes, tools.labels, tools.active);
  }

  /** Forget the committed features, as a session that ended does. */
  private drop(): void {
    this.committed = [];
    this.committedIds = new Set();
  }

  /**
   * Stop Terra Draw, its features kept. The active mode exits first, which
   * gives back double-click zoom and drag pan; both are then put back as they
   * were at the start, since a drag Terra Draw held never ends for it.
   */
  private halt(): void {
    const engine = this.engine;
    if (!engine) return;
    this.engine = null;
    this.hush(() => {
      try {
        engine.setMode(STATIC);
      } catch (error) {
        console.error("mapframe: drawing could not leave its mode", error);
      }
      try {
        engine.stop();
      } catch (error) {
        console.error("mapframe: drawing could not stop", error);
      }
    });
    engine.off("finish", this.onFinish);
    engine.off("change", this.onChange);
    this.mode = STATIC;
    const navigation = this.navigation;
    this.navigation = null;
    if (!navigation) return;
    const { dragPan, doubleClickZoom } = this.options.map;
    if (navigation.dragPan) dragPan.enable();
    else dragPan.disable();
    if (navigation.doubleClickZoom) doubleClickZoom.enable();
    else doubleClickZoom.disable();
  }

  private restore(features: DrawFeature[], seq: number): void {
    this.hush(() => this.add(features, seq));
    this.applied = seq;
    this.commit();
    this.lastSent = keyOf(this.committed);
  }

  /** Replace the features with a newer request's, and acknowledge it. */
  private apply(request: DrawRequestState): void {
    const engine = this.engine!;
    this.hush(() => {
      engine.clear();
      this.add(request.features, request.seq);
    });
    this.applied = request.seq;
    this.commit();
    this.report("request");
  }

  /**
   * Add the features of request `seq`, prepared, each one Terra Draw rejects
   * again under the mode its geometry implies, so an edited rectangle or
   * circle is never lost.
   */
  private add(features: DrawFeature[], seq: number): void {
    if (!features.length) return;
    const engine = this.engine!;
    const prepared = prepareFeatures(features, seq);
    const results = engine.addFeatures(prepared);
    const retry: DrawFeature[] = [];
    prepared.forEach((feature, i) => {
      if (results[i]?.valid) return;
      const mode = GEOMETRY_MODES[feature.geometry?.type];
      if (mode && mode !== feature.properties?.mode) {
        retry.push({ ...feature, properties: { ...feature.properties, mode } });
      } else {
        leftOut(feature, results[i]?.reason);
      }
    });
    if (!retry.length) return;
    engine.addFeatures(retry).forEach((result, i) => {
      if (!result.valid) leftOut(retry[i], result.reason);
    });
  }

  private switchTo(mode: string): void {
    const target = KNOWN.has(mode) ? mode : STATIC;
    // setMode stops the current mode even under the same name.
    if (!this.engine || target === this.mode) return;
    this.mode = target;
    this.hush(() => this.engine!.setMode(target));
  }

  /** New styles for every mode: a polygon being drawn keeps its points. */
  private recolor(color: string): void {
    const engine = this.engine!;
    this.color = color;
    for (const { name, options } of modeSpecs(color)) {
      this.hush(() =>
        engine.updateModeOptions(name, { styles: options.styles })
      );
    }
  }

  // A feature drawn, or an edit finished.
  private readonly onFinish = () => {
    if (!this.quiet && this.engine) this.userChanged();
  };

  // Deleting selection handles on deselect is no change of the features.
  private readonly onChange = (ids: unknown, type: unknown) => {
    this.rendered();
    if (
      this.quiet ||
      !this.engine ||
      type !== "delete" ||
      !Array.isArray(ids)
    ) {
      return;
    }
    if (ids.some((id) => this.committedIds.has(id))) this.userChanged();
  };

  private userChanged(): void {
    this.commit();
    if (keyOf(this.committed) !== this.lastSent) this.report("user");
  }

  private commit(): void {
    this.committed = snapshotOf(this.engine!.getSnapshot());
    this.committedIds = new Set(this.committed.map((f) => f.id));
  }

  private report(cause: DrawCause): void {
    const features = structuredClone(this.committed);
    this.lastSent = keyOf(features);
    this.transmit({
      type: "draw_report",
      view_id: this.options.viewId,
      side: this.options.side,
      request_seq: this.applied,
      cause,
      features,
    });
  }

  /**
   * A change the view makes, such as a mode or a colour, may fire no
   * `change`: tell what Terra Draw renders after it.
   */
  private hush(body: () => void): void {
    this.quiet += 1;
    try {
      body();
    } finally {
      this.quiet -= 1;
    }
    if (!this.quiet) this.rendered();
  }

  private rendered(): void {
    const { onRendered } = this.options;
    if (!onRendered) return;
    const engine = this.engine;
    onRendered(engine ? mirrorFeatures(engine.getSnapshot()) : [], this.color);
  }
}

function leftOut(feature: DrawFeature, reason: string | undefined): void {
  console.warn(
    `mapframe: drawing ${feature?.id} could not be shown: ${
      reason ?? "rejected"
    }`
  );
}

/**
 * Terra Draw's MapLibre adapter, made to survive a style that dropped its
 * sources and layers. Adapter 1.5.0 writes to its sources and removes them
 * unconditionally when it stops, which throws once a replaced style has none.
 */
class ViewAdapter extends TerraDrawMapLibreGLAdapter<MapLibreMap> {
  constructor(private readonly target: MapLibreMap) {
    super({
      map: target,
      prefixId: DRAW_PREFIX,
      coordinatePrecision: PRECISION,
    });
  }

  private intact(): boolean {
    const map = this.target;
    return (
      ADAPTER_SOURCES.every((id) => map.getSource(id)) &&
      ADAPTER_LAYERS.every((id) => map.getLayer(id))
    );
  }

  private removeOwn(): void {
    const map = this.target;
    for (const id of ADAPTER_LAYERS) if (map.getLayer(id)) map.removeLayer(id);
    for (const id of ADAPTER_SOURCES)
      if (map.getSource(id)) map.removeSource(id);
  }

  // A style MapLibre rebuilt from a snapshot, after a worker restart or a GPU
  // reset, still holds the sources and layers of the Terra Draw it stopped.
  override register(callbacks: TerraDrawExtend.TerraDrawCallbacks): void {
    this.removeOwn();
    super.register(callbacks);
  }

  override clear(): void {
    if (this.intact()) super.clear();
    else this._currentModeCallbacks?.onClear();
  }

  override unregister(): void {
    if (this.intact()) {
      super.unregister();
      return;
    }
    // The base adapter's teardown releases every listener and calls clear().
    TerraDrawExtend.TerraDrawBaseAdapter.prototype.unregister.call(this);
    // A new style that is still loading holds none of these.
    this.removeOwn();
  }
}

type ModeClass = new (
  options: any
) => TerraDrawExtend.TerraDrawBaseDrawMode<any>;

const MODE_CLASSES: Record<string, ModeClass> = {
  polygon: TerraDrawPolygonMode,
  rectangle: TerraDrawRectangleMode,
  circle: TerraDrawCircleMode,
  linestring: TerraDrawLineStringMode,
  point: TerraDrawPointMode,
  select: TerraDrawSelectMode,
};

/** A fresh Terra Draw on `map` for each start, with the bundled MapLibre adapter. */
export function terraDraw(map: MapLibreMap): ViewDrawOptions["createDraw"] {
  return (specs) =>
    new TerraDraw({
      adapter: new ViewAdapter(map),
      modes: specs.map(({ name, options }) => new MODE_CLASSES[name](options)),
      // No createdAt and updatedAt: an edit would change them on every select.
      tracked: false,
    }) as unknown as DrawEngine;
}
