import { FullscreenControl, NavigationControl } from "maplibre-gl";
import type { IControl, Map as MapLibreMap } from "maplibre-gl";

import type { MapState } from "./types";

type Name = "zoom" | "fullscreen";

/** The controls each map carries, so a later state can remove them. */
const held = new WeakMap<MapLibreMap, Partial<Record<Name, IControl>>>();

function toggle(
  map: MapLibreMap,
  name: Name,
  wanted: boolean,
  make: () => IControl
): void {
  const mine = held.get(map) ?? {};
  held.set(map, mine);
  const current = mine[name];
  if (wanted && !current) {
    const control = make();
    mine[name] = control;
    map.addControl(control, "top-left");
  } else if (!wanted && current) {
    map.removeControl(current);
    delete mine[name];
  }
}

/** Shows the controls and the theme class that `state` declares. */
export function syncControls(
  map: MapLibreMap,
  el: HTMLElement,
  state: Partial<MapState> | null | undefined
): void {
  const controls = state?.controls ?? { zoom: true, fullscreen: true };
  // The compass button can rotate the map, which the view keeps north-up.
  toggle(
    map,
    "zoom",
    controls.zoom,
    () => new NavigationControl({ showCompass: false, visualizePitch: false })
  );
  toggle(map, "fullscreen", controls.fullscreen, () => new FullscreenControl());
  el.classList.toggle("psm-dark", state?.theme === "dark");
}
