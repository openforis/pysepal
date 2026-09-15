import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const source = readFileSync(process.argv[2], "utf8");
const script = source.split("<script>")[1].split("</script>")[0];
const selectedCondition = source.match(/<v-list-item-action v-if="([^"]+)"/)[1];
const literal = script
  .slice(script.search(/^export default/m) + "export default".length)
  .trim()
  .replace(/;\s*$/, "");

function browser(stored = "", language = "en", blocked = false) {
  const writes = [];
  const environment = {
    window: {},
    navigator: { language },
    console: { warn() {} },
    localStorage: {
      getItem(key) {
        assert.equal(key, ":sepalUi:locale");
        if (blocked) throw new Error("Storage is blocked");
        return stored;
      },
      setItem(key, value) {
        assert.equal(key, ":sepalUi:locale");
        if (blocked) throw new Error("Storage is blocked");
        stored = value;
        writes.push(value);
      },
    },
  };
  const component = runInNewContext(`(${literal})`, environment);
  return {
    writes,
    environment,
    mount(value = "en", offered = ["en", "fr", "es", "pt-BR"]) {
      const instance = {
        ...component.data(),
        value,
        available_locales: offered.map((code) => ({ code })),
      };
      for (const [name, method] of Object.entries(component.methods)) {
        instance[name] = method.bind(instance);
      }
      component.created.call(instance);
      component.mounted.call(instance);
      return instance;
    },
  };
}

function selectedCodes(instance) {
  return instance.available_locales
    .filter((locale) =>
      runInNewContext(selectedCondition, { ...instance, locale })
    )
    .map((locale) => locale.code);
}

assert.equal(browser("fr", "es").mount().value, "fr");
assert.equal(browser("missing", "pt_br").mount().value, "pt-BR");
assert.equal(browser("", "missing").mount("fr").value, "en");
assert.equal(browser("", "missing").mount("en", ["fr"]).value, "fr");
assert.equal(browser("fr", "es", true).mount().value, "es");

const tab = browser("fr", "es");
const first = tab.mount();
assert.deepEqual(tab.writes, []);
first.openDialog();
first.selectLanguage("pt-BR");
assert.equal(first.value, "pt-BR");
assert.equal(first.dialogOpen, false);
assert.deepEqual(tab.writes, ["pt-BR"]);
first.selectLanguage("pt-BR");
assert.deepEqual(tab.writes, ["pt-BR"]);

first.value = "en";
tab.environment.localStorage.setItem(":sepalUi:locale", "es");
assert.equal(tab.mount(first.value).value, "en");
assert.equal(browser("es", "fr").mount().value, "es");

const blocked = browser("", "fr", true).mount();
blocked.selectLanguage("es");
assert.equal(blocked.value, "es");

const props = process.argv[3]
  ? JSON.parse(process.argv[3])
  : { value: "pt-BR", offered: ["en", "pt_br"] };
const alternate = browser("en", "en");
const alternateFirst = alternate.mount("en", props.offered);
alternateFirst.value = props.value;
assert.deepEqual(selectedCodes(alternateFirst), ["pt_br"]);
alternateFirst.selectLanguage("pt_br");
assert.equal(alternateFirst.value, props.value);
assert.deepEqual(alternate.writes, []);
const alternateRemount = alternate.mount(alternateFirst.value, props.offered);
assert.equal(alternateRemount.value, props.value);
assert.deepEqual(selectedCodes(alternateRemount), ["pt_br"]);
assert.deepEqual(alternate.writes, []);

process.stdout.write("Locale browser lifecycle passed\n");
