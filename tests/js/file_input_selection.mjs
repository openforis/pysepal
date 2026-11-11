// Drives FileInput.vue's own selection methods, so the browser side of
// multiple mode is tested rather than trusted.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const script = source.split("<script>")[1].split("</script>")[0];
const literal = script
  .slice(script.search(/^export default/m) + "export default".length)
  .trim()
  .replace(/;\s*$/, "");

let now = 10_000;
const component = runInNewContext(`(${literal})`, {
  window: {},
  Date: { now: () => now },
  setTimeout: () => 0,
});

function mount(props = {}) {
  const instance = { $refs: {}, $nextTick() {} };
  for (const [name, prop] of Object.entries(component.props)) {
    instance[name] =
      typeof prop.default === "function" ? prop.default() : prop.default;
  }
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
