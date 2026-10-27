// Builds the promo video: title cards (video/cards.html) and real footage of the
// static replay (web/dist), recorded frame by frame through the Chrome DevTools
// screencast, then cut together with ffmpeg and scored by video/sound.py.
//
//   (cd web && npm run build:replay)
//   node video/make_promo.mjs                  -> video/out/last-witness-promo.mp4 and GIFs
//   node video/make_promo.mjs ask verdict      -> re-record only those scenes (for tuning)
//
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
const W = 1920, H = 1080, FPS = 30;
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json", ".svg": "image/svg+xml" };
const only = process.argv.slice(2);

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
const pause = (ms) => new Promise((r) => setTimeout(r, ms));

// Captions and a visible cursor, injected into the game for the recording only.
const OVERLAY = `
(() => {
  const css = \`
    html { zoom: 1.25; }
    #pv-cap { position: fixed; left: 50%; bottom: 46px; transform: translateX(-50%); z-index: 9999; max-width: 1300px;
      font: 600 30px/1.3 "Inter Display", Inter, system-ui, sans-serif; color: #f1f3ea; text-align: center;
      background: rgba(8,10,9,.88); border: 1px solid #3a4a40; border-left: 5px solid #e8b04a; padding: 16px 30px;
      border-radius: 6px; opacity: 0; transition: opacity .45s, transform .45s; pointer-events: none; zoom: .8; }
    #pv-cap.on { opacity: 1; }
    #pv-cur { position: fixed; z-index: 10000; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
      border: 2px solid #e8b04a; background: rgba(232,176,74,.25); pointer-events: none; transition: transform .15s; left: -50px; top: -50px; }
    #pv-cur.down { transform: scale(.6); background: rgba(232,176,74,.7); }\`;
  const install = () => {
    if (document.getElementById("pv-cap")) return;
    const s = document.createElement("style"); s.textContent = css; document.head.appendChild(s);
    const cap = document.createElement("div"); cap.id = "pv-cap"; document.body.appendChild(cap);
    const cur = document.createElement("div"); cur.id = "pv-cur"; document.body.appendChild(cur);
    const z = 1.25;
    addEventListener("mousemove", (e) => { cur.style.left = e.clientX / z + "px"; cur.style.top = e.clientY / z + "px"; }, true);
    addEventListener("mousedown", () => cur.classList.add("down"), true);
    addEventListener("mouseup", () => cur.classList.remove("down"), true);
    window.__cap = (t) => { if (!t) { cap.classList.remove("on"); return; } cap.textContent = t; cap.classList.add("on"); };
  };
  if (document.readyState === "loading") addEventListener("DOMContentLoaded", install); else install();
})();`;

