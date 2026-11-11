// Runs LocaleSelect.vue's own matcher over the shared fixture table, so the
// browser implementation is tested rather than trusted. Only the object given
// to `module.exports` is evaluated, as ipyvue does.
import { readFileSync } from "node:fs";

const [vuePath, fixturePath] = process.argv.slice(2);

const source = readFileSync(vuePath, "utf8");
const script = source.split("<script>")[1].split("</script>")[0];
const literal = script
  .slice(script.search(/^module\.exports\s*=/m))
  .replace(/^module\.exports\s*=/, "");
const component = new Function(
  `return (${literal.trim().replace(/;\s*$/, "")});`
)();

const cases = JSON.parse(readFileSync(fixturePath, "utf8"));
const results = cases.map((testCase) =>
  component.methods.matchOffered.call(
    component.methods,
    testCase.candidate,
    testCase.offered
  )
);
process.stdout.write(JSON.stringify(results));
