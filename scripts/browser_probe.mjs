#!/usr/bin/env node
/**
 * browser_probe.mjs — drive a headless Chrome against a URL over the Chrome
 * DevTools Protocol (CDP) and evaluate JavaScript in the live page, printing
 * the (JSON-serialized) result to stdout.
 *
 * Purpose
 * -------
 * A dependency-free way to *test pysepal apps the way a browser sees them* —
 * inspect the rendered DOM, read computed styles, assert theme/layout state,
 * or compare the same app across runtimes (e.g. `solara run` vs Voila). It was
 * written to debug Solara/Voila styling parity, but it is a general tool: any
 * question of the form "what does this actually render to?" can be answered by
 * passing a probe expression.
 *
 * Requirements
 * ------------
 *   - Node >= 22 (uses the built-in global `WebSocket`; no npm install).
 *   - A Chrome/Chromium binary on PATH (or pass --chrome <path>).
 *
 * Usage
 * -----
 *   node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ \
 *        --wait '.pill-wrapper' --settle 2500 --eval @scripts/probe.example.js
 *
 *   node scripts/browser_probe.mjs --url http://127.0.0.1:8910/ \
 *        --eval "({ title: document.title })"
 *
 *   # dismiss a dialog by clicking the scrim, then check it actually closed
 *   node scripts/browser_probe.mjs --url http://127.0.0.1:8900/ \
 *        --wait '.v-dialog--active' --click 12,-12 --settle-after 1500 \
 *        --eval "({ open: !!document.querySelector('.v-dialog--active') })"
 *
 * Options
 * -------
 *   --url <url>          (required) page to load
 *   --eval <expr|@file>  JS expression to evaluate, or @path to a .js file
 *                        holding one expression (an IIFE is the usual shape).
 *                        Must return a JSON-serializable value. Default: title
 *                        + body text length.
 *   --wait <selector>    poll until this selector exists (else --timeout)
 *   --settle <ms>        extra wait after ready, for layout/theme (default 2000)
 *   --click <x,y|sel>    issue a REAL (trusted) click before --eval, either at
 *                        viewport coordinates or at the centre of a selector.
 *                        Negative coordinates count back from the right/bottom
 *                        edge, so `12,-12` is 12px in from the bottom-left.
 *                        Repeatable; clicks run in order, each followed by
 *                        --settle-after.
 *   --resize <WxH>       resize the viewport before --eval (e.g. 1000x700)
 *   --scale <n>          device scale factor for --resize (default 1); 2 gives
 *                        a retina-sharp --screenshot
 *   --settle-after <ms>  wait after each --click/--resize (default 1200).
 *                        Widget round-trips go through the python kernel, so a
 *                        UI change can take far longer than a repaint.
 *   --wait-js <expr>     after the clicks, poll until this expression is truthy
 *                        (same --timeout budget), e.g. until every leaflet tile
 *                        has loaded
 *   --screenshot <png>   write a PNG of the viewport after --eval
 *   --timeout <ms>       readiness budget (default 30000)
 *   --force-theme <t>    set the Solara and pysepal theme keys in localStorage
 *                        to "dark" or "light" and reload (Voila ignores them)
 *   --chrome <path>      Chrome binary (default: autodetect)
 *   --keep-open          leave Chrome running (debugging the probe itself)
 *
 * Notes / gotchas (learned the hard way)
 * --------------------------------------
 *   - Each run creates a FRESH browser session and, for server apps, a fresh
 *     kernel — it does NOT reuse your logged-in tab. That's usually what you
 *     want for reproducibility, but auth-gated pages may render empty.
 *   - Never clean up Chrome with `pkill -f <pattern>` where <pattern> also
 *     appears in the launching script's own argv — it matches (and kills) your
 *     own shell. This tool tracks the spawned PID and kills only that.
 *   - Inside a restricted sandbox Chrome may be signal-killed on launch; run it
 *     from a normal shell, or disable the sandbox for the launching command.
 *   - A click dispatched from JS (`el.click()`, `new MouseEvent(...)`) is NOT
 *     trusted, and vuetify's click-outside directive drops untrusted events on
 *     purpose. Use --click, which goes through CDP `Input.dispatchMouseEvent`,
 *     or you will "prove" that dismissing a dialog is broken when it is not.
 *   - The headless viewport is NOT the --window-size: derive click coordinates
 *     from `window.innerWidth/innerHeight` (which --click does) rather than
 *     hardcoding, or you will click outside the page and hit <html>.
 *   - ipyvue injects Vue `<style scoped>` as GLOBAL css (no data-v attribute),
 *     so computed styles can be affected by ancestor classes you don't expect
 *     (e.g. JupyterLab sets `theme-light` on <body>). Probing computed styles
 *     is how you catch that.
 */
