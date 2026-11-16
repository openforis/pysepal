// What the notification pill and its log show, run against NotificationUI.vue's
// own computed properties rather than its source text.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const script = source.split("<script>")[1].split("</script>")[0];
const literal = script
  .slice(script.search(/^export default/m) + "export default".length)
  .trim()
  .replace(/;\s*$/, "");

function mount(tasks, { reducedMotion = false } = {}) {
  const intervals = [];
  const environment = {
    window: { matchMedia: () => ({ matches: reducedMotion }) },
    setTimeout() {},
    setInterval(fn) {
      intervals.push(fn);
    },
  };
  const component = runInNewContext(`(${literal})`, environment);
  const vm = { ...component.data(), tasks, toasts: [], is_dark: false };
  for (const [name, getter] of Object.entries(component.computed)) {
    Object.defineProperty(vm, name, { get: getter.bind(vm) });
  }
  for (const [name, method] of Object.entries(component.methods)) {
    vm[name] = method.bind(vm);
  }
  component.mounted.call(vm);
  vm.tick = () => intervals.forEach((fn) => fn());
  return vm;
}

const running = (fields) => ({
  id: fields.title,
  status: "running",
  milestones: [],
  createdAt: 1,
  ...fields,
});

// The percentage floors: 99.5% is still running, not done.
let vm = mount([
  running({
    title: "Download",
    progress: 0.995,
    progressDetail: "tile 199/200",
  }),
]);
assert.equal(vm.pillPct, "99%");

// Title frame first, then the detail frame, then back.
assert.equal(vm.pillText, "Download");
assert.equal(vm.showDetailFrame, false);
vm.tick();
assert.equal(vm.showDetailFrame, true);
vm.tick();
assert.equal(vm.showDetailFrame, false);

// A detail on an indeterminate task stands alone, with no percentage.
vm = mount([
  running({ title: "Download", progress: null, progressDetail: "waiting" }),
]);
assert.equal(vm.pillPct, null);
assert.equal(vm.pillAlternates, true);

// No detail: no alternation, the title carries the last step.
vm = mount([running({ title: "Process", progress: 0.4, lastStep: "Compute" })]);
vm.tick();
assert.equal(vm.showDetailFrame, false);
assert.equal(vm.pillText, "Process — Compute");

// Reduced motion: one static line, the frames never alternate.
vm = mount(
  [running({ title: "Download", progress: 0.42, progressDetail: "tile 5/12" })],
  {
    reducedMotion: true,
  }
);
vm.tick();
assert.equal(vm.showDetailFrame, false);
assert.equal(vm.pillText, "Download · 42% tile 5/12");
