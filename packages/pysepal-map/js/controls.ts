import {
  FullscreenControl,
  NavigationControl,
  ScaleControl,
} from "maplibre-gl";
import type {
  ControlPosition,
  IControl,
  Map as MapLibreMap,
} from "maplibre-gl";

import type { MapState } from "./types";
import { NO_INSETS, type Insets } from "./view";

type Name = "zoom" | "fullscreen" | "scale";

const DEFAULT_CONTROLS: MapState["controls"] = {
  zoom: true,
  fullscreen: true,
  scale: true,
};

/** Marks the element the fullscreen control fills instead of the map's. */
const FULLSCREEN_ROOT = "data-psm-fullscreen-root";
/** Set on the element the fullscreen control filled, while it is fullscreen. */
const FULLSCREEN = "data-psm-fullscreen";

/** The two sides each control corner is placed from. */
const CORNERS: [ControlPosition, "top" | "bottom", "left" | "right"][] = [
  ["top-left", "top", "left"],
  ["top-right", "top", "right"],
  ["bottom-left", "bottom", "left"],
  ["bottom-right", "bottom", "right"],
];

/** What fullscreen fills for a map: its closest marked ancestor, or itself. */
function fullscreenTarget(el: HTMLElement): HTMLElement {
  return el.closest<HTMLElement>(`[${FULLSCREEN_ROOT}]`) ?? el;
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

export interface ViewControlsOptions {
  map: MapLibreMap;
  /** The map's element, which holds the control corners. */
  root: HTMLElement;
  /** Called with the insets the view uses each time they may have changed. */
  onInsets(insets: Insets): void;
}

/**
 * The controls, the theme class and the insets of one view.
 *
 * The control corners sit in by the insets. While fullscreen, the UI the
 * insets describe is out of sight, so the view uses none, and the
 * fullscreen element carries `data-psm-fullscreen`.
 */
export class ViewControls {
  private readonly held: Partial<Record<Name, IControl>> = {};
  private insets: Insets = NO_INSETS;
  /** The element filling the screen, while one does. */
  private fullscreen: HTMLElement | null = null;

  constructor(private readonly options: ViewControlsOptions) {}

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
    this.options.root.classList.toggle("psm-dark", state?.theme === "dark");
  }

  /** The insets the model declares. */
  setInsets(insets: Insets): void {
    this.insets = insets;
    this.apply();
  }

  /** Takes `data-psm-fullscreen` back off the element it marked. */
  dispose(): void {
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

  // Its events also fire in the pseudo-fullscreen fallback, where the
  // :fullscreen pseudo-class never matches.
  private fullscreenControl(): IControl {
    const control = new ViewFullscreenControl();
    control.on("fullscreenstart", () => {
      this.fullscreen = control.target;
      this.fullscreen.setAttribute(FULLSCREEN, "");
      this.apply();
    });
    control.on("fullscreenend", () => this.leaveFullscreen());
    return control;
  }

  private leaveFullscreen(): void {
    if (!this.fullscreen) return;
    this.fullscreen.removeAttribute(FULLSCREEN);
    this.fullscreen = null;
    this.apply();
  }

  private apply(): void {
    const insets = this.fullscreen ? NO_INSETS : this.insets;
    const { root, onInsets } = this.options;
    for (const [position, vertical, horizontal] of CORNERS) {
      const corner = root.querySelector<HTMLElement>(
        `.maplibregl-ctrl-${position}`
      );
      if (!corner) continue;
      corner.style[vertical] = `${insets[vertical]}px`;
      corner.style[horizontal] = `${insets[horizontal]}px`;
    }
    onInsets(insets);
  }
}
