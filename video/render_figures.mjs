// Renders the still figures in video/figures.html (how it works, results,
// citations) to PNG for the README and the post, into web/public/media/.
// With --site DIR it also writes 2x renders for a blog, a wide one and a
// stacked <name>-mobile.png for phones, as DIR/last-witness-<name>.png.
//
//   node video/render_figures.mjs
//   node video/render_figures.mjs --site ../resume/src/assets
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const ROOT = resolve(new URL("..", import.meta.url).pathname);
const OUT = join(ROOT, "web", "public", "media");
const PAGE = pathToFileURL(join(ROOT, "video", "figures.html")).href;
mkdirSync(OUT, { recursive: true });

const FIGS = ["how", "results", "citations"];
const siteAt = process.argv.indexOf("--site");
const SITE = siteAt > 0 ? resolve(process.argv[siteAt + 1]) : null;

async function render(page, id, path) {
  await page.goto(PAGE);
  await page.evaluate((id) => {
    document.querySelectorAll(".fig").forEach((f) => f.classList.toggle("on", f.id === id));
    return document.fonts.ready;
  }, id);
  await page.locator(`#${id}`).screenshot({ path });
}

const browser = await chromium.launch();
if (SITE) {
  for (const [suffix, width] of [["", 1600], ["-mobile", 800]]) {
    const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: 2 });
    for (const id of FIGS) {
      await render(page, id, join(SITE, `last-witness-${id}${suffix}.png`));
      console.log(`wrote ${SITE}/last-witness-${id}${suffix}.png`);
    }
    await page.close();
  }
  await browser.close();
  process.exit(0);
}
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
for (const id of FIGS) {
  await render(page, id, join(OUT, `${id}.png`));
  console.log(`wrote web/public/media/${id}.png`);
}
await browser.close();
