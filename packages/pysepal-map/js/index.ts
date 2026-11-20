import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "./style.css";
import { Protocol } from "pmtiles";
import workerSource from "maplibre-gl/dist/maplibre-gl-worker.mjs" with { type: "text" };
import type { RenderProps } from "@anywidget/types";

import { MapSync } from "./maplive";
import { StatusReporter, ViewPresence, newViewId, onLiveAgain } from "./status";

// MapLibre 6 loads its worker from a file next to the module; the bundle has
// no such file, so ship the worker inline.
maplibregl.setWorkerUrl(
  URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" })),
);

// One registration per bundled MapLibre instance, shared by all its views.
maplibregl.addProtocol("pmtiles", new Protocol().tile);

interface Model {
  height: string;
  state: unknown;
}

type PsmElement = HTMLElement & {
  psmMap?: maplibregl.Map;
  psmInspect?: () => unknown;
  psmStatus?: StatusReporter;
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

  const send = (content: unknown) => {
    try {
      model.send(content);
    } catch (error) {
      // A closed comm; reconnecting opens the view again.
      console.error("pysepal-map: could not send", error);
    }
  };
  const viewId = newViewId();
  const map = new maplibregl.Map({
    container: root,
    style: { version: 8, sources: {}, layers: [] },
  });
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
  const sync = new MapSync(map, model, root, reporter);
  root.psmInspect = () => sync.inspect();
  // Python may have expired the view, and reports sent meanwhile be lost.
  const stopLive = onLiveAgain(model, () => {
    presence.reopen();
    reporter.replay();
    sync.reconnect();
  });

  const resizer = new ResizeObserver(() => map.resize());
  resizer.observe(root);

  return () => {
    stopLive();
    sync.dispose();
    presence.dispose();
    model.off("change:height", applyHeight);
    resizer.disconnect();
    delete root.psmMap;
    delete root.psmInspect;
    delete root.psmStatus;
    map.remove();
  };
}

export default { render };
