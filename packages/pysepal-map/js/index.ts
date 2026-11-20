import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Protocol } from "pmtiles";
import type { RenderProps } from "@anywidget/types";

// One registration per bundled MapLibre instance, shared by all its views.
maplibregl.addProtocol("pmtiles", new Protocol().tile);

interface Model {
  height: string;
}

type PsmElement = HTMLElement & { psmMap?: maplibregl.Map };

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

  const resizer = new ResizeObserver(() => map.resize());
  resizer.observe(root);

  return () => {
    model.off("change:height", applyHeight);
    resizer.disconnect();
    delete root.psmMap;
    map.remove();
  };
}

export default { render };
