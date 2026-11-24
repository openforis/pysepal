import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { build, context } from "esbuild";

// Plain ES syntax for the worker import: prettier 2 cannot parse
// `import ... with { type: "text" }`.
const workerAsText = {
  name: "psm-maplibre-worker",
  setup(b) {
    const file = createRequire(import.meta.url).resolve(
      "maplibre-gl/dist/maplibre-gl-worker.mjs"
    );
    b.onResolve({ filter: /^psm:maplibre-worker$/ }, () => ({
      path: file,
      namespace: "psm-worker",
    }));
    // The worker runs from a blob URL, where its map comment would point
    // DevTools at a file the page root does not serve.
    b.onLoad({ filter: /.*/, namespace: "psm-worker" }, async (args) => ({
      contents: (await readFile(args.path, "utf8")).replace(
        /\n\/\/# sourceMappingURL=\S+\s*$/,
        "\n"
      ),
      loader: "text",
    }));
  },
};

const widget = {
  entryPoints: { widget: "js/index.ts" },
  outdir: "src/pysepal_map/static",
  bundle: true,
  format: "esm",
  minify: true,
  loader: { ".css": "css" },
  plugins: [workerAsText],
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
