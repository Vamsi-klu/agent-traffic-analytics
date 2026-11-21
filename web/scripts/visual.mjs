// Visual regression: screenshot the component overview + 8 pages (light, 1280 wide) in both styles (Cake <page>.png,
// Minimal <page>-minimal.png: shots.mjs STYLES) and compare pixel by pixel with visual/baseline/. Any changed pixel
// fails; the diff images go to visual/diff/. The dashboard and the session list show cake's own answers on the fixed
// test library at a fixed moment (shots.mjs LIBRARY_PAGES);
// the registration card is a fresh AgentCake's first page (shots.mjs PAGE_ANSWERS). Both ways it also draws the favicon
// from the same build and fails while public/favicon.ico is not that file (scripts/favicon.mjs writes it).
// Usage: npm run build && npm run visual            (compare)
//        npm run build && npm run visual:update     (accept the current look as the new baseline; commit it with the change)
import { mkdir, readFile, writeFile } from "node:fs/promises"
import { existsSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { PNG } from "pngjs"
import pixelmatch from "pixelmatch"
import { drawFavicon, staleFavicon } from "./favicon.mjs"
import { LIBRARY } from "./fixture-api.mjs"
import { LIBRARY_PAGES, PAGE_ANSWERS, STYLES, launch, pickStyle, serve, shoot, withAnswers } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.join(here, "..", "visual")
const update = process.argv.includes("--update")
const PAGES = { components: "#/components", home: "#/", dashboard: "#/dashboard", sessions: "#/sessions", "sessions-agent": "#/sessions?filter=agent&turns=human_agent",
  session: "#/sessions/7f3a-c1", "session-freed": "#/sessions/2b9e-c4", settings: "#/settings", register: "#/" }

for (const d of ["baseline", "actual", "diff"]) await mkdir(path.join(root, d), { recursive: true })
const srv = await serve(), lib = await serve(undefined, { fixtures: LIBRARY })
const origin = `http://127.0.0.1:${srv.address().port}/`, libOrigin = `http://127.0.0.1:${lib.address().port}/`
const browser = await launch()
let failed = 0
const shots = Object.entries(PAGES).map(([name, route]) => [name, () => (LIBRARY_PAGES.includes(name) ? libOrigin : origin) + "index.html" + route])
for (const style of STYLES) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: "light", reducedMotion: "reduce", deviceScaleFactor: 1 })
  await pickStyle(ctx, style)
  const page = await ctx.newPage()
  for (const [shot, url] of shots) {
    const buf = await withAnswers(page, PAGE_ANSWERS[shot], async () => {
      await shoot(page, await url())
      return page.screenshot({ fullPage: true, animations: "disabled", caret: "hide" })
    })
    failed += await compare(style === "cake" ? shot : `${shot}-${style}`, buf)
  }
  await ctx.close()
}

/** One screenshot against its baseline (or written as the baseline): 1 when it differs, else 0. */
async function compare(name, buf) {
  const basePath = path.join(root, "baseline", `${name}.png`)
  if (update || !existsSync(basePath)) { await writeFile(basePath, buf); console.log(`${name}: baseline ${update ? "updated" : "created"}`); return 0 }
  await writeFile(path.join(root, "actual", `${name}.png`), buf)
  const a = PNG.sync.read(await readFile(basePath)), b = PNG.sync.read(buf)
  if (a.width !== b.width || a.height !== b.height) { console.log(`${name}: FAIL size ${a.width}x${a.height} -> ${b.width}x${b.height}`); return 1 }
  const diff = new PNG({ width: a.width, height: a.height })
  const n = pixelmatch(a.data, b.data, diff.data, a.width, a.height, { threshold: 0.1 })
  if (n > 0) { await writeFile(path.join(root, "diff", `${name}.png`), PNG.sync.write(diff)); console.log(`${name}: FAIL ${n} pixels differ (visual/diff/${name}.png)`); return 1 }
  console.log(`${name}: same as baseline`)
  return 0
}
const faviconProblems = staleFavicon(await drawFavicon(browser, origin))
for (const problem of faviconProblems) console.log(`favicon: FAIL ${problem}: run node scripts/favicon.mjs and commit it`)
if (faviconProblems.length) failed++
else console.log("favicon: same as scripts/favicon.mjs draws")
await browser.close(); srv.close(); lib.close()
process.exit(failed ? 1 : 0)
