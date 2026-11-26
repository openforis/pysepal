import { LINK, PLACE, REQUEST, type LinkMark } from "./view";

interface MoveEvent {
  [LINK]?: unknown;
  [PLACE]?: unknown;
  [REQUEST]?: unknown;
  /** Set by MapLibre on the moves of a user gesture. */
  originalEvent?: unknown;
}

/** What a link reads and moves of a MapLibre map. */
export interface LinkMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  jumpTo(options: object, eventData?: object): unknown;
  on(type: "move" | "moveend", listener: (event: MoveEvent) => void): unknown;
  off(type: "move" | "moveend", listener: (event: MoveEvent) => void): unknown;
}

/** The part of the anywidget model a link uses. */
export interface LinkModel {
  get(name: "_link"): unknown;
  on(name: "change:_link", callback: () => void): void;
  off(name: "change:_link", callback: () => void): void;
}

interface Member {
  /** The widget's `member` in `_link`, the same for all its views. */
  id: string;
  map: LinkMap;
}

/** The maps of the page by group id. */
export type LinkRegistry = Map<string, Set<Member>>;

// anywidget loads the bundle once per widget, so a module-level map would
// hold one widget's views only.
const KEY = Symbol.for("mapframe.links");

export function pageRegistry(): LinkRegistry {
  const scope = globalThis as { [KEY]?: LinkRegistry };
  return (scope[KEY] ??= new Map());
}

export interface ViewLinkOptions {
  map: LinkMap;
  model: LinkModel;
  registry: LinkRegistry;
}

interface Link {
  group: string;
  /** The widget's request seq at link time. */
  seq: number;
  /** The widget's id, the same in every group. */
  member: string;
}

/** The `_link` trait, else no group. */
function linkOf(value: unknown): Link {
  const { group, seq, member } = (
    value && typeof value === "object" ? value : {}
  ) as { group?: unknown; seq?: unknown; member?: unknown };
  return typeof group === "string" &&
    group &&
    Number.isInteger(seq) &&
    typeof member === "string" &&
    member
    ? { group, seq: seq as number, member }
    : { group: "", seq: 0, member: "" };
}

type Camera = [lng: number, lat: number, zoom: number];

function cameraOf(map: LinkMap): Camera {
  const { lng, lat } = map.getCenter();
  return [lng, lat, map.getZoom()];
}

const sameCamera = (a: Camera, b: Camera): boolean =>
  a[0] === b[0] && a[1] === b[1] && a[2] === b[2];

/**
 * Keeps a view's map on the camera of the other widgets in its group.
 *
 * Python names the group in `_link`; the views of the page that share it
 * find each other here. Each move that changes a map's camera jumps the
 * others to its center and zoom in the same call, marked `frame`, which
 * their cameras do not report. As that movement ends, the others jump once
 * more, marked `user` when a user made it and `link` otherwise, so each
 * reports it once, as the map that moved does. A move that leaves the
 * camera where it was, such as a resize, moves nobody. A jump that carries
 * `LINK` is never passed on, and views of one widget never move each other.
 *
 * A request not newer than the link is one the group's camera already
 * answers, such as a fit that waited for a size, so while a peer is shown
 * the map takes the peer's camera back instead.
 */
export class ViewLink {
  private group = "";
  /** This view in the group it joined. */
  private member: Member | null = null;
  private started = false;
  private disposed = false;
  /** The camera this map last pushed or took. */
  private last: Camera = [NaN, NaN, NaN];
  /** Whether the movement under way pushed a frame. */
  private pushed = false;
  /** Whether the movement under way applies a request not newer than the link. */
  private stale = false;

  constructor(private readonly options: ViewLinkOptions) {}

  /**
   * Join the group named now. A view that joins takes the camera of the
   * group's other maps, unless `moved`, the seq of the request that moved it
   * on mount, is newer than the link: that request moves them instead.
   */
  start(moved: number | null = null): void {
    const { map, model } = this.options;
    this.started = true;
    this.last = cameraOf(map);
    map.on("move", this.onMove);
    map.on("moveend", this.onMoveEnd);
    model.on("change:_link", this.onChange);
    this.join(moved);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.started) {
      const { map, model } = this.options;
      map.off("move", this.onMove);
      map.off("moveend", this.onMoveEnd);
      model.off("change:_link", this.onChange);
    }
    this.leave();
  }

  private readonly onChange = () => {
    if (!this.disposed) this.join(null);
  };

  private join(moved: number | null): void {
    const link = linkOf(this.options.model.get("_link"));
    const { group, seq } = link;
    if (group === this.group) return;
    this.leave();
    if (!group) return;
    const { registry, map } = this.options;
    const peer = this.peers(link)[0];
    let members = registry.get(group);
    if (!members) registry.set(group, (members = new Set()));
    this.member = { id: link.member, map };
    members.add(this.member);
    this.group = group;
    if (!peer) return;
    if (moved !== null && moved > seq) this.push("link");
    else jump(map, peer.map, "link");
  }

  private leave(): void {
    const { registry } = this.options;
    const members = registry.get(this.group);
    if (this.member) members?.delete(this.member);
    if (members?.size === 0) registry.delete(this.group);
    this.group = "";
    this.member = null;
  }

  /**
   * The maps of the group `link` names but those of this widget. anywidget
   * gives each view its own model object, so the widget is told by the
   * `member` Python writes, not by the model.
   */
  private peers({ group, member }: Link): Member[] {
    const members = this.options.registry.get(group) ?? [];
    return [...members].filter((m) => m.id !== member);
  }

  /**
   * The peers of the group `_link` names now. A request and the link it
   * came with change in one message, their events in either order, so a
   * move reads the link itself rather than the group this view has joined.
   */
  private linked(): { peers: Member[]; seq: number } {
    const link = linkOf(this.options.model.get("_link"));
    return { peers: this.peers(link), seq: link.seq };
  }

  private readonly onMove = (event: MoveEvent) => {
    const { map } = this.options;
    // A peer's jump, or this map keeping its place while its insets change.
    if (event[LINK] !== undefined || event[PLACE] !== undefined) {
      this.last = cameraOf(map);
      return;
    }
    if (this.isStale(event)) {
      this.stale = true;
      return;
    }
    if (sameCamera(cameraOf(map), this.last)) return;
    this.pushed = true;
    this.push("frame");
  };

  private readonly onMoveEnd = (event: MoveEvent) => {
    if (event[LINK] !== undefined || event[PLACE] !== undefined) return;
    const { pushed, stale } = this;
    this.pushed = this.stale = false;
    if (stale) {
      // Here and not in the move, so that no jump runs inside a move listener.
      const [peer] = this.linked().peers;
      if (peer) jump(this.options.map, peer.map, "link");
    } else if (pushed) {
      this.push(event.originalEvent ? "user" : "link");
    }
  };

  private isStale(event: MoveEvent): boolean {
    const request = event[REQUEST];
    if (!Number.isInteger(request)) return false;
    const { peers, seq } = this.linked();
    return (request as number) <= seq && peers.length > 0;
  }

  private push(mark: LinkMark): void {
    const { map } = this.options;
    this.last = cameraOf(map);
    for (const peer of this.linked().peers) jump(peer.map, map, mark);
  }
}

/** Move `map` to the center and zoom of `to`. */
function jump(map: LinkMap, to: LinkMap, mark: LinkMark): void {
  const { lng, lat } = to.getCenter();
  try {
    map.jumpTo({ center: [lng, lat], zoom: to.getZoom() }, { [LINK]: mark });
  } catch (error) {
    // A map being removed; the others still follow.
    console.error("mapframe: a linked map could not follow", error);
  }
}
