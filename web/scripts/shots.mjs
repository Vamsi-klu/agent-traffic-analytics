// Screenshot the built app (dist/) 1280 and 485px wide, in both styles (Cake, then Minimal: STYLES), and fail on
// horizontal scroll.
// The pages read /api, answered here from src/data/fixtures/ (scripts/fixture-api.mjs), so every shot shows the same data:
// the dashboard and the session list (LIBRARY_PAGES) show cake's own answers on the fixed test library at a fixed moment
// (fixtures/library/), the other pages the samples, all behind a registered AgentCake
// (fixtures/register.json), and the registration card is a fresh AgentCake's first page (PAGE_ANSWERS).
// Usage: npm run build && node scripts/shots.mjs [outDir] [route ...]
// Browser: Playwright's Chromium; set CAKE_CHROME to its executable if it is not found automatically.
import { createServer } from "node:http"
import { readFile, mkdir } from "node:fs/promises"
import { existsSync, readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { chromium } from "playwright-core"
import { cakeStatic } from "./cake-static.mjs"
import { LIBRARY, fixtureApi } from "./fixture-api.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const dist = path.join(here, "..", "dist")
export const ROUTES = { home: "#/", components: "#/components", dashboard: "#/dashboard", sessions: "#/sessions", "sessions-agent": "#/sessions?filter=agent&turns=human_agent",
  session: "#/sessions/7f3a-c1", "session-tabs": "#/sessions/4c2d-71", "session-freed": "#/sessions/2b9e-c4", settings: "#/settings", register: "#/" }
/** The pages shot on real data: the fixed test library's answers. */
export const LIBRARY_PAGES = ["dashboard", "sessions"]
/** Pages shot with some answers swapped for other samples, { page: { url glob: sample } }: the registration card is
 *  what an AgentCake opened for the first time shows. */
export const PAGE_ANSWERS = { register: { "**/api/register": "register/first-run" } }
const fixtures = path.join(here, "..", "src", "data", "fixtures")
/** The pages' two styles (src/lib/style.ts): files of Cake's shots have no ending, Minimal's end in -minimal / _minimal. */
export const STYLES = ["cake", "minimal"]

/** Opens every page of the context in `style` as the top bar's Style menu leaves it: the choice this browser keeps
 *  (lib/style.ts STORAGE_KEY). A browser that picked nothing shows Minimal, the default. */
export async function pickStyle(ctx, style) {
  await ctx.addInitScript((picked) => {
    if (location.protocol.startsWith("http")) localStorage.setItem("agentcake-style", picked) // about:blank has no storage
  }, style)
}

/** shot() with the page's requests to each glob of answers answered by its sample (just shot() when answers is unset):
 *  in a fresh document before and after, since moving between the app's # routes keeps it loaded, and what it asked
 *  once (as whether this AgentCake has registered) it doesn't ask again. */
export async function withAnswers(page, answers, shot) {
  if (!answers) return shot()
  await page.goto("about:blank")
  for (const [glob, name] of Object.entries(answers)) {
    const json = JSON.parse(readFileSync(path.join(fixtures, `${name}.json`), "utf8"))
    await page.route(glob, (route) => route.fulfill({ json }))
  }
  try {
    return await shot()
  } finally {
    await page.unrouteAll()
    await page.goto("about:blank")
  }
}
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".ttf": "font/ttf", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png" }

/** The built app (dist/, or `root`) with the fixture /api and the player's /static/ files: the release's paths. fixtures: the sample set to answer from first (LIBRARY), as fixtureApi takes it. */
export function serve(root = dist, { fixtures } = {}) {
  const api = fixtureApi({ set: fixtures }), player = cakeStatic()
  const file = async (req, res) => {
    const p = path.join(root, decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/\/$/, "/index.html"))
    let body
    try { body = await readFile(p) } catch { res.writeHead(404); res.end(); return }
    res.writeHead(200, { "content-type": TYPES[path.extname(p)] || "application/octet-stream" }); res.end(body)
  }
  return new Promise((resolve) => {
    const srv = createServer((req, res) => {
      if (req.url.startsWith("/api/")) return api(req, res)
      if (req.url.startsWith("/static/")) return player(req, res)
      return file(req, res)
    })
    srv.listen(0, "127.0.0.1", () => resolve(srv))
  })
}

/** Chromium switches that make a screenshot the same pixels on every run however busy the machine is: everything drawn on
 *  the CPU (GPU rasterizing antialiased a thin diagonal, like Crumb's cherry stem, a pixel differently under load), every
 *  raster and compositing stage finished before a frame is shown, no partial re-raster, Skia's generic CPU paths, sRGB
 *  and greyscale text antialiasing. */
const STABLE_RENDERING = ["--disable-gpu", "--disable-gpu-rasterization", "--disable-partial-raster", "--run-all-compositor-stages-before-draw",
  "--disable-skia-runtime-opts", "--force-color-profile=srgb", "--disable-lcd-text", "--disable-threaded-animation", "--disable-threaded-scrolling",
  "--disable-checker-imaging"]

export async function launch() {
  const guess = path.join(process.env.HOME, "Library/Caches/ms-playwright/chromium-1228/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing")
  const executablePath = process.env.CAKE_CHROME || (existsSync(guess) ? guess : undefined)
  return chromium.launch({ executablePath, args: STABLE_RENDERING })
}

export async function shoot(page, url) {
  await page.goto(url, { waitUntil: "networkidle" })
  // The page drawn: the app mounted and no page's data still on its way (components/cake/page-state.tsx). A quiet
  // network alone is no sign: a busy machine pauses that long between a page's first answer and its own requests.
  await page.waitForFunction(() => document.querySelector("#root > *") && !document.querySelector('[data-page="loading"]'))
  await page.waitForFunction(() => !document.querySelector('[data-replay="loading"]')) // a replay shows its first moment
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(250)
  return page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth])
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const [outArg, ...only] = process.argv.slice(2)
  const out = outArg || path.join(here, "..", "visual", "shots")
  await mkdir(out, { recursive: true })
  const srv = await serve(), lib = await serve(dist, { fixtures: LIBRARY })
  const base = `http://127.0.0.1:${srv.address().port}/`, libBase = `http://127.0.0.1:${lib.address().port}/`
  const browser = await launch(); let bad = 0
  for (const style of STYLES) for (const [mode, width] of [["light", 1280], ["w485", 485]]) {
    const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: "light", reducedMotion: "reduce", deviceScaleFactor: mode === "w485" ? 2 : 1 })
    await pickStyle(ctx, style)
    const page = await ctx.newPage()
    const shot = style === "cake" ? mode : `${mode}_${style}`
    const take = async (name, url) => {
      const [sw, cw] = await withAnswers(page, PAGE_ANSWERS[name], async () => {
        const sizes = await shoot(page, url)
        await page.screenshot({ path: path.join(out, `${name}_${shot}.png`), fullPage: true })
        return sizes
      })
      const ok = sw <= cw; if (!ok) bad++
      console.log(`${name} ${shot} ${ok ? "no h-scroll" : `OVERFLOW ${sw}>${cw}`}`)
    }
    for (const [name, route] of Object.entries(ROUTES)) if (!only.length || only.includes(name)) await take(name, (LIBRARY_PAGES.includes(name) ? libBase : base) + "index.html" + route)
    await ctx.close()
  }
  await browser.close(); srv.close(); lib.close()
  process.exit(bad ? 1 : 0)
}