async function record(name, dur, fn, url) {
  const dir = join(OUT, "frames", name);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: W, height: H } });
  if (!url) await page.addInitScript(OVERLAY);
  await page.goto(url ?? BASE + "/");
  if (!url) { await page.evaluate(() => localStorage.clear()); await page.reload(); }
  await page.waitForLoadState("networkidle");
  if (!url) {  // the cards already tell the intro; open the game straight on the archive
    await page.getByRole("button", { name: "Mount the tape" }).click();
    await page.locator(".panel.archive").waitFor();
  }
  await pause(300);

  const cdp = await page.context().newCDPSession(page);
  const frames = [];
  cdp.on("Page.screencastFrame", async (f) => {
    frames.push({ t: f.metadata.timestamp, data: f.data });
    try { await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }); } catch { /* closed */ }
  });
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 90, maxWidth: W, maxHeight: H });
  const t0 = Date.now() / 1000;
  try { await fn(page); } catch (e) {
    await page.screenshot({ path: join(OUT, `fail-${name}.png`) });
    throw e;
  }
  const left = dur - (Date.now() / 1000 - t0);
  if (left < 0) console.warn(`scene ${name}: actions ran ${(-left).toFixed(1)} s past its ${dur} s; the end is cut`);
  if (left > 0) await pause(left * 1000);
  await cdp.send("Page.stopScreencast");
  await browser.close();

  // Each frame lasts until the next one; the last one holds to the end of the scene.
  const list = [];
  frames.forEach((f, i) => {
    const file = join(dir, `${String(i).padStart(5, "0")}.jpg`);
    writeFileSync(file, Buffer.from(f.data, "base64"));
    const next = i + 1 < frames.length ? frames[i + 1].t : f.t;
    list.push(`file '${file}'`, `duration ${Math.max(0.001, i + 1 < frames.length ? next - f.t : 0.001).toFixed(4)}`);
  });
  const lastT = frames.length ? frames[frames.length - 1].t - frames[0].t : 0;
  const lastFile = `file '${join(dir, String(frames.length - 1).padStart(5, "0") + ".jpg")}'`;
  // the concat demuxer ignores the last entry's duration, so the last frame goes in twice
  list.push(lastFile, `duration ${Math.max(0.05, dur - lastT).toFixed(4)}`, lastFile);
  writeFileSync(join(dir, "list.txt"), "ffconcat version 1.0\n" + list.join("\n") + "\n");
  const mp4 = join(OUT, "scenes", `${name}.mp4`);
  mkdirSync(join(OUT, "scenes"), { recursive: true });
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", join(dir, "list.txt"),
    "-vf", `scale=${W}:${H}:flags=lanczos,fps=${FPS},tpad=stop_mode=clone:stop_duration=${dur},format=yuv420p`, "-t", String(dur),
    "-c:v", "libx264", "-preset", "slow", "-crf", "17", mp4]);
  console.log(`scene ${name}: ${frames.length} frames, ${dur}s`);
  return mp4;
}

// ---- helpers for the game footage -------------------------------------------------
const cap = (page, t) => page.evaluate((x) => window.__cap(x), t);
async function glide(page, loc, { click = true } = {}) {
  await loc.scrollIntoViewIfNeeded();
  const b = await loc.boundingBox();
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2, { steps: 24 });
  await pause(250);
  if (click) { await page.mouse.down(); await pause(90); await page.mouse.up(); }
}
async function openFile(page, path) {
  const a = artifacts.find((x) => x.path === path);
  const folder = page.locator(".folder-name", { hasText: a.folder }).first();
  if ((await folder.getAttribute("aria-expanded")) !== "true") { await glide(page, folder); await pause(500); }
  await glide(page, page.locator(".folder").filter({ has: folder }).locator(`.file[title="${a.title}"]`).first());
}
const mount = async (page) => { await pause(600); };
const question = (re) => (session.messages.find((m) => m.role === "player" && re.test(m.text)) ?? session.messages[0]).text;

