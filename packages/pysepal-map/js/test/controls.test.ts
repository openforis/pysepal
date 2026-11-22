import { LngLat, ScaleControl } from "maplibre-gl";
import type { IControl, Map as MapLibreMap } from "maplibre-gl";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ViewControls } from "../controls";
import type { MapState } from "../types";
import type { Insets } from "../view";

type Listener = (event: any) => void;

/** Just enough of a DOM element for MapLibre's controls and ours. */
class FakeElement {
  className = "";
  title = "";
  type = "";
  textContent = "";
  disabled = false;
  parentElement: FakeElement | null = null;
  readonly children: FakeElement[] = [];
  readonly style: Record<string, string> = {};
  readonly attributes = new Map<string, string>();
  requestFullscreen?: () => void;
  private readonly listeners = new Map<string, Set<Listener>>();

  readonly classList = {
    contains: (token: string) => this.tokens().includes(token),
    add: (token: string) => this.classList.toggle(token, true),
    remove: (token: string) => this.classList.toggle(token, false),
    toggle: (token: string, force?: boolean) => {
      const on = force ?? !this.classList.contains(token);
      const rest = this.tokens().filter((t) => t !== token);
      this.className = (on ? [...rest, token] : rest).join(" ");
      return on;
    },
  };

  private tokens(): string[] {
    return this.className.split(" ").filter(Boolean);
  }

  setAttribute(name: string, value: string) {
    this.attributes.set(name, String(value));
  }

  hasAttribute(name: string) {
    return this.attributes.has(name);
  }

  removeAttribute(name: string) {
    this.attributes.delete(name);
  }

  appendChild(child: FakeElement) {
    child.remove();
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  insertBefore(child: FakeElement, _before: FakeElement | null) {
    return this.appendChild(child);
  }

  remove() {
    const siblings = this.parentElement?.children;
    if (siblings) siblings.splice(siblings.indexOf(this), 1);
    this.parentElement = null;
  }

  addEventListener(type: string, listener: Listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: Listener) {
    this.listeners.get(type)?.delete(listener);
  }

  click() {
    for (const listener of [...(this.listeners.get("click") ?? [])]) {
      listener({ type: "click" });
    }
  }

  /** Only `[attribute]` selectors. */
  closest(selector: string): FakeElement | null {
    const name = /^\[([\w-]+)\]$/.exec(selector)![1];
    let el: FakeElement | null = this;
    while (el && !el.hasAttribute(name)) el = el.parentElement;
    return el;
  }

  /** Only `.class` selectors. */
  querySelector(selector: string): FakeElement | null {
    const token = /^\.([\w-]+)$/.exec(selector)![1];
    for (const child of this.children) {
      if (child.classList.contains(token)) return child;
      const found = child.querySelector(selector);
      if (found) return found;
    }
    return null;
  }
}

/**
 * A document with the Fullscreen API, or without it, where MapLibre falls
 * back to its pseudo-fullscreen class.
 */
function fakeDocument(api: boolean) {
  const listeners = new Map<string, Set<Listener>>();
  const fire = (type: string) => {
    for (const listener of [...(listeners.get(type) ?? [])]) listener({ type });
  };
  const doc: Record<string, any> = {
    fullscreenElement: null as FakeElement | null,
    createElement: () => new FakeElement(),
    addEventListener(type: string, listener: Listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(listener);
    },
    removeEventListener(type: string, listener: Listener) {
      listeners.get(type)?.delete(listener);
    },
    /** A new element, which can go fullscreen if the API is there. */
    element(): FakeElement {
      const el = new FakeElement();
      if (api) {
        el.requestFullscreen = () => {
          doc.fullscreenElement = el;
          fire("fullscreenchange");
        };
      }
      return el;
    },
  };
  if (api) {
    doc.onfullscreenchange = null;
    doc.exitFullscreen = () => {
      doc.fullscreenElement = null;
      fire("fullscreenchange");
    };
  }
  return doc;
}

const POSITIONS = ["top-left", "top-right", "bottom-left", "bottom-right"];

/** A map that adds and removes controls as MapLibre does, in its corners. */
class FakeControlMap {
  readonly placed: { control: IControl; position: string }[] = [];
  readonly cooperativeGestures = {
    isEnabled: () => false,
    enable: () => {},
    disable: () => {},
  };
  readonly _camera = { renderedState: { width: 400, height: 300 } };
  resizes = 0;

