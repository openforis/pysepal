import { build, context } from "esbuild";

const options = {
  entryPoints: { widget: "js/index.ts" },
  outdir: "src/pysepal_map/static",
  bundle: true,
  format: "esm",
  minify: true,
  loader: { ".css": "css" },
  logLevel: "info",
};

if (process.argv.includes("--watch")) {
  const ctx = await context(options);
  await ctx.watch();
} else {
  await build(options);
}
