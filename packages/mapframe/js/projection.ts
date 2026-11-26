export type ProjectionName = "mercator" | "globe";

/** A projection as the model or MapLibre names it; anything else is Mercator. */
export function projectionOf(value: unknown): ProjectionName {
  return value === "globe" ? "globe" : "mercator";
}

/** What the projection reads of a MapLibre map. */
export interface ProjectionMap {
  getProjection(): { type?: unknown } | undefined;
  setProjection(projection: { type: ProjectionName }): unknown;
  on(type: string, listener: () => void): unknown;
  off(type: string, listener: () => void): unknown;
}

export interface ProjectionModel {
  get(name: "projection"): unknown;
  on(event: string, callback: () => void): void;
  off(event: string, callback: () => void): void;
}

export interface ViewProjectionOptions {
  map: ProjectionMap;
  model: ProjectionModel;
  viewId: string;
  send(content: unknown): boolean;
}

/**
 * Keeps a view's map in the projection the model holds, and reports one a
 * user picked, with the globe button, so every view of the map follows.
 *
 * MapLibre throws on a projection set while a style loads, and rebuilds the
 * style after a worker restart or a GPU reset, so it waits for each
 * `style.load`.
 */
export class ViewProjection {
  private styled = false;

  constructor(private readonly options: ViewProjectionOptions) {
    const { map, model } = options;
    map.on("style.load", this.onStyleLoad);
    map.on("styledataloading", this.unstyled);
    map.on("webglcontextlost", this.unstyled);
    map.on("projectiontransition", this.onTransition);
    model.on("change:projection", this.apply);
  }

  dispose(): void {
    const { map, model } = this.options;
    map.off("style.load", this.onStyleLoad);
    map.off("styledataloading", this.unstyled);
    map.off("webglcontextlost", this.unstyled);
    map.off("projectiontransition", this.onTransition);
    model.off("change:projection", this.apply);
  }

  private current(): ProjectionName {
    return projectionOf(this.options.map.getProjection()?.type);
  }

  private wanted(): ProjectionName {
    return projectionOf(this.options.model.get("projection"));
  }

  private readonly onStyleLoad = () => {
    this.styled = true;
    this.apply();
  };

  private readonly unstyled = () => {
    this.styled = false;
  };

  private readonly apply = () => {
    if (!this.styled) return;
    const wanted = this.wanted();
    if (this.current() !== wanted)
      this.options.map.setProjection({ type: wanted });
  };

  // A style that loads sets its own projection first: only a loaded one reports.
  private readonly onTransition = () => {
    if (!this.styled) return;
    const now = this.current();
    if (now === this.wanted()) return;
    this.options.send({
      type: "projection",
      view_id: this.options.viewId,
      projection: now,
    });
  };
}
