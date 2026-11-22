import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { Protocol } from "pmtiles";
import workerSource from "psm:maplibre-worker";
import type { RenderProps } from "@anywidget/types";

import { ViewControls } from "./controls";
import { MapSync } from "./maplive";
import { ViewPointer } from "./pointer";
import { ViewPopups } from "./popups";
import { StatusReporter, ViewPresence, newViewId, onLiveAgain } from "./status";
import type { MapState } from "./types";
import { CAMERA_OPTIONS, ViewCamera, insetsOf, lockRotation } from "./view";

// MapLibre 6 loads its worker from a file next to the module; the bundle has
// no such file, so ship the worker inline.
maplibregl.setWorkerUrl(
  URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }))
);

// One registration per bundled MapLibre instance, shared by all its views.
maplibregl.addProtocol("pmtiles", new Protocol().tile);

interface Model {
  height: string;
  state: unknown;
  view: unknown;
  view_request: unknown;
  insets: unknown;
  cursor: string;
  marker: unknown;
}

type PsmElement = HTMLElement & {
  psmMap?: maplibregl.Map;
  psmInspect?: () => unknown;
  psmStatus?: StatusReporter;
  psmCamera?: ViewCamera;
};

// Phase 1 renders a single map; compare views will mount "left" and "right".
const SIDE = "main";

function render({ model, el }: RenderProps<Model>) {
  const root = el as PsmElement;
  root.classList.add("psm-map");
  const applyHeight = () => {
    root.style.setProperty("--psm-height", model.get("height"));
  };
  applyHeight();
  model.on("change:height", applyHeight);

  const send = (content: unknown): boolean => {
    try {
      model.send(content);
      return true;
    } catch (error) {
      // A closed comm; reconnecting opens the view again.
      console.error("pysepal-map: could not send", error);
      return false;
    }
  };
  const viewId = newViewId();
  const map = new maplibregl.Map({
    container: root,
    style: { version: 8, sources: {}, layers: [] },
    ...CAMERA_OPTIONS,
  });
  lockRotation(map);
  root.psmMap = map;
  const reporter = new StatusReporter({
    viewId,
    side: SIDE,
    send,
    current: (id) => map.getSource(id),
  });
  root.psmStatus = reporter;
  // Open before the first report, so Python counts the view in.
  const presence = new ViewPresence({ viewId, side: SIDE, send, page: window });
  presence.start();
  const sync = new MapSync(map, model, root, reporter, { viewId, side: SIDE });
  root.psmInspect = () => sync.inspect();
  const popups = new ViewPopups({
    map,
    model,
    createPopup: (options) => new maplibregl.Popup(options),
  });
  const pointer = new ViewPointer({
    map,
    model,
    viewId,
    side: SIDE,
    settled: () => sync.settled(),
    clickable: popups.clickable,
    createMarker: (color) => new maplibregl.Marker({ color }),
  });
  const camera = new ViewCamera({ map, model, viewId, host: root, send });
  root.psmCamera = camera;
  const controls = new ViewControls({
    map,
    root,
    onInsets: (insets) => camera.setInsets(insets),
  });
  const applyInsets = () => controls.setInsets(insetsOf(model.get("insets")));
  // Before the camera starts, which restores its center inside them.
  applyInsets();
  model.on("change:insets", applyInsets);
  camera.start();
  // Python may have expired the view, and reports sent meanwhile be lost.
  const stopLive = onLiveAgain(model, () => {
    presence.reopen();
    reporter.replay();
    sync.reconnect();
    camera.reconnect();
  });

  const applyControls = () =>
    controls.sync(model.get("state") as Partial<MapState>);
  applyControls();
  model.on("change:state", applyControls);

  const resizer = new ResizeObserver(() => map.resize());
  resizer.observe(root);

  return () => {
    stopLive();
    camera.dispose();
    pointer.dispose();
    popups.dispose();
    controls.dispose();
    sync.dispose();
    presence.dispose();
    model.off("change:height", applyHeight);
    model.off("change:insets", applyInsets);
    model.off("change:state", applyControls);
    resizer.disconnect();
    delete root.psmMap;
    delete root.psmInspect;
    delete root.psmStatus;
    delete root.psmCamera;
    map.remove();
  };
}

export default { render };
