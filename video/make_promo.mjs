// Builds the promo video: title cards (video/cards.html) and real footage of the
// static replay (web/dist), recorded frame by frame through the Chrome DevTools
// screencast, cut to the voice-over in video/script.json, then mixed with the
// synthesized score from video/sound.py.
//
//   (cd web && npm run build:replay)
//   node video/make_promo.mjs                  -> video/out/last-witness-promo.mp4 and GIFs
//   node video/make_promo.mjs ask verdict      -> re-record only those scenes (for tuning)
//
// The voice-over is read from LW_VOICE_DIR/<scene>.wav (Kokoro-82M renders, see
// video/README.md). Without it, scenes are timed from the script and stay silent.
// Needs Playwright with Chromium, ffmpeg and python3 with numpy.
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { extname, join, resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = resolve(new URL("..", import.meta.url).pathname);
const DIST = join(ROOT, "web", "dist");
const OUT = join(ROOT, "video", "out");
const W = 1920, H = 1080, FPS = 30, XF = 0.5, LEAD = 0.5, TAIL = 0.8;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".svg": "image/svg+xml", ".woff2": "font/woff2" };
const only = process.argv.slice(2);
const VOICE_DIR = process.env.LW_VOICE_DIR ?? "";

if (!existsSync(join(DIST, "replay", "session.json"))) {
  console.error("web/dist has no replay. Run: (cd web && npm run build:replay)");
  process.exit(1);
}
const server = createServer((req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
  const base = url.startsWith("/video/") ? ROOT : DIST;
  const path = join(base, url.endsWith("/") ? url + "index.html" : url);
  if (!path.startsWith(base) || !existsSync(path)) { res.writeHead(404).end(); return; }
  res.writeHead(200, { "content-type": TYPES[extname(path)] ?? "application/octet-stream" }).end(readFileSync(path));
}).listen(0);
const BASE = `http://127.0.0.1:${server.address().port}`;
const session = JSON.parse(readFileSync(join(DIST, "replay", "session.json"), "utf8"));
const sealed = JSON.parse(readFileSync(join(DIST, "replay", "sealed.json"), "utf8"));
const artifacts = JSON.parse(readFileSync(join(DIST, "replay", "artifacts.json"), "utf8")).artifacts;
const script = Object.fromEntries(JSON.parse(readFileSync(join(ROOT, "video", "script.json"), "utf8")).lines.map((l) => [l.id, l.text]));
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

function voice(id) {
  const wav = VOICE_DIR && join(VOICE_DIR, `${id}.wav`);
  if (wav && existsSync(wav)) {
    const d = +execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]).toString();
    return { wav, dur: d };
  }
  return { wav: null, dur: script[id].split(/\s+/).length / 2.6 };
}

// Subtitles: the voice-over, a clause at a time, timed by length.
function subtitles(text, dur) {
  const parts = text.match(/[^.,:?!]+[.,:?!]*/g).map((s) => s.trim()).filter(Boolean);
  const chunks = [];
  for (const p of parts) {
    const last = chunks[chunks.length - 1];
    if (last && (last + " " + p).length < 70 && !/[.?!]$/.test(last)) chunks[chunks.length - 1] = last + " " + p;
    else chunks.push(p);
  }
  const total = chunks.reduce((s, c) => s + c.length, 0);
  let t = 0;
  return chunks.map((c) => { const at = t; t += (c.length / total) * dur; return { at, text: c }; });
}

