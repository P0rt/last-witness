// Renders the still figures in video/figures.html (how it works, results,
// citations) to PNG for the README and the post, into web/public/media/.
//
//   node video/render_figures.mjs
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

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
for (const id of ["how", "results", "citations"]) {
  await page.goto(PAGE);
  await page.evaluate((id) => {
    document.querySelectorAll(".fig").forEach((f) => f.classList.toggle("on", f.id === id));
    return document.fonts.ready;
  }, id);
  await page.locator(`#${id}`).screenshot({ path: join(OUT, `${id}.png`) });
  console.log(`wrote web/public/media/${id}.png`);
}
await browser.close();
