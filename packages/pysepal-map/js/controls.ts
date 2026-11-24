import {
  AttributionControl,
  FullscreenControl,
  NavigationControl,
  ScaleControl,
} from "maplibre-gl";
import type {
  ControlPosition,
  IControl,
  Map as MapLibreMap,
} from "maplibre-gl";

import { wrapLng } from "./pointer";
import { forSide } from "./translate";
import type { MapState } from "./types";
import { NO_INSETS, type Insets } from "./view";

/** The link MapLibre's default attribution control shows; it is not exported. */
const MAPLIBRE_ATTRIBUTION =
  '<a href="https://maplibre.org/" target="_blank">MapLibre</a>';

type Name = "zoom" | "fullscreen" | "scale" | "coordinates";

const DEFAULT_CONTROLS: MapState["controls"] = {
  zoom: true,
  fullscreen: true,
  scale: true,
  coordinates: false,
};

/** Marks the element the fullscreen control fills instead of the map's. */
const FULLSCREEN_ROOT = "data-psm-fullscreen-root";
/** Set on the element the fullscreen control filled, while it is fullscreen. */
const FULLSCREEN = "data-psm-fullscreen";
/** Set on the element that holds the corner heights, to the measuring view's id. */
export const CONTROLS = "data-psm-controls";

/** The variable that holds the height of a control corner. */
const cornerVariable = (position: ControlPosition) =>
  `--psm-controls-${position}`;

/** The two sides each control corner is placed from. */
const CORNERS: [ControlPosition, "top" | "bottom", "left" | "right"][] = [
  ["top-left", "top", "left"],
  ["top-right", "top", "right"],
  ["bottom-left", "bottom", "left"],
  ["bottom-right", "bottom", "right"],
];

/** What fullscreen fills for a map: its closest marked ancestor, or itself. */
export function fullscreenTarget(el: HTMLElement): HTMLElement {
  return el.closest<HTMLElement>(`[${FULLSCREEN_ROOT}]`) ?? el;
}

function observeSize(elements: HTMLElement[], callback: () => void) {
  const observer = new ResizeObserver(() => callback());
  for (const el of elements) observer.observe(el);
  return () => observer.disconnect();
}

/**
 * MapLibre's fullscreen control, aimed at `fullscreenTarget` on each
 * request: a view is often not in the page yet when its controls are added.
 */
class ViewFullscreenControl extends FullscreenControl {
  /** The element it fills, or last filled. */
  get target(): HTMLElement {
    return this._container;
  }

  override _requestFullscreen(): void {
    this._container = fullscreenTarget(this._map.getContainer());
    super._requestFullscreen();
  }
}

/**
 * The attributions of the visible layers the right map of a compare view
 * draws and the main map does not, once each and in state order. The main
 * map's attribution control finds every other one in its own sources.
 */
function rightOnlyAttributions(
  state: Partial<MapState> | null | undefined
): string[] {
  if (state?.compare !== true || !Array.isArray(state.layers)) return [];
  const full = state as MapState;
  const main = new Set(forSide(full, "main").layers);
  const found: string[] = [];
  for (const layer of forSide(full, "right").layers) {
    if (main.has(layer) || !layer.visible || !layer.attribution) continue;
    if (!found.includes(layer.attribution)) found.push(layer.attribution);
  }
  return found;
}

/** The pointer's `lat, lng`, empty while the pointer is off the map. */
class CoordinatesControl implements IControl {
  private el: HTMLElement | null = null;
  private map: MapLibreMap | null = null;

  onAdd(map: MapLibreMap): HTMLElement {
    this.map = map;
    this.el = document.createElement("div");
    this.el.className = "maplibregl-ctrl psm-coordinates";
    map.on("mousemove", this.onMove);
    map.on("mouseout", this.onOut);
    return this.el;
  }

  onRemove(): void {
    this.map?.off("mousemove", this.onMove);
    this.map?.off("mouseout", this.onOut);
    this.el?.remove();
    this.el = null;
    this.map = null;
  }

  private readonly onMove = (event: {
    lngLat: { lng: number; lat: number };
  }): void => {
    if (!this.el) return;
    const { lng, lat } = event.lngLat;
    this.el.textContent = `${lat.toFixed(5)}, ${wrapLng(lng).toFixed(5)}`;
  };

  private readonly onOut = (): void => {
    if (this.el) this.el.textContent = "";
  };
}

export interface ViewControlsOptions {
  map: MapLibreMap;
  /** The map's element, which holds the control corners. */
  root: HTMLElement;
  /** The view's id, which marks the element holding its corner heights. */
  viewId: string;
  /**
   * Called with the insets the view uses each time they may have changed;
   * `keepPlace` is false when the view enters or leaves fullscreen.
   */
  onInsets(insets: Insets, keepPlace: boolean): void;
  /**
   * Calls `callback` each time one of `elements` changes size, until the
   * returned function is called. A `ResizeObserver` by default.
   */
  observeSize?(elements: HTMLElement[], callback: () => void): () => void;
}

/**
 * The controls, the theme class and the insets of one view.
 *
 * The control corners sit in by the insets. While fullscreen, the UI the
 * insets describe is out of sight, so the view uses none, and the
 * fullscreen element carries `data-psm-fullscreen`.
 *
 * Each time a corner changes size, the fullscreen target gets every
 * corner's height inline, as `--psm-controls-top-left` and so on, and
 * `data-psm-controls` set to the view's id, so the host's overlays can
 * clear the controls. A newer view that measured there since keeps both.
 *
 * The attribution control is MapLibre's default one, which the map is built
 * without: in compare it also lists what only the right map draws, and its
 * custom attribution is fixed once added, so a change replaces it.
 */