// Subtitles, a visible cursor and a camera, injected into the game for the recording only.
const OVERLAY = `
(() => {
  const css = \`
    @font-face { font-family: "IBM Plex Mono"; src: url(/video/fonts/ibm-plex-mono-latin-400-normal.woff2) format("woff2"); }
    #pv-sub { position: fixed; left: 50%; bottom: 44px; transform: translateX(-50%); z-index: 9999; max-width: 1500px; text-align: center;
      font: 34px/1.35 "IBM Plex Mono", ui-monospace, monospace; color: #f4efe2; background: rgba(0,0,0,.78); padding: 10px 24px;
      border-radius: 4px; opacity: 0; transition: opacity .25s; pointer-events: none; }
    #pv-sub.on { opacity: 1; }
    #pv-cur { position: fixed; z-index: 10000; width: 26px; height: 26px; margin: -13px 0 0 -13px; border-radius: 50%;
      border: 3px solid #ffb347; background: rgba(255,179,71,.25); pointer-events: none; transition: transform .15s; left: -60px; top: -60px;
      box-shadow: 0 0 18px rgba(255,170,60,.6); }
    #pv-cur.down { transform: scale(.55); background: rgba(255,179,71,.8); }
    #root { transform-origin: 0 0; transition: transform 1.1s cubic-bezier(.45,0,.2,1); }\`;
  const install = () => {
    if (document.getElementById("pv-sub")) return;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    const sub = document.createElement("div"); sub.id = "pv-sub"; document.body.appendChild(sub);
    const cur = document.createElement("div"); cur.id = "pv-cur"; document.body.appendChild(cur);
    addEventListener("mousemove", (e) => { cur.style.left = e.clientX + "px"; cur.style.top = e.clientY + "px"; }, true);
    addEventListener("mousedown", () => cur.classList.add("down"), true);
    addEventListener("mouseup", () => cur.classList.remove("down"), true);
    window.__sub = (t) => { if (!t) { sub.classList.remove("on"); return; } sub.textContent = t; sub.classList.add("on"); };
    // camera: bring page point (cx, cy) to the middle of the frame at scale s, never showing past the edges
    window.__cam = (cx, cy, s) => {
      const W = innerWidth, H = innerHeight, r = document.getElementById("root");
      const tx = Math.min(0, Math.max(W - s * W, W / 2 - s * cx)), ty = Math.min(0, Math.max(H - s * H, H / 2 - s * cy));
      r.style.transform = s === 1 ? "none" : \`translate(\${tx}px, \${ty}px) scale(\${s})\`;
    };
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", install); else install();
})();`;