import { spawn, execSync } from "node:child_process";
import { setTimeout as sleep } from "node:timers/promises";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function argVal(name, def) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : def;
}

function argAll(name) {
  return process.argv.flatMap((a, i) =>
    a === name && i + 1 < process.argv.length ? [process.argv[i + 1]] : []
  );
}

const URL = argVal("--url");
if (!URL) {
  console.error("--url is required. See the header of this file for usage.");
  process.exit(2);
}
const WAIT = argVal("--wait");
const SETTLE = parseInt(argVal("--settle", "2000"), 10);
const TIMEOUT = parseInt(argVal("--timeout", "30000"), 10);
const FORCE_THEME = argVal("--force-theme");
const KEEP_OPEN = process.argv.includes("--keep-open");
const CLICKS = argAll("--click");
const RESIZE = argVal("--resize");
const SCALE = parseFloat(argVal("--scale", "1"));
const WAIT_JS = argVal("--wait-js");
const SCREENSHOT = argVal("--screenshot");
const SETTLE_AFTER = parseInt(argVal("--settle-after", "1200"), 10);
let EVAL = argVal("--eval");
if (EVAL && EVAL.startsWith("@")) EVAL = readFileSync(EVAL.slice(1), "utf8");
if (!EVAL)
  EVAL =
    "({ title: document.title, bodyTextLen: document.body.innerText.length })";

function findChrome() {
  const explicit = argVal("--chrome");
  if (explicit) return explicit;
  for (const c of [
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
  ]) {
    try {
      return execSync(`command -v ${c}`, {
        stdio: ["ignore", "pipe", "ignore"],
      })
        .toString()
        .trim();
    } catch {
      /* try next */
    }
  }
  throw new Error("No chrome/chromium found on PATH; pass --chrome <path>");
}

// ---- minimal CDP client over the built-in WebSocket ----
let msgId = 0;
const pending = new Map();

function send(ws, method, params = {}, sessionId) {
  const id = ++msgId;
  const payload = { id, method, params };
  if (sessionId) payload.sessionId = sessionId;
  ws.send(JSON.stringify(payload));
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => {
      pending.delete(id);
      reject(new Error("CDP timeout: " + method));
    }, 20000);
    pending.set(id, {
      resolve: (v) => {
        clearTimeout(t);
        resolve(v);
      },
      reject: (e) => {
        clearTimeout(t);
        reject(e);
      },
    });
  });
}

async function evaluate(ws, sessionId, expr) {
  // Evaluate `expr` as-is. Runtime.evaluate returns the completion value, so
  // both a parenthesized expression `({...})` and an IIFE statement
  // `(() => {...})();` work. (Wrapping in extra parens would break the latter.)
  const r = await send(
    ws,
    "Runtime.evaluate",
    { expression: expr, returnByValue: true, awaitPromise: true },
    sessionId
  );
  if (r.exceptionDetails)
    throw new Error("eval error: " + JSON.stringify(r.exceptionDetails));
  return r.result.value;
}

