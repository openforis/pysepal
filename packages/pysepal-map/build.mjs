import { build, context } from "esbuild";

const widget = {
  entryPoints: { widget: "js/index.ts" },
  outdir: "src/pysepal_map/static",
  bundle: true,
  format: "esm",
  minify: true,
  loader: { ".css": "css" },
  logLevel: "info",
};

// Test-only probes, injected into the page by the browser tests.
const harness = {
  entryPoints: ["tests/browser/harness.ts"],
  outfile: "tests/browser/.build/harness.js",
  bundle: true,
  format: "iife",
  logLevel: "info",
};

const options = process.argv.includes("--harness") ? harness : widget;

if (process.argv.includes("--watch")) {
  const ctx = await context(options);
  await ctx.watch();
} else {
  await build(options);
}