// ---- the cut -----------------------------------------------------------------------
const card = (id) => `${BASE}/video/cards.html#${id}`;
const SCENES = [
  ["cold", 8.5, async () => {}, card("cold")],
  ["tape", 8.5, async () => {}, card("tape")],
  ["explore", 18, async (p) => {
    await mount(p);
    await cap(p, "58 files survived. Forum threads, 1999 home pages, mail, server logs.");
    await openFile(p, "/forum/signals/thread_046.html");
    await pause(2600);
    await cap(p, "Open a page the way it looked in 1999. Or view its source.");
    await openFile(p, "/~eward/index.html");
    await pause(2400);
    await glide(p, p.getByRole("button", { name: /View source/ }));
    await pause(1200);
    const mark = p.locator("mark.srcmark").last();
    if (await mark.count()) await mark.scrollIntoViewIfNeeded();
    await cap(p, "Some evidence is only in HTML comments nobody was meant to read.");
    await pause(3000);
  }],
  ["partner", 7, async () => {}, card("partner")],
  ["ask", 16, async (p) => {
    await mount(p);
    await cap(p, "Ask it anything about what you have found.");
    const q = question(/genuine/);
    await glide(p, p.locator(".replay-qs button", { hasText: q }));
    await p.locator(".msg.ai .answer").first().waitFor({ timeout: 10000 });
    await pause(1200);
    await cap(p, "Every claim comes with the sentence it stands on.");
    await p.mouse.wheel(0, 200);
    await pause(2600);
    const cite = p.locator(".msg.ai button.cite").first();
    if (await cite.count()) {
      await cap(p, "Click a citation, and the exact sentence lights up.");
      await glide(p, cite);
      await pause(3600);
    }
  }],
  ["rule", 7.5, async () => {}, card("rule")],
  ["reason", 13.5, async (p) => {
    await mount(p);
    await glide(p, p.getByRole("tab", { name: /Timeline/i }));
    await cap(p, "It rebuilds the timeline, marking every date it had to guess.");
    await pause(3600);
    await glide(p, p.getByRole("tab", { name: /Hypotheses|explanations/i }));
    await cap(p, "And weighs four competing explanations against the evidence.");
    await pause(1500);
    await p.mouse.wheel(0, 300);
    await pause(2200);
  }],
  ["reveal", 7, async () => {}, card("reveal")],
  ["verdict", 21, async (p) => {
    await mount(p);
    await glide(p, p.getByRole("tab", { name: /Reconstruct/i }));
    await cap(p, "Fill in your reconstruction. The AI's answers stay sealed.");
    for (const [qid, k] of Object.entries(sealed.key)) {
      const keys = Object.keys(sealed.evaluation.ai.rows.find((r) => r.id === qid).options);
      const choice = k.observable ? k.answer : "unknown";
      const opt = p.locator(".opt").filter({ has: p.locator(`input[name="${qid}"]`) }).nth(keys.indexOf(choice));
      await opt.scrollIntoViewIfNeeded();
      await opt.click();
      await pause(140);
    }
    await glide(p, p.getByRole("tab", { name: /Reveal/i }));
    await pause(700);
    await cap(p, null);
    await glide(p, p.getByRole("button", { name: "Reveal" }));
    await pause(1800);
    await cap(p, "The truth, the AI and you, side by side.");
    for (let i = 0; i < 5; i++) { await p.mouse.wheel(0, 260); await pause(650); }
    await cap(p, "The ghosts: things it said that the archive never did.");
    for (let i = 0; i < 6; i++) { await p.mouse.wheel(0, 300); await pause(650); }
    await cap(p, "And the people of the Lighthouse Network, remembered accurately.");
    for (let i = 0; i < 8; i++) { await p.mouse.wheel(0, 420); await pause(450); }
  }],
  ["numbers", 9.5, async () => {}, card("numbers")],
  ["end", 8, async () => {}, card("end")],
];

mkdirSync(OUT, { recursive: true });
const parts = [];
const cues = [];
let t = 0;
for (const [name, dur, fn, url] of SCENES) {
  if (only.length && !only.includes(name)) { t += dur; continue; }
  parts.push(await record(name, dur, fn, url));
  cues.push({ name, start: +t.toFixed(3), dur, card: !!url });
  t += dur;
}
server.close();
if (only.length) process.exit(0);

// Cross-fade the scenes, then lay the score under them.
const XF = 0.6;
const args = ["-y", "-loglevel", "error"];
parts.forEach((p) => args.push("-i", p));
let chain = "", prev = "[0:v]", offset = 0;
for (let i = 1; i < parts.length; i++) {
  offset += SCENES[i - 1][1] - XF;
  const out = i === parts.length - 1 ? "[v]" : `[x${i}]`;
  chain += `${prev}[${i}:v]xfade=transition=fade:duration=${XF}:offset=${offset.toFixed(3)}${out};`;
  prev = out;
}
const total = SCENES.reduce((s, x) => s + x[1], 0) - XF * (SCENES.length - 1);
// cue times shift by the cross-fades
const shifted = cues.map((c, i) => ({ ...c, start: +(c.start - XF * i).toFixed(3) }));
writeFileSync(join(OUT, "cues.json"), JSON.stringify({ total, cues: shifted }, null, 1));
const silent = join(OUT, "silent.mp4");
execFileSync("ffmpeg", [...args, "-filter_complex", chain.replace(/;$/, ""), "-map", "[v]",
  "-c:v", "libx264", "-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent]);
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