async function record(name, dur, fn, url, pre, subs) {
  const dir = join(OUT, "frames", name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  if (!url) await page.addInitScript(OVERLAY);
  await page.goto(url ?? BASE + "/");
  if (!url) {
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForLoadState("networkidle");
    // the cards already tell the intro; open the game straight on the archive
    await page.getByRole("button", { name: "Mount the tape" }).click();
    await page.locator(".panel.archive").waitFor();
    if (pre) await pre(page);
  }
  await page.evaluate(() => document.fonts.ready);
  await pause(300);

  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on("Page.screencastFrame", async (f) => {
    frames.push({ t: f.metadata.timestamp, data: f.data });
    try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch { /* closed */ }
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: W, maxHeight: H });
  const t0 = Date.now() / 1000;
  const timers = subs.map((s) => setTimeout(() => page.evaluate((x) => window.__sub(x), s.text).catch(() => {}), (LEAD + s.at) * 1000));
  timers.push(setTimeout(() => page.evaluate(() => window.__sub(null)).catch(() => {}), (dur - 0.35) * 1000));
  try { await fn(page); } catch (e) {
    await page.screenshot({ path: join(OUT, `fail-${name}.png`) });
    throw e;
  }
  const left = dur - (Date.now() / 1000 - t0);
  if (left < 0) console.warn(`scene ${name}: actions ran ${(-left).toFixed(1)} s past its ${dur.toFixed(1)} s; the end is cut`);
  if (left > 0) await pause(left * 1000);
  await cdp.send("Page.stopScreencast");
  timers.forEach(clearTimeout);
  await browser.close();

  // Each frame lasts until the next one; the last one holds to the end of the scene.
  const list = [];
  frames.forEach((f, i) => {
    const file = join(dir, `${String(i).padStart(5, "0")}.jpg`);
    writeFileSync(file, Buffer.from(f.data, "base64"));
    if (i + 1 < frames.length) list.push(`file '${file}'`, `duration ${Math.max(0.001, frames[i + 1].t - f.t).toFixed(4)}`);
  });
  const lastT = frames[frames.length - 1].t - frames[0].t;
  const lastFile = `file '${join(dir, String(frames.length - 1).padStart(5, "0") + ".jpg")}'`;
  // the concat demuxer ignores the last entry's duration, so the last frame goes in twice
  list.push(lastFile, `duration ${Math.max(0.05, dur - lastT).toFixed(4)}`, lastFile);
  writeFileSync(join(dir, "list.txt"), "ffconcat version 1.0\n" + list.join("\n") + "\n");
  const mp4 = join(OUT, "scenes", `${name}.mp4`);
  mkdirSync(join(OUT, "scenes"), { recursive: true });
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", join(dir, "list.txt"),
    "-vf", `scale=${W}:${H}:flags=lanczos,fps=${FPS},tpad=stop_mode=clone:stop_duration=${dur},format=yuv420p`, "-t", String(dur),
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", mp4]);
  console.log(`scene ${name}: ${frames.length} frames, ${dur.toFixed(1)}s`);
  return mp4;
}

// ---- helpers for the game footage -------------------------------------------------
async function cam(page, loc, s = 1.6) {
  if (!loc) { await page.evaluate(() => window.__cam(0, 0, 1)); await pause(1150); return; }
  // measure untransformed: reset, read, then move the camera
  const b = await page.evaluate(async ([sel, nth]) => {
    const r = document.getElementById("root"), prev = r.style.transition;
    r.style.transition = "none"; const keep = r.style.transform; r.style.transform = "none";
    // first selector that matches wins: "a, b" falls back to b
    const el = sel.split(",").map((x) => document.querySelectorAll(x.trim())[nth] ?? document.querySelector(x.trim())).find(Boolean);
    const box = el.getBoundingClientRect();
    r.style.transform = keep; void r.offsetWidth; r.style.transition = prev;
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  }, [loc.sel, loc.nth ?? 0]);
  await page.evaluate(([x, y, k]) => window.__cam(x, y, k), [b.x, b.y, s]);
  await pause(1150);
}
async function glide(page, loc, { click = true } = {}) {
  const b = await loc.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 22 });
  await pause(220);
  if (click) { await page.mouse.down(); await pause(90); await page.mouse.up(); }
}
async function openFile(page, path) {
  const a = artifacts.find((x) => x.path === path);
  const folder = page.locator(".folder-name", { hasText: a.folder }).first();
  if ((await folder.getAttribute("aria-expanded")) !== "true") { await glide(page, folder); await pause(400); }
  await glide(page, page.locator(".folder").filter({ has: folder }).locator(`.file[title="${a.title}"]`).first());
}
const question = (re) => (session.messages.find((m) => m.role === "player" && re.test(m.text)) ?? session.messages[0]).text;

// ---- the cut -----------------------------------------------------------------------
// [id, minimum seconds, actions, card url, setup before recording]
const card = (id) => `${BASE}/video/cards.html#${id}`;
const SCENES = [
  ["cold", 9.5, async () => {}, card("cold")],
  ["tape", 8, async () => {}, card("tape")],
  ["explore", 16.5, async (p) => {
    await pause(400);
    await openFile(p, "/forum/signals/thread_046.html");
    await cam(p, { sel: ".panel.viewer" }, 1.35);
    await pause(1500);
    await cam(p, null);
    await openFile(p, "/~eward/index.html");
    await cam(p, { sel: ".panel.viewer" }, 1.45);
    await pause(1600);
    await cam(p, null);
    await glide(p, p.getByRole("button", { name: /View source/ }));
    await pause(500);
    await cam(p, { sel: "mark.srcmark", nth: 1 }, 2.1);
    await pause(2200);
  }],
  ["partner", 8.5, async () => {}, card("partner")],
  ["ask", 13, async (p) => {
    await cam(p, { sel: ".panel.investigator" }, 1.7);
    await glide(p, p.locator(".replay-qs button", { hasText: question(/genuine/) }));
    await p.locator(".msg.ai .answer").first().waitFor({ timeout: 10000 });
    await pause(2600);
    const cite = p.locator(".msg.ai button.cite").first();
    if (await cite.count()) {
      await glide(p, cite);
      await pause(500);
      await cam(p, { sel: ".s.hl, .panel.viewer" }, 1.8);
      await pause(2200);
    }
  }],
  ["rule", 7, async () => {}, card("rule")],
  ["reason", 8, async (p) => {
    await glide(p, p.getByRole("tab", { name: /Timeline/i }));
    await cam(p, { sel: ".timeline" }, 1.5);
    await pause(1300);
    await cam(p, null);
    await glide(p, p.getByRole("tab", { name: /Hypotheses|explanations/i }));
    await cam(p, { sel: ".hyps" }, 1.35);
    await pause(1500);
  }],
  ["reveal", 5, async () => {}, card("reveal")],
  ["verdict", 13.5, async (p) => {
    await cam(p, { sel: ".reveal-gate button.primary" }, 1.8);
    await glide(p, p.getByRole("button", { name: "Reveal" }));
    await pause(900);
    await cam(p, null);
    await pause(400);
    for (let i = 0; i < 4; i++) { await p.mouse.wheel(0, 260); await pause(600); }
    for (let i = 0; i < 6; i++) { await p.mouse.wheel(0, 320); await pause(550); }
    for (let i = 0; i < 8; i++) { await p.mouse.wheel(0, 460); await pause(400); }
  }, null, async (p) => {
    await p.getByRole("tab", { name: /Reconstruct/i }).click();
    for (const [qid, k] of Object.entries(sealed.key)) {
      const keys = Object.keys(sealed.evaluation.ai.rows.find((r) => r.id === qid).options);
      await p.locator(".opt").filter({ has: p.locator(`input[name="${qid}"]`) }).nth(keys.indexOf(k.observable ? k.answer : "unknown")).click();
    }
    await p.getByRole("tab", { name: /Reveal/i }).click();
    await p.getByRole("button", { name: "Reveal" }).waitFor();
  }],
  ["numbers", 10, async () => {}, card("numbers")],
  ["end", 8, async () => {}, card("end")],
];

