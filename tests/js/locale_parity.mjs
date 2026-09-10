// Runs LocaleSelect.vue's own matcher over the shared fixture table, so the
// browser implementation is tested rather than trusted. ipyvue evaluates the
// `export default` object, so that is what this evaluates too.
import { readFileSync } from "node:fs";

const [vuePath, fixturePath] = process.argv.slice(2);

const script = readFileSync(vuePath, "utf8").split("<script>")[1].split("</script>")[0];
// Anchored to the start of a line: the header comment can mention the words.
const at = script.search(/^export default/m);
const literal = script.slice(at + "export default".length);
const component = new Function(`return (${literal.trim().replace(/;\s*$/, "")});`)();

const cases = JSON.parse(readFileSync(fixturePath, "utf8"));
const results = cases.map((testCase) =>
  component.methods.matchOffered.call(
    component.methods,
    testCase.candidate,
    testCase.offered
  )
);
process.stdout.write(JSON.stringify(results));
