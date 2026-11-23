import { AttributionControl, LngLat, ScaleControl } from "maplibre-gl";
import type { IControl, Map as MapLibreMap } from "maplibre-gl";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ViewControls } from "../controls";
import type { LayerSide, LayerState, MapState } from "../types";
import type { Insets } from "../view";

type Listener = (event: any) => void;

/** An inline style: properties as fields, custom properties through the methods. */
class FakeStyle {
  [name: string]: unknown;

  setProperty(name: string, value: string) {
    this[name] = value;
  }

  removeProperty(name: string) {
    delete this[name];
  }

  getPropertyValue(name: string): string {
    return (this[name] as string | undefined) ?? "";
  }
}

/** Just enough of a DOM element for MapLibre's controls and ours. */
class FakeElement {
  className = "";
  title = "";
  type = "";
  textContent = "";
  disabled = false;
  offsetHeight = 0;
  parentElement: FakeElement | null = null;
  readonly children: FakeElement[] = [];
  readonly style = new FakeStyle();
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

  getAttribute(name: string): string | null {
    return this.attributes.get(name) ?? null;
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

  getCanvasContainer() {
    return { offsetWidth: 400 };
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

/** A view; a second one on the same page passes the first one's `doc`. */
function setup({
  api = true,
  doc = fakeDocument(api),
  viewId = "view-1",
} = {}) {
  vi.stubGlobal("document", doc);
  vi.stubGlobal("window", { document: doc });
  const root: FakeElement = doc.element();
  const map = new FakeControlMap(root);
  const told: Insets[] = [];
  const observer = {
    elements: [] as FakeElement[],
    callback: () => {},
    stopped: false,
  };
  const controls = new ViewControls({
    map: map as unknown as MapLibreMap,
    root: root as unknown as HTMLElement,
    viewId,
    onInsets: (insets) => told.push(insets),
    observeSize: (elements, callback) => {
      observer.elements = elements as unknown as FakeElement[];
      observer.callback = callback;
      return () => {
        observer.stopped = true;
      };
    },
  });
  const button = () =>
    root.querySelector(".maplibregl-ctrl-fullscreen") ??
    root.querySelector(".maplibregl-ctrl-shrink")!;
  /** What the observer calls when a corner changes size. */
  const measure = () => observer.callback();
  return { doc, root, map, controls, told, button, observer, measure };
}

/** Puts `el` inside a new element marked as the fullscreen root. */
function inFullscreenRoot(
  doc: ReturnType<typeof fakeDocument>,
  el: FakeElement
) {
  const ancestor: FakeElement = doc.element();
  ancestor.setAttribute("data-psm-fullscreen-root", "");
  const between: FakeElement = doc.element();
  ancestor.appendChild(between);
  between.appendChild(el);
  return ancestor;
}

/** Gives each corner of `map` a height. */
function setHeights(map: FakeControlMap, heights: Record<string, number>) {
  for (const position of POSITIONS) {
    map.corner(position).offsetHeight = heights[position];
  }
}

const HEIGHTS = {
  "top-left": 107,
  "top-right": 0,
  "bottom-left": 28,
  "bottom-right": 34,
};

/** The corner variables `el` carries inline. */
function published(el: FakeElement): Record<string, string> {
  const found: Record<string, string> = {};
  for (const position of POSITIONS) {
    const value = el.style.getPropertyValue(`--psm-controls-${position}`);
    if (value) found[position] = value;
  }
  return found;
}

const inPx = (heights: Record<string, number>) =>
  Object.fromEntries(Object.entries(heights).map(([p, h]) => [p, `${h}px`]));

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

/** MapLibre's own attribution link, which its default control shows. */
const MAPLIBRE = '<a href="https://maplibre.org/" target="_blank">MapLibre</a>';

/** Just what the attribution reads of a layer. */
const sided = (
  id: string,
  side: LayerSide,
  attribution: string,
  visible = true
) => ({ id, side, attribution, visible } as unknown as LayerState);

const attribution = (map: FakeControlMap) => {
  const [control, ...others] = map.at("bottom-right");
  expect(others).toEqual([]);
  expect(control).toBeInstanceOf(AttributionControl);
  return control as AttributionControl;
};

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
    expect(map.placed.map((p) => p.position)).toEqual([
      "bottom-left",
      "bottom-right",
    ]);
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

  it("publishes each corner's height on the fullscreen root", () => {
    const { doc, root, map, controls, observer, measure } = setup();
    controls.sync(state());
    expect(observer.elements).toEqual(POSITIONS.map((p) => map.corner(p)));
    const ancestor = inFullscreenRoot(doc, root);
    setHeights(map, HEIGHTS);

    measure();
    expect(published(ancestor)).toEqual(inPx(HEIGHTS));
    expect(published(root)).toEqual({});
  });

  it("falls back to the map root without a marked ancestor", () => {
    const { doc, root, map, measure } = setup();
    doc.element().appendChild(root);
    setHeights(map, HEIGHTS);
    measure();
    expect(published(root)).toEqual(inPx(HEIGHTS));
    expect(root.getAttribute("data-psm-controls")).toBe("view-1");

    // The view joined a marked root since: the next measure moves both there.
    const ancestor = inFullscreenRoot(doc, root);
    measure();
    expect(published(ancestor)).toEqual(inPx(HEIGHTS));
    expect(ancestor.getAttribute("data-psm-controls")).toBe("view-1");
    expect(published(root)).toEqual({});
    expect(root.hasAttribute("data-psm-controls")).toBe(false);
  });

  it("sets the variables on every measure", () => {
    const { doc, root, map, measure } = setup();
    const ancestor = inFullscreenRoot(doc, root);
    setHeights(map, HEIGHTS);
    measure();

    ancestor.style.removeProperty("--psm-controls-top-left");
    measure();
    expect(published(ancestor)).toEqual(inPx(HEIGHTS));

    const taller = { ...HEIGHTS, "top-left": 223 };
    setHeights(map, taller);
    measure();
    expect(published(ancestor)).toEqual(inPx(taller));
  });

  it("marks the target with its view id in data-psm-controls", () => {
    const { doc, root, measure } = setup({ viewId: "view-7" });
    const ancestor = inFullscreenRoot(doc, root);
    expect(ancestor.hasAttribute("data-psm-controls")).toBe(false);
    measure();
    expect(ancestor.getAttribute("data-psm-controls")).toBe("view-7");
    expect(root.hasAttribute("data-psm-controls")).toBe(false);
  });

  it("removes the variables and the mark on dispose", () => {
    const { doc, root, map, controls, observer, measure } = setup();
    const ancestor = inFullscreenRoot(doc, root);
    setHeights(map, HEIGHTS);
    measure();

    controls.dispose();
    expect(observer.stopped).toBe(true);
    expect(published(ancestor)).toEqual({});
    expect(ancestor.hasAttribute("data-psm-controls")).toBe(false);
  });

  it("dispose leaves a newer view's variables and mark", () => {
    const first = setup({ viewId: "view-1" });
    const ancestor = inFullscreenRoot(first.doc, first.root);
    const second = setup({ doc: first.doc, viewId: "view-2" });
    ancestor.appendChild(second.root);
    const later = { ...HEIGHTS, "top-left": 223 };
    setHeights(first.map, HEIGHTS);
    setHeights(second.map, later);

    first.measure();
    second.measure();
    first.controls.dispose();
    expect(ancestor.getAttribute("data-psm-controls")).toBe("view-2");
    expect(published(ancestor)).toEqual(inPx(later));

    second.controls.dispose();
    expect(published(ancestor)).toEqual({});
    expect(ancestor.hasAttribute("data-psm-controls")).toBe(false);
  });

  it("adds the attribution control MapLibre's default would be", () => {
    const { map, controls } = setup();
    controls.sync(state());
    expect(attribution(map).options).toEqual({
      compact: true,
      customAttribution: [MAPLIBRE],
    });
    expect(map.corner("bottom-right").children).toHaveLength(1);
  });

  it("adds the attributions only the right map shows while compare is on", () => {
    const layers = [
      sided("l", "left", "L-attr"),
      sided("b", "both", "B-attr"),
      sided("r", "right", "R-attr"),
      sided("r2", "right", "R-attr"),
      sided("hidden", "right", "H-attr", false),
      sided("bare", "right", ""),
    ];
    const { map, controls } = setup();
    controls.sync({ ...state(), layers });
    const off = attribution(map);
    expect(off.options.customAttribution).toEqual([MAPLIBRE]);

    controls.sync({ ...state(), compare: true, layers });
    const on = attribution(map);
    expect(on).not.toBe(off);
    expect(on.options).toEqual({
      compact: true,
      customAttribution: [MAPLIBRE, "R-attr"],
    });
    expect(map.corner("bottom-right").children).toHaveLength(1);

    // The same text keeps the control.
    controls.sync({
      ...state(),
      compare: true,
      layers: [...layers, sided("l2", "left", "L2-attr")],
    });
    expect(attribution(map)).toBe(on);

    controls.sync({ ...state(), layers });
    const again = attribution(map);
    expect(again).not.toBe(on);
    expect(again.options.customAttribution).toEqual([MAPLIBRE]);
    expect(map.corner("bottom-right").children).toHaveLength(1);
  });

  it("toggles the dark theme class", () => {
    const { root, controls } = setup();
    controls.sync({ ...state(), theme: "dark" });
    expect(root.classList.contains("psm-dark")).toBe(true);
    controls.sync(state());
    expect(root.classList.contains("psm-dark")).toBe(false);
  });
});
