import { describe, expect, it } from "vitest";

import { faCircle } from "@fortawesome/free-regular-svg-icons/faCircle";
import { faSquare } from "@fortawesome/free-regular-svg-icons/faSquare";
import { faArrowPointer } from "@fortawesome/free-solid-svg-icons/faArrowPointer";
import { faBezierCurve } from "@fortawesome/free-solid-svg-icons/faBezierCurve";
import { faDrawPolygon } from "@fortawesome/free-solid-svg-icons/faDrawPolygon";
import { faLocationDot } from "@fortawesome/free-solid-svg-icons/faLocationDot";
import { faTrash } from "@fortawesome/free-solid-svg-icons/faTrash";

import { DrawToolbar } from "../toolbar";

const SVG = "http://www.w3.org/2000/svg";

/** The part of an element the toolbar uses, which records what it was given. */
class FakeElement {
  className = "";
  title = "";
  type = "";
  children: FakeElement[] = [];
  removed = false;
  private readonly attributes = new Map<string, string>();
  private readonly listeners = new Map<string, (() => void)[]>();
  constructor(readonly tagName: string, readonly namespace: string | null) {}
  setAttribute(name: string, value: string) {
    this.attributes.set(name, String(value));
  }
  getAttribute(name: string) {
    return this.attributes.get(name) ?? null;
  }
  append(...nodes: FakeElement[]) {
    this.children.push(...nodes);
  }
  replaceChildren(...nodes: FakeElement[]) {
    this.children = [...nodes];
  }
  addEventListener(type: string, listener: () => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  remove() {
    this.removed = true;
  }
  click() {
    for (const listener of this.listeners.get("click") ?? []) listener();
  }
}

const doc = {
  createElement: (tag: string) => new FakeElement(tag, null),
  createElementNS: (namespace: string, tag: string) =>
    new FakeElement(tag, namespace),
} as unknown as Document;

const MODES = [
  "polygon",
  "rectangle",
  "circle",
  "linestring",
  "point",
  "select",
];
const LABELS: Record<string, string> = {
  polygon: "Draw a polygon",
  rectangle: "Draw a rectangle",
  circle: "Draw a circle",
  linestring: "Draw a line",
  point: "Draw a point",
  select: "Select and edit shapes",
  clear: "Remove all shapes",
};
const ICONS = [
  faDrawPolygon,
  faSquare,
  faCircle,
  faBezierCurve,
  faLocationDot,
  faArrowPointer,
  faTrash,
];

function setup() {
  const selected: string[] = [];
  let cleared = 0;
  const toolbar: DrawToolbar = new DrawToolbar({
    // As the view does: it takes the mode, then tells the toolbar.
    onSelect: (mode) => {
      selected.push(mode);
      toolbar.sync(MODES, LABELS, mode);
    },
    onClear: () => (cleared += 1),
    doc,
  });
  const el = toolbar.onAdd() as unknown as FakeElement;
  const button = (mode: string) =>
    el.children.find((b) => b.getAttribute("data-mode") === mode)!;
  const pressed = () =>
    el.children
      .filter((b) => b.getAttribute("aria-pressed") === "true")
      .map((b) => b.getAttribute("data-mode"));
  return {
    toolbar,
    el,
    selected,
    cleared: () => cleared,
    button,
    pressed,
  };
}

describe("DrawToolbar", () => {
  it("renders a button per mode in order and a clear button", () => {
    const { toolbar, el, button, pressed } = setup();
    toolbar.sync(MODES, LABELS, "circle");
    expect(el.className).toBe(
      "maplibregl-ctrl maplibregl-ctrl-group mapframe-draw-toolbar"
    );
    expect(
      el.children.map((b) => [
        b.tagName,
        b.type,
        b.className,
        b.getAttribute("data-mode"),
        b.title,
        b.getAttribute("aria-label"),
        b.getAttribute("aria-pressed"),
      ])
    ).toEqual([
      ...MODES.map((mode) => [
        "button",
        "button",
        "mapframe-draw-tool",
        mode,
        LABELS[mode],
        LABELS[mode],
        String(mode === "circle"),
      ]),
      [
        "button",
        "button",
        "mapframe-draw-clear",
        null,
        LABELS.clear,
        LABELS.clear,
        null,
      ],
    ]);
    // Each holds its Font Awesome icon as one inline path in the text colour.
    el.children.forEach((b, i) => {
      const [width, height, , , path] = ICONS[i].icon;
      const [svg] = b.children;
      expect([b.children.length, svg.tagName, svg.namespace]).toEqual([
        1,
        "svg",
        SVG,
      ]);
      expect(svg.getAttribute("viewBox")).toBe(`0 0 ${width} ${height}`);
      expect(svg.getAttribute("aria-hidden")).toBe("true");
      expect(svg.children.map((p) => p.tagName)).toEqual(["path"]);
      expect(svg.children[0].getAttribute("d")).toBe(path);
      expect(svg.children[0].getAttribute("fill")).toBe("currentColor");
    });

    // A new active tool keeps the buttons; new modes or labels rebuild them.
    const polygon = button("polygon");
    toolbar.sync(MODES, LABELS, "static");
    expect(pressed()).toEqual([]);
    expect(button("polygon")).toBe(polygon);
    toolbar.sync(["point"], { ...LABELS, point: "Point" }, "point");
    expect(
      el.children.map((b) => [b.getAttribute("data-mode"), b.title])
    ).toEqual([
      ["point", "Point"],
      [null, LABELS.clear],
    ]);
    expect(pressed()).toEqual(["point"]);
  });

  it("a click selects a mode, a second click static", () => {
    const { toolbar, selected, button, pressed } = setup();
    toolbar.sync(MODES, LABELS, "static");
    button("polygon").click();
    expect(pressed()).toEqual(["polygon"]);
    button("polygon").click();
    expect(pressed()).toEqual([]);
    button("point").click();
    button("select").click();
    expect(pressed()).toEqual(["select"]);
    expect(selected).toEqual(["polygon", "static", "point", "select"]);
  });

  it("clear calls onClear", () => {
    const { toolbar, el, selected, cleared, pressed } = setup();
    toolbar.sync(MODES, LABELS, "polygon");
    el.children.at(-1)!.click();
    expect(cleared()).toBe(1);
    expect(selected).toEqual([]);
    expect(pressed()).toEqual(["polygon"]);
    toolbar.onRemove();
    expect(el.removed).toBe(true);
  });
});
