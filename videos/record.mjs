// Record a demo take of the running app, frame by frame, over the Chrome DevTools protocol.
// Real mouse events drive the app (hover states and clicks are the app's own); the cursor,
// window and wallpaper are drawn afterwards by videos/compose.py.
//
//   node videos/record.mjs --take videos/demos/inspect-kit.mjs --out out/social/inspect-kit [--still]
//
// Writes <out>-frames/NNNNN.png (2x) and <out>-track.json, then runs compose.py.

import { spawn, execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const argv = process.argv.slice(2), args = {};
for (let i = 0; i < argv.length; i++) {
  if (!argv[i].startsWith("--")) continue;
  const next = argv[i + 1];
  args[argv[i].slice(2)] = next === undefined || next.startsWith("--") ? true : next;
}
const W = +(args.width || 1200), H = +(args.height || 1200), PAD = +(args.pad || 40), BAR = 36;
const FPS = +(args.fps || 30), SCALE = 2, PORT = 9334;
const VW = W - 2 * PAD, VH = H - 2 * PAD - BAR;  // the app's viewport, CSS px
const out = path.resolve(args.out), framesDir = `${out}-frames`;
const take = await import(path.resolve(args.take));
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

fs.rmSync(framesDir, { recursive: true, force: true });
fs.mkdirSync(framesDir, { recursive: true });
const profile = fs.mkdtempSync("/tmp/inspec-rec-");
const chrome = spawn(CHROME, ["--headless=new", "--disable-gpu", "--hide-scrollbars",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 50 && !target; i++) {
  try { target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json(); }
  catch { await sleep(200); }
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
let nextId = 0; const pending = {};
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (pending[d.id]) { pending[d.id](d); delete pending[d.id]; } };
await new Promise((r) => (ws.onopen = r));
const send = (method, params = {}) => new Promise((r) => { pending[++nextId] = r; ws.send(JSON.stringify({ id: nextId, method, params })); })
  .then((d) => { if (d.error) throw new Error(`${method}: ${d.error.message}`); return d.result; });
const evaluate = async (expression) => (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result.value;

await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: VW, height: VH, deviceScaleFactor: SCALE, mobile: false });
await send("Page.navigate", { url: take.url });
await sleep(take.loadMs ?? 9000);
await evaluate(`(() => { const s = document.createElement("style"); s.textContent = ${JSON.stringify(
  "*{caret-color:transparent!important} ::-webkit-scrollbar{display:none} " + (take.css || ""))}; document.head.append(s); })()`);
await sleep(500);

// --- the take API -------------------------------------------------------------------------
let seed = +(args.seed || 1);
const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const track = { width: W, height: H, pad: PAD, bar: BAR, scale: SCALE, fps: FPS, frames: [], poster: null };
let cx = VW * 0.55, cy = VH * 0.6, ripple = null;

async function frame() {
  const kind = await evaluate(`(() => { const e = document.elementFromPoint(${cx}, ${cy});
    if (!e) return "arrow"; const c = getComputedStyle(e).cursor;
    return c === "pointer" || e.closest("button,a,[role=option],[data-baseweb=select],label") ? "hand" : "arrow"; })()`);
  const { data } = await send("Page.captureScreenshot", { format: "png" });
  const n = track.frames.length;
  fs.writeFileSync(path.join(framesDir, `${String(n).padStart(5, "0")}.png`), Buffer.from(data, "base64"));
  track.frames.push({ x: cx, y: cy, kind, ripple: ripple !== null ? n - ripple : null });
  if (ripple !== null && n - ripple > 12) ripple = null;
}
const frames = (ms) => Math.max(1, Math.round((ms / 1000) * FPS));
const mouse = (type, extra = {}) => send("Input.dispatchMouseEvent", { type, x: cx, y: cy, ...extra });

const t = {
  width: VW, height: VH, fps: FPS, random, evaluate,
  async hold(ms) { for (let i = 0; i < frames(ms); i++) await frame(); },
  async moveTo(x, y, { ms, bow = 0.12 } = {}) {
    const x0 = cx, y0 = cy, dist = Math.hypot(x - x0, y - y0);
    const n = frames(ms ?? Math.min(900, 250 + dist * 0.9));
    const nx = -(y - y0) / (dist || 1), ny = (x - x0) / (dist || 1), b = dist * bow * (random() - 0.3);
    for (let i = 1; i <= n; i++) {
      const s = i / n, e = s < 0.5 ? 4 * s ** 3 : 1 - (-2 * s + 2) ** 3 / 2;  // ease in-out
      const arc = Math.sin(Math.PI * e) * b;
      cx = x0 + (x - x0) * e + nx * arc; cy = y0 + (y - y0) * e + ny * arc;
      await mouse("mouseMoved"); await frame();
    }
  },
  // A box is {x, y, w, h} in viewport CSS px, from a JS expression that returns an element.
  async box(expr) {
    for (let i = 0; i < 40; i++) {
      const b = await evaluate(`(() => { const e = (${expr}); if (!e) return null;
        const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; })()`);
      if (b && b.w) return b;
      await sleep(250);
    }
    throw new Error(`not found: ${expr}`);
  },
  aim(b, fx = 0.5, fy = 0.5) {
    return [b.x + b.w * fx + (random() - 0.5) * Math.min(8, b.w * 0.1),
            b.y + b.h * fy + (random() - 0.5) * Math.min(4, b.h * 0.1)];
  },
  async hover(expr, { fx, fy, dwell = 360, ms } = {}) {
    const [x, y] = t.aim(await t.box(expr), fx, fy); await t.moveTo(x, y, { ms }); await t.hold(dwell);
  },
  async click() {
    await mouse("mousePressed", { button: "left", clickCount: 1 });
    ripple = track.frames.length; await frame();
    await mouse("mouseReleased", { button: "left", clickCount: 1 });
  },
  async clickOn(expr, { fx, fy, dwell = 160, settle = 200 } = {}) {
    await t.hover(expr, { fx, fy, dwell }); await t.click(); await t.hold(settle);
  },
  async type(text, { perChar = 90 } = {}) {
    for (const ch of text) { await send("Input.insertText", { text: ch }); await t.hold(perChar * (0.7 + random() * 0.6)); }
  },
  async wheel(dy, { ms = 700 } = {}) {
    const n = frames(ms), ease = (s) => 0.5 - Math.cos(Math.PI * s) / 2;
    for (let i = 0; i < n; i++) {
      await mouse("mouseWheel", { deltaX: 0, deltaY: dy * (ease((i + 1) / n) - ease(i / n)) }); await frame();
    }
  },
  async waitFor(expr, timeoutMs = 30000) {  // real time; frames keep rolling while waiting
    const end = Date.now() + timeoutMs;
    while (!(await evaluate(`!!(${expr})`))) { if (Date.now() > end) throw new Error(`timeout: ${expr}`); await frame(); }
  },
  poster() { track.poster = track.frames.length; },
};

try {
  if (args.still) {
    if (take.still) await take.still(t);
    await frame(); track.poster = 0;
  } else {
    await take.default(t);
  }
} finally {
  fs.writeFileSync(`${out}-track.json`, JSON.stringify(track));
  ws.close();
  const exited = new Promise((r) => chrome.once("exit", r));
  chrome.kill(); await exited;
  fs.rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
console.log(`${track.frames.length} frames -> ${framesDir}`);
execFileSync(process.env.PYTHON || ".venv/bin/python", [path.resolve("videos/compose.py"), out,
  ...(args.still ? ["--still"] : [])], { stdio: "inherit" });
