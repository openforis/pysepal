import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { Protocol } from "pmtiles";
import workerSource from "psm:maplibre-worker";
import type { RenderProps } from "@anywidget/types";

import { CompareView, RevisionMark, type CompareRoot } from "./compare";
import { ViewControls } from "./controls";
import { ViewDraw, terraDraw } from "./draw";
import { installImages } from "./images";
import { ViewLink, pageRegistry } from "./link";
import { MapSync } from "./maplive";
import { ViewPointer } from "./pointer";
import { ViewPopups } from "./popups";
import { ViewProjection } from "./projection";
import { StatusReporter, ViewPresence, newViewId, onLiveAgain } from "./status";
import { DrawToolbar } from "./toolbar";
import type { MapState } from "./types";
import { CAMERA_OPTIONS, ViewCamera, insetsOf, lockRotation } from "./view";

// MapLibre 6 loads its worker from a file next to the module; the bundle has
// no such file, so ship the worker inline.
maplibregl.setWorkerUrl(
  URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }))
);

// One registration per bundled MapLibre instance, shared by all its views.
// The metadata gives the TileJSON the archive's layer names, which the
// status reporter checks, and its attribution.
maplibregl.addProtocol("pmtiles", new Protocol({ metadata: true }).tile);

interface Model {
  height: string;
  state: unknown;
  view: unknown;
  view_request: unknown;
  insets: unknown;
  cursor: string;
  marker: unknown;
  drawing: unknown;
  draw_request: unknown;
  drawn: unknown;
  draw_tool: unknown;
  projection: string;
  _link: Record<string, unknown>;
}

type PsmElement = HTMLElement &
  CompareRoot & {
    psmMap?: maplibregl.Map;
    psmInspect?: () => unknown;
    psmStatus?: StatusReporter;
    psmCamera?: ViewCamera;
    psmDraw?: ViewDraw;
  };

// The view's own map; in compare, a CompareView adds the "right" one.
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
    // ViewControls adds it, with the right map's attributions in compare.
    attributionControl: false,
    // The root's resize observer resizes it, and paints it at once.
    trackResize: false,
  });
  lockRotation(map);
  const removeImages = installImages(map);
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
  const mark = new RevisionMark(root, model);
  // Set once built, after the main sync, whose first state already looks.
  let shared: CompareView | null = null;
  const sync = new MapSync(
    map,
    model,
    (revision) => mark.set(SIDE, revision),
    reporter,
    // A state that hands a right layer to the main map reaches the main sync
    // first, while the right map still holds its payload.
    { viewId, side: SIDE, lookup: (digest) => shared?.payload(digest) }
  );
  root.psmInspect = () => sync.inspect();
  // Before the tools that read it: the pointer's settled waits for both maps.
  const compare = new CompareView({
    root,
    main: map,
    model,
    viewId,
    send,
    mark,
    lookup: (digest) => sync.payload(digest),
    createMap: (container) =>
      new maplibregl.Map({
        container,
        style: { version: 8, sources: {}, layers: [] },
        ...CAMERA_OPTIONS,
        interactive: false,
        attributionControl: false,
        // The root's resize observer resizes it with the main map.
        trackResize: false,
      }),
  });
  shared = compare;
  // Built after the map sync, so it handles a style load after the sync did.
  let draw: ViewDraw | null = null;
  const drawing = () => draw?.interactive() ?? false;
  // In compare, the pointer reads what the half it is over shows.
  const pick = (point: { x: number; y: number }) => compare.pick(point);
  const popups = new ViewPopups({
    map,
    model,
    drawing,
    pick,
    createPopup: (options) => new maplibregl.Popup(options),
  });
  const pointer = new ViewPointer({
    map,
    model,
    viewId,
    side: SIDE,
    send,
    settled: () => sync.settled() && compare.settled(),
    drawing,
    pick,
    hidden: (point) => compare.hidden(point),
    clickable: popups.clickable,
    clustered: (id) => {
      const state = model.get("state") as Partial<MapState> | null;
      return (state?.layers ?? []).some(
        (l) => l.id === id && l.kind === "geojson" && l.source.cluster !== null
      );
    },
    createMarker: (color) => new maplibregl.Marker({ color }),
  });
  const toolbar = new DrawToolbar({
    onSelect: (mode) => draw?.setMode(mode),
    onClear: () => draw?.clearAll(),
  });
  let toolbarShown = false;
  const showTools = (
    modes: string[],
    labels: Record<string, string>,
    active: string
  ) => {
    if (modes.length) {
      toolbar.sync(modes, labels, active);
      if (!toolbarShown) map.addControl(toolbar, "top-left");
    } else if (toolbarShown) {
      map.removeControl(toolbar);
    }
    toolbarShown = modes.length > 0;
  };
  draw = new ViewDraw({
    map,
    model,
    viewId,
    side: SIDE,
    send,
    createDraw: terraDraw(map),
    onInteractiveChange: () => {
      popups.drawingChanged();
      pointer.drawingChanged();
    },
    onRendered: (features, color) => {
      compare.setDrawing(features, color);
      root.style.setProperty("--psm-draw-color", color);
    },
    onToolsChange: showTools,
  });
  root.psmDraw = draw;
  const camera = new ViewCamera({ map, model, viewId, host: root, send });
  root.psmCamera = camera;
  const projection = new ViewProjection({ map, model, viewId, send });
  const controls = new ViewControls({
    map,
    root,
    viewId,
    onInsets: (insets, keepPlace) => {
      camera.setInsets(insets, keepPlace);
      compare.setInsets(insets);
    },
  });
  const applyInsets = () => controls.setInsets(insetsOf(model.get("insets")));
  // Before the camera starts, which restores its center inside them.
  applyInsets();
  model.on("change:insets", applyInsets);
  // After the camera has restored its view, which the group must not take.
  const link = new ViewLink({ map, model, registry: pageRegistry() });
  link.start(camera.start());
  // Python may have expired the view, and reports sent meanwhile be lost.
  const stopLive = onLiveAgain(model, () => {
    presence.reopen();
    reporter.replay();
    sync.reconnect();
    compare.reconnect();
    camera.reconnect();
    draw?.reconnect();
  });

  const applyControls = () =>
    controls.sync(model.get("state") as Partial<MapState>);
  applyControls();
  model.on("change:state", applyControls);
  // After the controls, so the toolbar sits below them.
  const { modes, labels, active } = draw.tools();
  showTools(modes, labels, active);

  const resizer = new ResizeObserver(() => {
    // The right map first, so the main map's move paints it at its new size.
    compare.resize();
    map.resize();
    // A resize clears the canvas, and MapLibre paints on the next frame: the
    // browser would show this one blank, each step of a window resize.
    map.redraw();
  });
  resizer.observe(root);

  return () => {
    stopLive();
    link.dispose();
    camera.dispose();
    projection.dispose();
    // Before the map goes: it removes Terra Draw's layers.
    draw?.dispose();
    pointer.dispose();
    popups.dispose();
    // Before the main map goes: the right map lives in its canvas container.
    compare.dispose();
    removeImages();
    controls.dispose();
    sync.dispose();
    presence.dispose();
    model.off("change:height", applyHeight);
    model.off("change:insets", applyInsets);
    model.off("change:state", applyControls);
    resizer.disconnect();
    root.style.removeProperty("--psm-draw-color");
    delete root.psmMap;
    delete root.psmInspect;
    delete root.psmStatus;
    delete root.psmCamera;
    delete root.psmDraw;
    map.remove();
  };
}

export default { render };