export class ViewControls {
  private readonly held: Partial<Record<Name, IControl>> = {};
  private attribution: { control: IControl; key: string } | null = null;
  private insets: Insets = NO_INSETS;
  /** The element filling the screen, while one does. */
  private fullscreen: HTMLElement | null = null;
  /** MapLibre's corner elements, which it keeps for the map's life. */
  private readonly corners = new Map<ControlPosition, HTMLElement>();
  /** The element holding the corner heights this view last measured. */
  private measured: HTMLElement | null = null;
  private readonly stopObserving: () => void;

  constructor(private readonly options: ViewControlsOptions) {
    // A compare view's right map sits in the canvas container, before the
    // main map's control container, with corners of its own.
    for (const [position] of CORNERS) {
      const corner = options.map
        .getContainer()
        .querySelector<HTMLElement>(
          `:scope > .maplibregl-control-container > .maplibregl-ctrl-${position}`
        );
      if (corner) this.corners.set(position, corner);
    }
    this.stopObserving = (options.observeSize ?? observeSize)(
      [...this.corners.values()],
      () => this.measure()
    );
  }

  /** Shows the controls and the theme class that `state` declares. */
  sync(state: Partial<MapState> | null | undefined): void {
    const controls = state?.controls ?? DEFAULT_CONTROLS;
    // The compass button can rotate the map, which the view keeps north-up.
    this.toggle(
      "zoom",
      controls.zoom,
      "top-left",
      () => new NavigationControl({ showCompass: false, visualizePitch: false })
    );
    this.toggle("fullscreen", controls.fullscreen, "top-left", () =>
      this.fullscreenControl()
    );
    this.toggle(
      "scale",
      controls.scale,
      "bottom-left",
      () => new ScaleControl({ unit: "metric" })
    );
    this.toggle(
      "coordinates",
      Boolean(controls.coordinates),
      "bottom-left",
      () => new CoordinatesControl()
    );
    this.syncAttribution(state);
    this.options.root.classList.toggle("psm-dark", state?.theme === "dark");
  }

  /** The insets the model declares. */
  setInsets(insets: Insets): void {
    this.insets = insets;
    this.apply();
  }

  /** Takes `data-psm-fullscreen` and the corner heights back off. */
  dispose(): void {
    this.stopObserving();
    this.unmeasure();
    this.leaveFullscreen();
  }

  private toggle(
    name: Name,
    wanted: boolean,
    position: ControlPosition,
    make: () => IControl
  ): void {
    const current = this.held[name];
    if (wanted && !current) {
      const control = make();
      this.held[name] = control;
      this.options.map.addControl(control, position);
    } else if (!wanted && current) {
      this.options.map.removeControl(current);
      delete this.held[name];
      // Its onRemove drops the document listener: no fullscreenend follows.
      if (name === "fullscreen") this.leaveFullscreen();
    }
  }

  private syncAttribution(state: Partial<MapState> | null | undefined): void {
    const customAttribution = [
      MAPLIBRE_ATTRIBUTION,
      ...rightOnlyAttributions(state),
    ];
    const key = JSON.stringify(customAttribution);
    if (this.attribution?.key === key) return;
    const { map } = this.options;
    if (this.attribution) map.removeControl(this.attribution.control);
    const control = new AttributionControl({
      compact: true,
      customAttribution,
    });
    map.addControl(control, "bottom-left");
    this.attribution = { control, key };
  }

  // Its events also fire in the pseudo-fullscreen fallback, where the
  // :fullscreen pseudo-class never matches.
  private fullscreenControl(): IControl {
    const control = new ViewFullscreenControl();
    control.on("fullscreenstart", () => {
      this.fullscreen = control.target;
      this.fullscreen.setAttribute(FULLSCREEN, "");
      this.apply(false);
    });
    control.on("fullscreenend", () => this.leaveFullscreen());
    return control;
  }

  private leaveFullscreen(): void {
    if (!this.fullscreen) return;
    this.fullscreen.removeAttribute(FULLSCREEN);
    this.fullscreen = null;
    this.apply(false);
  }

  private apply(keepPlace = true): void {
    const insets = this.fullscreen ? NO_INSETS : this.insets;
    for (const [position, vertical, horizontal] of CORNERS) {
      const corner = this.corners.get(position);
      if (!corner) continue;
      corner.style[vertical] = `${insets[vertical]}px`;
      corner.style[horizontal] = `${insets[horizontal]}px`;
    }
    this.options.onInsets(insets, keepPlace);
  }

  // The target is resolved each time: the view may join the page, or move,
  // after its first measure.
  private measure(): void {
    const target = fullscreenTarget(this.options.root);
    if (this.measured !== target) this.unmeasure();
    for (const [position, corner] of this.corners) {
      target.style.setProperty(
        cornerVariable(position),
        `${corner.offsetHeight}px`
      );
    }
    target.setAttribute(CONTROLS, this.options.viewId);
    this.measured = target;
  }

  private unmeasure(): void {
    const el = this.measured;
    this.measured = null;
    if (el?.getAttribute(CONTROLS) !== this.options.viewId) return;
    el.removeAttribute(CONTROLS);
    for (const [position] of CORNERS) {
      el.style.removeProperty(cornerVariable(position));
    }
  }
}