  constructor(private readonly container: FakeElement) {
    const corners = new FakeElement();
    corners.className = "maplibregl-control-container";
    container.appendChild(corners);
    for (const position of POSITIONS) {
      const corner = new FakeElement();
      corner.className = `maplibregl-ctrl-${position}`;
      corners.appendChild(corner);
    }
  }

  corner(position: string): FakeElement {
    return this.container.querySelector(`.maplibregl-ctrl-${position}`)!;
  }

  at(position: string): IControl[] {
    return this.placed
      .filter((p) => p.position === position)
      .map((p) => p.control);
  }

  addControl(control: IControl, position: string) {
    const el = control.onAdd(this as unknown as MapLibreMap);
    this.corner(position).appendChild(el as unknown as FakeElement);
    this.placed.push({ control, position });
  }

  removeControl(control: IControl) {
    control.onRemove(this as unknown as MapLibreMap);
    this.placed.splice(
      this.placed.findIndex((p) => p.control === control),
      1
    );
  }

  getContainer() {
    return this.container;
  }

  resize() {
    this.resizes++;
  }

  _getUIString(key: string) {
    return key;
  }

  on() {}

  off() {}

  getZoom() {
    return 2;
  }

  getMaxZoom() {
    return 24;
  }

  getMinZoom() {
    return 0;
  }

  // What the scale control measures: one degree per 100 px.
  unproject([x]: [number, number]) {
    return new LngLat(x / 100, 0);
  }