async function main() {
  const chromeBin = findChrome();
  const udd = mkdtempSync(join(tmpdir(), "browser-probe-"));
  const chrome = spawn(
    chromeBin,
    [
      "--headless=new",
      "--no-sandbox",
      "--disable-gpu",
      "--disable-dev-shm-usage",
      "--no-first-run",
      "--no-default-browser-check",
      `--user-data-dir=${udd}`,
      "--remote-debugging-port=0", // ephemeral; real port is printed to stderr
      "--remote-allow-origins=*",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] }
  );

  const cleanup = () => {
    if (KEEP_OPEN) return;
    try {
      chrome.kill("SIGKILL");
    } catch {}
    try {
      rmSync(udd, { recursive: true, force: true });
    } catch {}
  };
  process.on("exit", cleanup);
  process.on("SIGINT", () => {
    cleanup();
    process.exit(130);
  });

  // Chrome prints "DevTools listening on ws://127.0.0.1:<port>/devtools/browser/..."
  const wsUrl = await new Promise((resolve, reject) => {
    let buf = "";
    const to = setTimeout(
      () => reject(new Error("Chrome never reported a DevTools endpoint")),
      15000
    );
    chrome.stderr.on("data", (d) => {
      buf += d.toString();
      const m = buf.match(/ws:\/\/\S+/);
      if (m) {
        clearTimeout(to);
        resolve(m[0]);
      }
    });
    chrome.on("exit", (code) => {
      clearTimeout(to);
      reject(new Error("Chrome exited early (code " + code + ")"));
    });
  });

  const ws = await new Promise((resolve, reject) => {
    const s = new WebSocket(wsUrl);
    s.addEventListener("open", () => resolve(s), { once: true });
    s.addEventListener(
      "error",
      () => reject(new Error("WebSocket connect failed")),
      { once: true }
    );
  });
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const p = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) p.reject(new Error(JSON.stringify(msg.error)));
      else p.resolve(msg.result);
    }
  });

  const { targetId } = await send(ws, "Target.createTarget", { url: URL });
  const { sessionId } = await send(ws, "Target.attachToTarget", {
    targetId,
    flatten: true,
  });
  await send(ws, "Page.enable", {}, sessionId);
  await send(ws, "Runtime.enable", {}, sessionId);

  const waitFor = async (expr) => {
    const start = Date.now();
    while (Date.now() - start < TIMEOUT) {
      try {
        if (await evaluate(ws, sessionId, expr)) return;
      } catch {
        /* keep polling */
      }
      await sleep(500);
    }
    throw new Error(`timed out after ${TIMEOUT}ms waiting for: ${expr}`);
  };
  const waitReady = () =>
    waitFor(
      WAIT
        ? `!!document.querySelector(${JSON.stringify(WAIT)})`
        : `document.readyState === 'complete'`
    );

  await waitReady();
  await sleep(SETTLE);

  if (FORCE_THEME === "dark" || FORCE_THEME === "light") {
    await evaluate(
      ws,
      sessionId,
      `localStorage.setItem(':solara:theme.variant', '"${FORCE_THEME}"'),
       localStorage.setItem(':sepalUi:theme.variant', '"${FORCE_THEME}"'), true`
    );
    await send(ws, "Page.reload", {}, sessionId);
    await waitReady();
    await sleep(SETTLE);
  }

  if (RESIZE) {
    const m = /^(\d+)x(\d+)$/.exec(RESIZE);
    if (!m) throw new Error(`--resize expects WxH, got "${RESIZE}"`);
    await send(
      ws,
      "Emulation.setDeviceMetricsOverride",
      {
        width: parseInt(m[1], 10),
        height: parseInt(m[2], 10),
        deviceScaleFactor: SCALE,
        mobile: false,
      },
      sessionId
    );
    await sleep(SETTLE_AFTER);
  }

  for (const CLICK of CLICKS) {
    // Resolve to viewport coordinates in the page, so the caller never has to
    // guess the headless viewport size.
    const point = await evaluate(
      ws,
      sessionId,
      `(() => {
        const spec = ${JSON.stringify(CLICK)};
        const coords = /^(-?\\d+),(-?\\d+)$/.exec(spec);
        if (coords) {
          const x = +coords[1], y = +coords[2];
          return { x: x < 0 ? window.innerWidth + x : x,
                   y: y < 0 ? window.innerHeight + y : y };
        }
        const el = document.querySelector(spec);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) };
      })()`
    );
    if (!point) throw new Error(`--click found no element for "${CLICK}"`);

    for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) {
      await send(
        ws,
        "Input.dispatchMouseEvent",
        {
          type,
          x: point.x,
          y: point.y,
          ...(type === "mouseMoved" ? {} : { button: "left", clickCount: 1 }),
        },
        sessionId
      );
    }
    await sleep(SETTLE_AFTER);
  }

  if (WAIT_JS) await waitFor(WAIT_JS);

  const value = await evaluate(ws, sessionId, EVAL);
  console.log(JSON.stringify(value, null, 2));

  if (SCREENSHOT) {
    const { data } = await send(
      ws,
      "Page.captureScreenshot",
      { format: "png", captureBeyondViewport: false },
      sessionId
    );
    writeFileSync(SCREENSHOT, Buffer.from(data, "base64"));
    console.error(`screenshot written to ${SCREENSHOT}`);
  }

  try {
    await send(ws, "Target.closeTarget", { targetId });
  } catch {}
  ws.close();
  cleanup();
}

main().catch((e) => {
  console.error("ERROR:", e.message);
  process.exit(1);
});
