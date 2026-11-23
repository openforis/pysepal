/*! Font Awesome Free 7.3.1 by @fontawesome - https://fontawesome.com License - https://fontawesome.com/license/free (Icons: CC BY 4.0, Code: MIT) */
import { faCircle } from "@fortawesome/free-regular-svg-icons/faCircle";
import { faSquare } from "@fortawesome/free-regular-svg-icons/faSquare";
import { faArrowPointer } from "@fortawesome/free-solid-svg-icons/faArrowPointer";
import { faBezierCurve } from "@fortawesome/free-solid-svg-icons/faBezierCurve";
import { faDrawPolygon } from "@fortawesome/free-solid-svg-icons/faDrawPolygon";
import { faLocationDot } from "@fortawesome/free-solid-svg-icons/faLocationDot";
import { faTrash } from "@fortawesome/free-solid-svg-icons/faTrash";
import type { IControl } from "maplibre-gl";

type Icon = typeof faTrash;

const STATIC = "static";
const SVG = "http://www.w3.org/2000/svg";

/** Each tool's icon, from Font Awesome Free, the set SEPAL's GUI uses. */
const ICONS: Record<string, Icon> = {
  polygon: faDrawPolygon,
  rectangle: faSquare,
  circle: faCircle,
  linestring: faBezierCurve,
  point: faLocationDot,
  select: faArrowPointer,
};

export interface DrawToolbarOptions {
  /** A tool was clicked: its mode, or `static` for the active one. */
  onSelect(mode: string): void;
  onClear(): void;
  doc?: Document;
}

/**
 * The draw toolbar of one view: a button per tool offered, the active one
 * pressed, then a button that removes every shape. It shows what `sync`
 * last gave it, and a click only tells the view.
 */
export class DrawToolbar implements IControl {
  private readonly doc: Document;
  private readonly element: HTMLElement;
  private tools: HTMLButtonElement[] = [];
  private shown = "";
  private active = STATIC;

  constructor(private readonly options: DrawToolbarOptions) {
    this.doc = options.doc ?? document;
    this.element = this.doc.createElement("div");
    this.element.className =
      "maplibregl-ctrl maplibregl-ctrl-group psm-draw-toolbar";
  }

  onAdd(): HTMLElement {
    return this.element;
  }

  onRemove(): void {
    this.element.remove();
  }

  /** Show the tools `modes`, in order, with their `labels`, and `active` pressed. */
  sync(modes: string[], labels: Record<string, string>, active: string): void {
    const shown = JSON.stringify([modes, labels]);
    if (shown !== this.shown) {
      this.shown = shown;
      this.build(modes, labels);
    }
    this.active = active;
    for (const button of this.tools) {
      const pressed = button.getAttribute("data-mode") === active;
      button.setAttribute("aria-pressed", String(pressed));
    }
  }

  private build(modes: string[], labels: Record<string, string>): void {
    this.tools = modes
      .filter((mode) => ICONS[mode])
      .map((mode) => {
        const button = this.button("psm-draw-tool", ICONS[mode], labels[mode]);
        button.setAttribute("data-mode", mode);
        button.addEventListener("click", () =>
          this.options.onSelect(mode === this.active ? STATIC : mode)
        );
        return button;
      });
    const clear = this.button("psm-draw-clear", faTrash, labels.clear);
    clear.addEventListener("click", () => this.options.onClear());
    this.element.replaceChildren(...this.tools, clear);
  }

  private button(
    className: string,
    { icon: [width, height, , , path] }: Icon,
    label = ""
  ): HTMLButtonElement {
    const { doc } = this;
    const button = doc.createElement("button");
    button.type = "button";
    button.className = className;
    button.title = label;
    button.setAttribute("aria-label", label);
    const svg = doc.createElementNS(SVG, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("aria-hidden", "true");
    const shape = doc.createElementNS(SVG, "path");
    // A duotone icon would give two paths; these are all single.
    shape.setAttribute("d", path as string);
    shape.setAttribute("fill", "currentColor");
    svg.append(shape);
    button.append(svg);
    return button;
  }
}
