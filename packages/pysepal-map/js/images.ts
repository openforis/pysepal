import { COUNT_PREFIX, PIN_PREFIX } from "./translate";

/** Pixels of an image, in the shape `map.addImage` takes. */
export interface Pixels {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

/** The part of a MapLibre map the resolver uses. */
export interface ImageMap {
  hasImage(id: string): boolean;
  addImage(id: string, image: Pixels, options: { pixelRatio: number }): unknown;
  setMissingStyleImageResolver(
    resolver: ((id: string) => void | Promise<void>) | null
  ): unknown;
}

export type Drawing =
  | { kind: "pin"; color: string }
  | { kind: "count"; color: string; label: string };

function decode(text: string): string | null {
  try {
    return decodeURIComponent(text);
  } catch {
    return null;
  }
}

/** The colour of a `psm-pin:<color>` id, or null for any other id. */
export function parsePinId(id: string): string | null {
  if (!id.startsWith(PIN_PREFIX)) return null;
  const color = decode(id.slice(PIN_PREFIX.length));
  return color ? color : null;
}

/** The colour and label of a `psm-count:<color>:<label>` id, or null. */
export function parseCountId(
  id: string
): { color: string; label: string } | null {
  if (!id.startsWith(COUNT_PREFIX)) return null;
  const rest = id.slice(COUNT_PREFIX.length);
  // The colour is escaped, so its first raw colon ends it.
  const colon = rest.indexOf(":");
  if (colon < 1) return null;
  const color = decode(rest.slice(0, colon));
  const label = rest.slice(colon + 1);
  return color && label ? { color, label } : null;
}

/** What an id asks to be drawn, or null for an id that is not ours. */
export function parseImageId(id: string): Drawing | null {
  const color = parsePinId(id);
  if (color) return { kind: "pin", color };
  const count = parseCountId(id);
  return count ? { kind: "count", ...count } : null;
}

const PIN_WIDTH = 20;
const PIN_HEIGHT = 28;
const RING = 1.5;

/** The CSS-pixel size of the image for a drawing. */
export function sizeOf(drawing: Drawing): { width: number; height: number } {
  if (drawing.kind === "pin") return { width: PIN_WIDTH, height: PIN_HEIGHT };
  const diameter = 22 + 5 * (drawing.label.length - 1);
  return { width: diameter, height: diameter };
}

function paintPin(ctx: CanvasRenderingContext2D, color: string): void {
  ctx.beginPath();
  ctx.moveTo(10, 27);
  ctx.bezierCurveTo(5, 21, 2, 15, 2, 10);
  ctx.arc(10, 10, 8, Math.PI, 0);
  ctx.bezierCurveTo(18, 15, 15, 21, 10, 27);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = RING;
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#ffffff";
  ctx.stroke();
}

function paintCount(
  ctx: CanvasRenderingContext2D,
  color: string,
  label: string,
  diameter: number
): void {
  const middle = diameter / 2;
  ctx.beginPath();
  ctx.arc(middle, middle, middle - RING / 2, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.lineWidth = RING;
  ctx.strokeStyle = "#ffffff";
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 12px sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, middle, middle);
}

/** Draw an image on a canvas, at `ratio` device pixels per CSS pixel. */
export function drawOnCanvas(drawing: Drawing, ratio: number): Pixels {
  const { width, height } = sizeOf(drawing);
  const canvas = document.createElement("canvas");
  canvas.width = Math.ceil(width * ratio);
  canvas.height = Math.ceil(height * ratio);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("no 2D canvas for generated images");
  ctx.scale(ratio, ratio);
  if (drawing.kind === "pin") paintPin(ctx, drawing.color);
  else paintCount(ctx, drawing.color, drawing.label, width);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

export interface ImageOptions {
  ratio?(): number;
  draw?(drawing: Drawing, ratio: number): Pixels;
}

/**
 * Serve the pin and count images the style asks for. MapLibre waits for the
 * resolver before treating an image as missing, so the request that names
 * one gets its pixels at once. Returns a function that removes the resolver.
 */
export function installImages(
  map: ImageMap,
  options: ImageOptions = {}
): () => void {
  const ratio = options.ratio ?? (() => window.devicePixelRatio || 1);
  const draw = options.draw ?? drawOnCanvas;
  map.setMissingStyleImageResolver(async (id) => {
    const drawing = parseImageId(id);
    if (!drawing || map.hasImage(id)) return;
    const pixelRatio = ratio();
    map.addImage(id, draw(drawing, pixelRatio), { pixelRatio });
  });
  return () => void map.setMissingStyleImageResolver(null);
}
