import type { PointLike } from "maplibre-gl";

import {
  isCluster,
  ownedStyleLayers,
  type PointerMap,
  type RenderedFeature,
} from "./pointer";
import { sourceId } from "./translate";
import type { InteractionState, LayerState, MapState } from "./types";

const MAX_CELL = 200;

type Kind = keyof InteractionState;

/** The part of a DOM element the popup content uses. */
export interface ElementLike {
  className: string;
  textContent: string | null;
  append(...nodes: any[]): void;
}

export interface PopupOptions {
  className: string;
  closeButton: boolean;
  closeOnClick?: boolean;
  maxWidth?: string;
  offset?: number;
  focusAfterOpen?: boolean;
}

/** The part of `maplibregl.Popup` a view uses. */
export interface PopupLike {
  setLngLat(lnglat: [number, number]): unknown;
  setDOMContent(node: any): unknown;
  addTo(map: any): unknown;
  on(type: "close", listener: () => void): unknown;
  remove(): unknown;
}

export interface PopupModel {
  get(name: "state"): unknown;
  on(name: string, callback: () => void): void;
  off(name: string, callback: () => void): void;
}

export interface PopupsOptions {
  map: Pick<
    PointerMap,
    "getLayersOrder" | "getLayer" | "queryRenderedFeatures" | "on" | "off"
  >;
  model: PopupModel;
  /** Whether drawing is interactive: popups and tooltips are then off. */
  drawing?(): boolean;
  createPopup(options: PopupOptions): PopupLike;
  doc?: { createElement(tag: string): ElementLike };
  requestFrame?(callback: () => void): unknown;
}

interface PointerEvent {
  point: PointLike;
  lngLat: { lng: number; lat: number };
}

interface Shown {
  popup: PopupLike;
  /** The full source id of the feature it shows. */
  source: string;
}

interface Target {
  layer: LayerState;
  fields: string[];
  properties: Record<string, unknown>;
}

function cell(value: unknown): string {
  let text: string;
  if (value === null || value === undefined) text = "";
  else if (typeof value === "string") text = value;
  else if (typeof value === "object") text = JSON.stringify(value);
  else text = String(value);
  return text.slice(0, MAX_CELL);
}

/** The `[name, text]` pairs to show: the named properties present, or all. */
function entries(
  fields: string[],
  properties: Record<string, unknown>
): [string, string][] {
  const names = fields.length
    ? fields.filter((name) => Object.hasOwn(properties, name))
    : Object.keys(properties);
  return names.map((name) => [name, cell(properties[name])]);
}

/**
 * The click popup and the hover tooltip of one view, which each layer
 * declares in its `interaction`. Text goes in with `textContent`, never HTML.
 */
export class ViewPopups {
  private popup: Shown | null = null;
  private tooltip: Shown | null = null;
  private latest: PointerEvent | null = null;
  private frame = false;
  private disposed = false;
  private readonly doc: NonNullable<PopupsOptions["doc"]>;
  private readonly requestFrame: NonNullable<PopupsOptions["requestFrame"]>;

  constructor(private readonly options: PopupsOptions) {
    this.doc = options.doc ?? document;
    this.requestFrame =
      options.requestFrame ?? ((callback) => requestAnimationFrame(callback));
    const { map, model } = options;
    map.on("click", this.onClick);
    map.on("mousemove", this.onMove);
    map.on("mouseout", this.onOut);
    model.on("change:state", this.onState);
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    const { map, model } = this.options;
    map.off("click", this.onClick);
    map.off("mousemove", this.onMove);
    map.off("mouseout", this.onOut);
    model.off("change:state", this.onState);
    this.close("popup");
    this.close("tooltip");
  }

  /** Drawing became interactive or stopped being so: while it is, nothing stays open. */
  drawingChanged(): void {
    if (this.disposed || !this.options.drawing?.()) return;
    this.close("popup");
    this.close("tooltip");
  }

  /** Whether a layer shows a popup or a tooltip: its features take `pointer`. */
  clickable = (layerId: string): boolean => {
    const interaction = this.layers().find(
      (l) => l.id === layerId
    )?.interaction;
    return Boolean(interaction && (interaction.popup || interaction.tooltip));
  };

  private layers(): LayerState[] {
    const state = this.options.model.get("state") as Partial<MapState> | null;
    return state?.layers ?? [];
  }

