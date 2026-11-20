import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import workerSource from "maplibre-gl/dist/maplibre-gl-worker.mjs" with { type: "text" };
import type { RenderProps } from "@anywidget/types";

import { MapSync } from "./maplive";

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
};

function render({ model, el }: RenderProps<Model>) {
  const root = el as PsmElement;
  root.classList.add("psm-map");
  const applyHeight = () => {
    root.style.height = model.get("height");
  };
  applyHeight();
  model.on("change:height", applyHeight);

  const map = new maplibregl.Map({
    container: root,
    style: { version: 8, sources: {}, layers: [] },
  });
  root.psmMap = map;
  const sync = new MapSync(map, model, root);
  root.psmInspect = () => sync.inspect();

  const resizer = new ResizeObserver(() => map.resize());
  resizer.observe(root);

  return () => {
    sync.dispose();
    model.off("change:height", applyHeight);
    resizer.disconnect();
    delete root.psmMap;
    delete root.psmInspect;
    map.remove();
  };
}

export default { render };
