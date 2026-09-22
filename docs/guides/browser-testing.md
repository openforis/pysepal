# Browser testing with headless Chrome (CDP)

pysepal apps render to a real browser DOM through several layers (ipywidgets →
ipyvue/ipyvuetify → Vuetify, under either `solara run` or Voila). Unit tests
exercise the Python render tree, but they can't tell you what a _browser_
actually paints — computed colors, font sizes, theme classes, z-index, layout.
`scripts/browser_probe.mjs` closes that gap: it drives a **headless Chrome**
over the DevTools Protocol and evaluates JavaScript in the live page, so you can
assert on the rendered result and **compare the same app across runtimes**.

It has no dependencies beyond Node ≥ 22 and a Chrome/Chromium binary.

## When to use it

- Debugging a visual difference (theme, spacing, fonts) between `solara run` and
  Voila — inspect the _computed_ styles side by side instead of eyeballing.
- Confirming a CSS/`.vue` fix actually lands in the browser before asking a
  human to reload — iterate without round-trips.
- Any "what does this render to?" question: does this element exist, what color
  is it, how many of them are there, which theme class is applied.

It is **not** a replacement for `nox -s test`. Use it for rendered-DOM
questions; use pytest for Python logic.

## Prerequisites

- Node ≥ 22 (built-in global `WebSocket` — the script needs no npm install).
- `google-chrome` / `chromium` on `PATH` (or pass `--chrome <path>`).
- The app already running locally, e.g.:
  - Solara: `./run_solara.sh demo_apps/solara_map_app/app.py --port 8900`
  - Voila: `voila <notebook>.ipynb --port 8910`

## Quickstart

```bash
# Simplest: read the page title
node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ --eval "({ title: document.title })"

# Wait for a real element to mount, settle, then run the example diagnostic
node scripts/browser_probe.mjs \
  --url http://127.0.0.1:8910/ \
  --wait '.pill-wrapper' --settle 2500 \
  --eval @scripts/probe.example.js
```

Output is pretty-printed JSON on stdout, so it pipes into `jq`, `python -m json.tool`,
or a diff.

### Compare two runtimes

Run the same probe against both ports and diff:

```bash
node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ --wait '.pill-wrapper' --eval @scripts/probe.example.js > /tmp/solara.json
node scripts/browser_probe.mjs --url http://127.0.0.1:8910/ --wait '.pill-wrapper' --eval @scripts/probe.example.js > /tmp/voila.json
diff <(jq -S . /tmp/solara.json) <(jq -S . /tmp/voila.json)
```

## Interacting before you measure

Some questions are only answerable by _doing_ something first — does clicking
outside dismiss this dialog, does the scrim resize cleanly. `--click` and
`--resize` run before `--eval`, so the expression measures the result:

```bash
# does clicking outside dismiss the dialog?
node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ \
  --wait '.v-dialog--active' --click 12,-12 --settle-after 1500 \
  --eval "({ open: !!document.querySelector('.v-dialog--active') })"

# does the scrim track a viewport resize, or animate to it?
node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ \
  --wait '.v-overlay' --resize 1000x700 --settle-after 50 \
  --eval "(() => { const r = document.querySelector('.v-overlay__scrim').getBoundingClientRect();
                   return { w: Math.round(r.width), vw: window.innerWidth }; })()"
```

**Use `--click` rather than clicking from `--eval`.** A click dispatched from JS
(`el.click()`, `new MouseEvent(...)`) is untrusted, and vuetify's click-outside
directive drops untrusted events on purpose (`if ('isTrusted' in e && !e.isTrusted) return false`). Driving it from `--eval` will tell you that
dismissing a dialog is broken when it works perfectly.

`--settle-after` defaults to 1200ms because widget round-trips go through the
python kernel — far slower than a repaint. If a result looks negative, raise it
before concluding anything.

## Writing a probe

A probe is **one JavaScript expression** evaluated in the page. Read the DOM and
`getComputedStyle(...)` and return a **JSON-serializable** object. An IIFE is the
usual shape (see `scripts/probe.example.js`):

```js
(() => {
  const el = document.querySelector(".solara-markdown");
  return {
    present: !!el,
    color: el ? getComputedStyle(el).color : null,
    // resolve a CSS variable exactly as the browser sees it
    pillBg: (() => {
      const b = document.querySelector(".pill-log-btn");
      return b
        ? getComputedStyle(b).getPropertyValue("--pill-bg").trim()
        : null;
    })(),
  };
})();
```

Pass it inline with `--eval "(...)"` or from a file with `--eval @path/to/probe.js`.

## Options