  /** The top feature among layers that declare `kind`, if it is a declared instance. */
  private top(
    point: PointLike,
    kind: Kind,
    layers: LayerState[]
  ): Target | null {
    const { map } = this.options;
    const wants = (id: string) =>
      layers.some((l) => l.id === id && l.interaction?.[kind]);
    const styleLayers = ownedStyleLayers(map, wants);
    if (!styleLayers.length) return null;
    // Clusters are queried too, so one on top shows nothing of what lies below.
    styleLayers.push(...ownedStyleLayers(map, undefined, "only"));
    const features: RenderedFeature[] = map.queryRenderedFeatures(point, {
      layers: styleLayers,
    });
    for (const feature of features) {
      if (isCluster(feature)) return null;
      const layer = layers.find((l) => sourceId(l) === feature.source);
      const fields = layer?.interaction?.[kind];
      if (layer && fields) {
        return { layer, fields, properties: feature.properties ?? {} };
      }
    }
    return null;
  }

  private readonly onClick = (event: PointerEvent): void => {
    if (this.options.drawing?.()) return;
    const hit = this.top(event.point, "popup", this.layers());
    if (!hit) return;
    const shown = entries(hit.fields, hit.properties);
    if (!shown.length) return;
    this.close("popup");
    const table = this.doc.createElement("table");
    table.className = "psm-popup-table";
    for (const [name, text] of shown) {
      const row = this.doc.createElement("tr");
      const key = this.doc.createElement("th");
      key.textContent = name;
      const value = this.doc.createElement("td");
      value.textContent = text;
      row.append(key, value);
      table.append(row);
    }
    this.show("popup", sourceId(hit.layer), table, event, {
      className: "psm-popup",
      closeButton: true,
      maxWidth: "320px",
    });
  };

  private readonly onMove = (event: PointerEvent): void => {
    this.latest = event;
    if (this.frame) return;
    this.frame = true;
    this.requestFrame(() => {
      this.frame = false;
      const at = this.latest;
      if (this.disposed || !at) return;
      this.updateTooltip(at);
    });
  };

  private readonly onOut = (): void => {
    this.latest = null;
    this.close("tooltip");
  };

  private updateTooltip(event: PointerEvent): void {
    if (this.options.drawing?.()) {
      this.close("tooltip");
      return;
    }
    const hit = this.top(event.point, "tooltip", this.layers());
    const shown = hit ? entries(hit.fields, hit.properties) : [];
    if (!hit || !shown.length) {
      this.close("tooltip");
      return;
    }
    const content = this.doc.createElement("div");
    if (shown.length === 1 && hit.fields.length === 1) {
      content.textContent = shown[0][1];
    } else {
      for (const [name, text] of shown) {
        const line = this.doc.createElement("div");
        line.textContent = `${name}: ${text}`;
        content.append(line);
      }
    }
    this.show("tooltip", sourceId(hit.layer), content, event, {
      className: "psm-tooltip",
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      focusAfterOpen: false,
    });
  }

  private show(
    kind: Kind,
    source: string,
    content: ElementLike,
    event: PointerEvent,
    options: PopupOptions
  ): void {
    const open = this[kind];
    if (open && kind === "tooltip") {
      open.source = source;
      open.popup.setLngLat([event.lngLat.lng, event.lngLat.lat]);
      open.popup.setDOMContent(content);
      return;
    }
    const popup = this.options.createPopup(options);
    popup.setLngLat([event.lngLat.lng, event.lngLat.lat]);
    popup.setDOMContent(content);
    const shown = { popup, source };
    this[kind] = shown;
    // The close button and a click on the map close a popup on their own.
    popup.on("close", () => {
      if (this[kind] === shown) this[kind] = null;
    });
    popup.addTo(this.options.map);
  }

  private close(kind: Kind): void {
    const shown = this[kind];
    this[kind] = null;
    shown?.popup.remove();
  }

  // Each closes when the layer it shows is gone, replaced, hidden or no
  // longer declares it.
  private readonly onState = (): void => {
    const layers = this.layers();
    for (const kind of ["popup", "tooltip"] as const) {
      const shown = this[kind];
      if (!shown) continue;
      const layer = layers.find((l) => sourceId(l) === shown.source);
      if (!layer || !layer.visible || !layer.interaction?.[kind]) {
        this.close(kind);
      }
    }
  };
}