mkdirSync(OUT, { recursive: true });
const plan = SCENES.map(([name, min, fn, url, pre]) => {
  const vo = voice(name);
  return { name, fn, url, pre, vo, dur: +Math.max(min, LEAD + vo.dur + TAIL).toFixed(2) };
});
const parts = [];
for (const s of plan) {
  if (only.length && !only.includes(s.name)) continue;
  parts.push(await record(s.name, s.dur, s.fn, s.url, s.pre, subtitles(script[s.name], s.vo.dur)));
}
server.close();
if (only.length) process.exit(0);

// Cross-fade the scenes, then lay the voice and the score under them.
const args = ["-y", "-loglevel", "error"];
parts.forEach((p) => args.push("-i", p));
let chain = "", prev = "[0:v]", offset = 0;
for (let i = 1; i < parts.length; i++) {
  offset += plan[i - 1].dur - XF;
  const out = i === parts.length - 1 ? "[v]" : `[x${i}]`;
  chain += `${prev}[${i}:v]xfade=transition=fade:duration=${XF}:offset=${offset.toFixed(3)}${out};`;
  prev = out;
}
let start = 0;
const cues = plan.map((s, i) => {
  const c = { name: s.name, start: +start.toFixed(3), dur: s.dur, card: !!s.url, vo: s.vo.wav, vo_at: +(start + LEAD).toFixed(3) };
  start += s.dur - XF;
  return c;
});
const total = start + XF;
writeFileSync(join(OUT, "cues.json"), JSON.stringify({ total, cues }, null, 1));
const silent = join(OUT, "silent.mp4");
execFileSync("ffmpeg", [...args, "-filter_complex", chain.replace(/;$/, ""), "-map", "[v]",
  "-c:v", "libx264", "-preset", "slow", "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent]);
const wav = join(OUT, "score.wav");
execFileSync("python3", [join(ROOT, "video", "sound.py"), join(OUT, "cues.json"), wav], { stdio: "inherit" });
const final = join(OUT, "last-witness-promo.mp4");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
  "-shortest", "-movflags", "+faststart", final]);
console.log(`wrote ${final} (${total.toFixed(1)} s)`);

// GIFs for the post, cut from the same game footage.
const vf = "fps=12,scale=1100:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=3";
for (const name of ["explore", "ask", "verdict"]) {
  const gif = join(OUT, `${name}.gif`);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", join(OUT, "scenes", `${name}.mp4`), "-vf", vf, gif]);
  console.log("wrote", gif);
}
