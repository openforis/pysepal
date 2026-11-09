// Prints the drawer links MapApp.vue's own `externalLinks` computes for the
// props given as JSON, so the template logic is tested rather than trusted.
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

const [vuePath, propsJson] = process.argv.slice(2);

const script = readFileSync(vuePath, "utf8")
  .split("<script>")[1]
  .split("</script>")[0];
const literal = script
  .slice(script.search(/^export default/m) + "export default".length)
  .trim()
  .replace(/;\s*$/, "");
const component = runInNewContext(`(${literal})`, { window: {} });

const links = component.computed.externalLinks.call(JSON.parse(propsJson));
process.stdout.write(JSON.stringify(links));