| Flag                        | Meaning                                                                                                                                                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--url <url>`               | **required** — page to load                                                                                                                                                              |
| `--eval <expr\|@file>`      | expression to evaluate (or `@file`); must return JSON-serializable data                                                                                                                  |
| `--wait <selector>`         | poll until this selector exists (else `--timeout`)                                                                                                                                       |
| `--settle <ms>`             | extra wait after ready, for layout/theme (default 2000)                                                                                                                                  |
| `--click <x,y\|selector>`   | issue a **real (trusted)** click before `--eval` — coordinates, or the centre of a selector. Negative coordinates count back from the right/bottom edge. Repeatable; clicks run in order |
| `--resize <WxH>`            | resize the viewport before `--eval` (e.g. `1000x700`)                                                                                                                                    |
| `--scale <n>`               | device scale factor for `--resize` (default 1); `2` gives a retina-sharp `--screenshot`                                                                                                  |
| `--settle-after <ms>`       | wait after each `--click`/`--resize` (default 1200)                                                                                                                                      |
| `--wait-js <expr>`          | after the clicks, poll until this expression is truthy (same `--timeout` budget), e.g. until every leaflet tile has loaded                                                               |
| `--screenshot <png>`        | write a PNG of the viewport after `--eval`                                                                                                                                               |
| `--timeout <ms>`            | readiness budget (default 30000)                                                                                                                                                         |
| `--force-theme dark\|light` | set the Solara and pysepal theme keys in localStorage and reload (Voila ignores them)                                                                                                    |
| `--chrome <path>`           | Chrome binary (default: autodetect)                                                                                                                                                      |
| `--keep-open`               | leave Chrome running (to debug the probe itself)                                                                                                                                         |

## Worked example: the Solara/Voila theme-parity hunt

This tool was written to chase notification/markdown styling that differed
between `solara run` and Voila. The probes proved, in order:

1. `getComputedStyle('.solara-markdown').color` was near-black in Voila dark mode
   but themed correctly under Solara → JupyterLab's base CSS owns the
   `--jp-content-*` vars in Voila (fix: `.solara-markdown { color: inherit }`).
2. The notification pill's resolved `--pill-bg` was the _light_ value even though
   its own root was `theme-dark` → the culprit ancestor was
   `document.body` carrying JupyterLab's single-dash **`theme-light`** class,
   which collides with pysepal's notification theme classes; ipyvue renders
   `<style scoped>` as _global_ CSS, so the descendant selector
   `.theme-light .pill-wrapper` reached across (fix: anchor with the child
   combinator, `.theme-light > .pill-wrapper`).
3. `toast_stack_count`/`pill_wrapper_count` were both `1` → the earlier
   "double-mounted notification" suspicion was wrong; nothing to fix there.

Each conclusion came from a computed-style read, not a guess.

## Gotchas & limitations

- **Fresh session, not your tab.** Each run spins up a new browser session and,
  for server apps, a fresh kernel — it does **not** reuse your logged-in tab.
  Great for reproducibility; auth-gated pages may render empty.
- **`<style scoped>` is not scoped here.** ipyvue injects Vue scoped styles as
  global CSS (elements get no `data-v-*` attribute), so computed styles can be
  affected by ancestor classes from the host page (Jupyter sets `theme-light`
  on `<body>`). Probe computed styles to catch this; prefer child combinators or
  namespaced classes in `.vue` theme rules.
- **The viewport is not `--window-size`.** Headless Chrome may report a much
  smaller `window.innerHeight` than the window you asked for. Derive click
  coordinates from `window.innerWidth/innerHeight` — which `--click` does for
  you — instead of hardcoding, or you will click past the page and hit `<html>`.
- **Bind dialogs with a real two-way model.** A fixture built with a constant
  (ipyvuetify `Dialog(v_model=True)` with no handler) reopens the instant
  vuetify closes it, so it can never _appear_ to dismiss. Use a reactive plus
  `on_v_model` or you will measure your own fixture.
- **Theme defaults differ.** Solara defaults dark via a `localStorage` flag that
  applies on the _next_ load; a first headless load may render light. Use
  `--force-theme dark` (Solara) or drive the app's own theme toggle.
- **Don't `pkill -f` your own launcher.** A pattern like
  `pkill -f remote-debugging-port=9222` also matches the shell running your
  script (the string is in its argv) and kills it. The script kills only the
  Chrome PID it spawned — follow that rule in any wrapper you write.
- **Restricted sandboxes.** Inside some CI/agent sandboxes Chrome is
  signal-killed on launch; run from a normal shell (the `--no-sandbox` flag the
  script passes is for Chrome's own sandbox, a separate thing).
- **Interactions.** The probe can click/type via more CDP calls, but the script
  ships read-only by default. Extend it with `Input.dispatchMouseEvent` or by
  evaluating `el.click()` if you need to drive a flow (e.g. toggle the theme and
  re-read).