  project(lngLat: LngLat) {
    return { x: lngLat.lng * 100, y: 0 };
  }
}

const NO_INSETS: Insets = { left: 0, right: 0, top: 0, bottom: 0 };
const INSETS: Insets = { left: 300, right: 20, top: 10, bottom: 40 };

function state(controls: Partial<MapState["controls"]> = {}): MapState {
  return {
    revision: 1,
    theme: "light",
    compare: false,
    controls: {
      zoom: true,
      fullscreen: true,
      scale: true,
      coordinates: false,
      ...controls,
    },
    basemap: null,
    layers: [],
  };
}

function setup({ api = true } = {}) {
  const doc = fakeDocument(api);
  vi.stubGlobal("document", doc);
  vi.stubGlobal("window", { document: doc });
  const root: FakeElement = doc.element();
  const map = new FakeControlMap(root);
  const told: Insets[] = [];
  const controls = new ViewControls({
    map: map as unknown as MapLibreMap,
    root: root as unknown as HTMLElement,
    onInsets: (insets) => told.push(insets),
  });
  const button = () =>
    root.querySelector(".maplibregl-ctrl-fullscreen") ??
    root.querySelector(".maplibregl-ctrl-shrink")!;
  return { doc, root, map, controls, told, button };
}

/** Where each corner sits, from the sides it is placed from. */
function corners(map: FakeControlMap) {
  return Object.fromEntries(
    POSITIONS.map((p) => [p, { ...map.corner(p).style }])
  );
}

const placedAt = ({ left, right, top, bottom }: Insets) => ({
  "top-left": { top: `${top}px`, left: `${left}px` },
  "top-right": { top: `${top}px`, right: `${right}px` },
  "bottom-left": { bottom: `${bottom}px`, left: `${left}px` },
  "bottom-right": { bottom: `${bottom}px`, right: `${right}px` },
});

const MODES = [
  ["the Fullscreen API", true],
  ["the pseudo-fullscreen fallback", false],
] as const;

describe("ViewControls", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("adds a metric scale control bottom-left when scale is true, and removes it when false", () => {
    const { map, controls } = setup();
    controls.sync(state());
    const [scale, ...others] = map.at("bottom-left");
    expect(scale).toBeInstanceOf(ScaleControl);
    expect((scale as ScaleControl).options.unit).toBe("metric");
    expect(others).toEqual([]);
    expect(map.corner("bottom-left").children).toHaveLength(1);

    controls.sync(state({ scale: false }));
    expect(map.at("bottom-left")).toEqual([]);
    expect(map.corner("bottom-left").children).toHaveLength(0);
    controls.sync(state({ scale: true, coordinates: false }));
    expect(map.at("bottom-left")).toHaveLength(1);
  });

  it("keeps the zoom and fullscreen controls top-left", () => {
    const { map, controls } = setup();
    controls.sync(state());
    expect(map.at("top-left")).toHaveLength(2);
    controls.sync(state({ zoom: false, fullscreen: false }));
    expect(map.placed.map((p) => p.position)).toEqual(["bottom-left"]);
  });

  it("offsets the control corners by the insets", () => {
    const { map, controls, told } = setup();
    controls.setInsets(INSETS);
    expect(corners(map)).toEqual(placedAt(INSETS));
    expect(told).toEqual([INSETS]);
    controls.setInsets(NO_INSETS);
    expect(corners(map)).toEqual(placedAt(NO_INSETS));
  });

  it.each(MODES)("fullscreen targets the marked ancestor with %s", (_, api) => {
    const { doc, root, controls, button } = setup({ api });
    controls.sync(state());
    // The view joins the page after its controls were added.
    const ancestor: FakeElement = doc.element();
    ancestor.setAttribute("data-psm-fullscreen-root", "");
    const between: FakeElement = doc.element();
    ancestor.appendChild(between);
    between.appendChild(root);

    button().click();
    if (api) {
      expect(doc.fullscreenElement).toBe(ancestor);
    } else {
      expect(ancestor.classList.contains("maplibregl-pseudo-fullscreen")).toBe(
        true
      );
    }
    expect(ancestor.hasAttribute("data-psm-fullscreen")).toBe(true);
    expect(root.hasAttribute("data-psm-fullscreen")).toBe(false);
  });

  it.each(MODES)(
    "fullscreen targets the map element without a marked ancestor, with %s",
    (_, api) => {
      const { doc, root, controls, button } = setup({ api });
      controls.sync(state());
      doc.element().appendChild(root);
      button().click();
      if (api) {
        expect(doc.fullscreenElement).toBe(root);
      } else {
        expect(root.classList.contains("maplibregl-pseudo-fullscreen")).toBe(
          true
        );
      }
      expect(root.hasAttribute("data-psm-fullscreen")).toBe(true);
    }
  );

  it.each(MODES)(
    "fullscreen uses zero insets and restores them, with %s",
    (_, api) => {
      const { root, map, controls, told, button } = setup({ api });
      controls.setInsets(INSETS);
      controls.sync(state());
      told.length = 0;

      button().click();
      expect(told).toEqual([NO_INSETS]);
      expect(corners(map)).toEqual(placedAt(NO_INSETS));
      expect(root.hasAttribute("data-psm-fullscreen")).toBe(true);

      // Insets declared meanwhile wait for the exit.
      const later = { ...INSETS, left: 100 };
      controls.setInsets(later);
      expect(corners(map)).toEqual(placedAt(NO_INSETS));

      button().click();
      expect(told.at(-1)).toEqual(later);
      expect(corners(map)).toEqual(placedAt(later));
      expect(root.hasAttribute("data-psm-fullscreen")).toBe(false);
      if (!api) {
        expect(root.classList.contains("maplibregl-pseudo-fullscreen")).toBe(
          false
        );
      }
    }
  );

  it.each(MODES)(
    "leaves fullscreen when its control is removed while fullscreen, with %s",
    (_, api) => {
      const { root, map, controls, told, button } = setup({ api });
      controls.setInsets(INSETS);
      controls.sync(state());
      button().click();
      expect(root.hasAttribute("data-psm-fullscreen")).toBe(true);

      // MapLibre drops its listener on removal: no fullscreenend follows.
      controls.sync(state({ fullscreen: false }));
      expect(root.hasAttribute("data-psm-fullscreen")).toBe(false);
      expect(told.at(-1)).toEqual(INSETS);
      expect(corners(map)).toEqual(placedAt(INSETS));
    }
  );

  it.each(MODES)(
    "leaves fullscreen when the view is disposed while fullscreen, with %s",
    (_, api) => {
      const { doc, root, controls, told, button } = setup({ api });
      const ancestor: FakeElement = doc.element();
      ancestor.setAttribute("data-psm-fullscreen-root", "");
      ancestor.appendChild(root);
      controls.setInsets(INSETS);
      controls.sync(state());
      button().click();
      expect(ancestor.hasAttribute("data-psm-fullscreen")).toBe(true);

      controls.dispose();
      expect(ancestor.hasAttribute("data-psm-fullscreen")).toBe(false);
      expect(told.at(-1)).toEqual(INSETS);
    }
  );

  it("toggles the dark theme class", () => {
    const { root, controls } = setup();
    controls.sync({ ...state(), theme: "dark" });
    expect(root.classList.contains("psm-dark")).toBe(true);
    controls.sync(state());
    expect(root.classList.contains("psm-dark")).toBe(false);
  });
});
