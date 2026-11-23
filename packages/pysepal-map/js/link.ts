import { LINK } from "./view";

interface MoveEvent {
  [LINK]?: unknown;
  /** Set by MapLibre on the moves of a user gesture. */
  originalEvent?: unknown;
}

/** What a link reads and moves of a MapLibre map. */
export interface LinkMap {
  getCenter(): { lng: number; lat: number };
  getZoom(): number;
  jumpTo(options: object, eventData?: object): unknown;
  on(type: "move", listener: (event: MoveEvent) => void): unknown;
  off(type: "move", listener: (event: MoveEvent) => void): unknown;
}

/** The part of the anywidget model a link uses. */
export interface LinkModel {
  get(name: "_link"): unknown;
  on(name: "change:_link", callback: () => void): void;
  off(name: "change:_link", callback: () => void): void;
}

interface Member {
  model: object;
  map: LinkMap;
}

/** The maps of the page by group id. */
export type LinkRegistry = Map<string, Set<Member>>;

// anywidget loads the bundle once per widget, so a module-level map would
// hold one widget's views only.
const KEY = Symbol.for("pysepal-map.links");

export function pageRegistry(): LinkRegistry {
  const scope = globalThis as { [KEY]?: LinkRegistry };
  return (scope[KEY] ??= new Map());
}

export interface ViewLinkOptions {
  map: LinkMap;
  model: LinkModel;
  registry: LinkRegistry;
}

/** The `_link` trait: the group, and the widget's request seq at link time. */
function linkOf(value: unknown): { group: string; seq: number } {
  const { group, seq } = (value && typeof value === "object" ? value : {}) as {
    group?: unknown;
    seq?: unknown;
  };
  return typeof group === "string" && group && Number.isInteger(seq)
    ? { group, seq: seq as number }
    : { group: "", seq: 0 };
}

/**
 * Keeps a view's map on the camera of the other widgets in its group.
 *
 * Python names the group in `_link`; the views of the page that share it
 * find each other here, so every move of one map jumps the others to its
 * center and zoom in the same frame. A jump carries `LINK`, so the maps it
 * moves do not pass it on. Views of one widget never move each other.
 */
export class ViewLink {
  private group = "";
  private readonly member: Member;
  private started = false;
  private disposed = false;

  constructor(private readonly options: ViewLinkOptions) {
    this.member = { model: options.model, map: options.map };
  }

  /**
   * Join the group named now. A view that joins takes the camera of the
   * group's other maps, unless `moved`, the seq of the request that moved it
   * on mount, is newer than the link: that request moves them instead.
   */
  start(moved: number | null = null): void {
    this.started = true;
    this.options.map.on("move", this.onMove);
    this.options.model.on("change:_link", this.onChange);
    this.join(moved);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    if (this.started) {
      this.options.map.off("move", this.onMove);
      this.options.model.off("change:_link", this.onChange);
    }
    this.leave();
  }

  private readonly onChange = () => {
    if (!this.disposed) this.join(null);
  };

  private join(moved: number | null): void {
    const { group, seq } = linkOf(this.options.model.get("_link"));
    if (group === this.group) return;
    this.leave();
    if (!group) return;
    const { registry, map } = this.options;
    let members = registry.get(group);
    if (!members) registry.set(group, (members = new Set()));
    const peer = this.peers(members)[0];
    members.add(this.member);
    this.group = group;
    if (!peer) return;
    if (moved !== null && moved > seq) this.push("other");
    else jump(map, peer.map, "other");
  }

  private leave(): void {
    const { registry } = this.options;
    const members = registry.get(this.group);
    members?.delete(this.member);
    if (members?.size === 0) registry.delete(this.group);
    this.group = "";
  }

  private peers(members: Set<Member>): Member[] {
    return [...members].filter((m) => m.model !== this.options.model);
  }

  private readonly onMove = (event: MoveEvent) => {
    if (event[LINK] !== undefined || !this.group) return;
    this.push(event.originalEvent ? "user" : "other");
  };

  private push(cause: "user" | "other"): void {
    const members = this.options.registry.get(this.group);
    if (!members) return;
    for (const peer of this.peers(members)) {
      jump(peer.map, this.options.map, cause);
    }
  }
}

/** Move `map` to the center and zoom of `to`. */
function jump(map: LinkMap, to: LinkMap, cause: "user" | "other"): void {
  const { lng, lat } = to.getCenter();
  try {
    map.jumpTo({ center: [lng, lat], zoom: to.getZoom() }, { [LINK]: cause });
  } catch (error) {
    // A map being removed; the others still follow.
    console.error("pysepal-map: a linked map could not follow", error);
  }
}
