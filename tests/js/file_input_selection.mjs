// Drives FileInput.js's own selection methods, so the browser side of
// multiple mode is tested rather than trusted.
//
// node file_input_selection.mjs <FileInput.js> <JSON of the widget's trait defaults>
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const script = readFileSync(process.argv[2], "utf8");
const traits = JSON.parse(process.argv[3]);

// Evaluated like ipyvue 1 does: a CommonJS body that sets module.exports
let now = 10_000;
const module = { exports: {} };
runInNewContext(script, {
  module,
  exports: module.exports,
  window: {},
  Date: { now: () => now },
  setTimeout: () => 0,
});
const component = module.exports;

// Like ipyvue, the synced traits are the component's data: the template must not
// declare them as props, which Vue 3 would read in their place.
assert.equal(component.props, undefined);

function mount(props = {}) {
  const instance = { $refs: {}, $nextTick() {}, ...structuredClone(traits) };
  Object.assign(instance, component.data(), props);
  for (const [name, method] of Object.entries(component.methods)) {
    instance[name] = method.bind(instance);
  }
  for (const [name, getter] of Object.entries(component.computed)) {
    Object.defineProperty(instance, name, { get: getter.bind(instance) });
  }
  return instance;
}

const file = (path) => ({ name: path.split("/").pop(), path, type: "file" });
const folder = (path) => ({
  name: path.split("/").pop(),
  path,
  type: "directory",
});

// single mode: a click selects one file and closes the menu, as before
const single = mount({ root: "/r", current_folder: "/r", showFileMenu: true });
single.onFileSelect(file("/r/a.csv"));
assert.equal(single.value, "/r/a.csv");
assert.equal(single.showFileMenu, false);
single.onFileSelect(folder("/r/sub"));
assert.equal(single.current_folder, "/r/sub");
single.reset();
assert.equal(single.value, "");

// multiple mode: a click toggles a file and leaves the menu open
const multi = mount({
  multiple: true,
  value: [],
  root: "/r",
  current_folder: "/r",
  showFileMenu: true,
});
assert.equal(multi.countLabel, "");
multi.onFileSelect(file("/r/a.csv"));
assert.deepEqual([...multi.value], ["/r/a.csv"]);
assert.equal(multi.showFileMenu, true);
assert.equal(multi.isSelected(file("/r/a.csv")), true);
assert.equal(multi.countLabel, "1 file");

// a click on a folder enters it, like single mode, and keeps the selection
multi.onFileSelect(folder("/r/sub"));
assert.equal(multi.current_folder, "/r/sub");
assert.deepEqual([...multi.value], ["/r/a.csv"]);

// the second click of a double click on the folder lands in the new listing
// and must not pick the file that took the folder's place
multi.onFileSelect(file("/r/sub/b.csv"));
assert.deepEqual([...multi.value], ["/r/a.csv"]);

now += 1000;
multi.onFileSelect(file("/r/sub/b.csv"));
assert.deepEqual([...multi.value], ["/r/a.csv", "/r/sub/b.csv"]);
assert.equal(multi.countLabel, "2 files");

// the value is replaced, not mutated, so the change syncs to Python
const before = multi.value;
multi.onFileSelect(file("/r/a.csv"));
assert.deepEqual([...multi.value], ["/r/sub/b.csv"]);
assert.deepEqual([...before], ["/r/a.csv", "/r/sub/b.csv"]);

// a row removed from the selected list (the v-select's change) is a new array
multi.onFileSelect(file("/r/sub/c.csv"));
const remaining = ["/r/sub/c.csv"];
multi.setSelection(remaining);
assert.deepEqual([...multi.value], ["/r/sub/c.csv"]);
assert.notEqual(multi.value, remaining);

// clearing clears every path
multi.reset();
assert.deepEqual([...multi.value], []);
assert.equal(multi.countLabel, "");

// a str value from Python before the first sync still reads as a list
assert.deepEqual([...mount({ multiple: true, value: "" }).selectedPaths], []);

// only files have a check, unless the app also selects folders
const files = mount({
  multiple: true,
  value: [],
  root: "/r",
  current_folder: "/r",
});
assert.equal(files.isCheckable(file("/r/a.csv")), true);
assert.equal(files.isCheckable(folder("/r/sub")), false);
assert.equal(mount().isCheckable(file("/r/a.csv")), false);

// with select_folders a folder is selected with its check; its row still opens it
const both = mount({
  multiple: true,
  select_folders: true,
  value: [],
  root: "/r",
  current_folder: "/r",
});
assert.equal(both.isCheckable(folder("/r/sub")), true);
assert.equal(
  both.isCheckable({ name: "..", path: "/", type: "directory" }),
  false
);
both.toggleFile(both.fullPath(folder("/r/sub")));
assert.deepEqual([...both.value], ["/r/sub"]);
assert.equal(both.isSelected(folder("/r/sub")), true);
assert.equal(both.countLabel, "1 item");
both.onFileSelect(folder("/r/sub"));
assert.equal(both.current_folder, "/r/sub");
assert.deepEqual([...both.value], ["/r/sub"]);

// theme colours are spelled for the Vuetify major the page runs
const csv = file("/r/a.csv");
const v2 = mount();
assert.equal(v2.getIconColor(csv), "secondary_contrast");
assert.match(v2.primaryColor, /--v-primary-base/);
const v3 = mount({ $vuetify: { theme: { global: { name: "light" } } } });
assert.equal(v3.getIconColor(csv), "secondary-contrast");
assert.equal(v3.getIconColor(folder("/r/sub")), "primary-contrast");
assert.equal(v3.primaryColor, "rgb(var(--v-theme-primary))");
assert.equal(Object.keys(v3.getItemStyle(0)).length, 0);
v3.selectedIndex = 0;
assert.equal(
  v3.getItemStyle(0).borderLeft,
  "3px solid rgb(var(--v-theme-primary))"
);
