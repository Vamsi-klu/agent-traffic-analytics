// README's dashboard preview, docs/assets/readme/preview-*.png: the dashboard as a newcomer sees it scrolling down, one
// part at a time (Key metrics; Top agents and Trends; Paths and Sources; Devices and Geography), then the session list,
// as five pictures of one size that README shows in a row to scroll sideways. Each is the browser's view at that place:
// the top bar stays (it is sticky), and whatever of the parts before and after would show in the view is hidden, so no
// picture ends in half a card; the session list hides a row the view's bottom edge would cut. Light theme, 1280 wide,
// decorative motion off, drawn at twice the pixels and saved at OUT_WIDTH, sharp where README shows them half as wide.
// It takes them from the AgentCake that --origin names, any one whose dashboard has sessions to show (README's are of
// a copy of a demo shop's data folder, served with `agentcake serve`), and refuses every request that would leave it,
// so a session's replay never reaches the site it was recorded on.
//   cd web && npm run build && node scripts/readme-preview.mjs --origin http://127.0.0.1:<port>/
// It finds the parts by the icons of their cards' titles (lucide's classes) and the page's structure, never by
// words, so new interface words do not change it.
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { PNG } from "pngjs"
import { launch, shoot } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(here, "..", "..", "docs", "assets", "readme")
const VIEW = { width: 1280, height: 1160, pixelRatio: 2 } // tall enough for the tallest part (Top agents and Trends) under the top bar
const OUT_WIDTH = 1440 // README shows each 720 px wide: twice that, for sharp screens
const RGB = 2 // protocol: PNG colour type 2; screenshots are opaque, so alpha would only take room
const MOST_DEFLATE = 9 // protocol: zlib's highest compression level
const ICON = (name) => `main [data-slot=card-title] svg.lucide-${name}` // a card title's icon (the verdict icons reuse some)
/** The pictures, in README's order: the route, and the part of the page each shows, from the block holding its first
 *  icon (or the page's top) to the block holding its last; `heading` takes in the section heading above the first. */
export const SLIDES = [
  { file: "preview-key-metrics.png", route: "#/dashboard", from: null, to: ICON("bot"), before: true },
  { file: "preview-top-agents.png", route: "#/dashboard", from: ICON("bot"), to: ICON("trending-up"), heading: true },
  { file: "preview-paths.png", route: "#/dashboard", from: ICON("route"), to: ICON("signpost") },
  { file: "preview-devices.png", route: "#/dashboard", from: ICON("monitor-smartphone"), to: ICON("map-pin") },
  { file: "preview-sessions.png", route: "#/sessions", from: null, to: null },
]
const SESSION_ROW = 'main a[href^="#/sessions/"]' // a row of the session list
const option = (name) => { const at = process.argv.indexOf(name); return at > 0 ? process.argv[at + 1] : undefined }

/** In the page: where a part lies (page px), { top, bottom, startY }: from the block holding its first icon (or the
 *  page's top) to the block holding its last (or the page's end), and where the page's own first block starts at the
 *  top. README's demo pauses its scroll down the dashboard at the same parts. */
export function partRange({ from, to, before, heading }) {
  const pageY = (element) => { const box = element.getBoundingClientRect(); return { top: box.top + scrollY, bottom: box.bottom + scrollY } }
  const main = document.querySelector("main")
  const block = (selector) => { // the outermost card or section holding the icon
    const icon = document.querySelector(selector)
    if (!icon) throw new Error(`no ${selector} on this page`)
    return icon.closest("section") || icon.closest("[data-slot=card]")
  }
  const startY = pageY(main.firstElementChild).top
  let top = startY, bottom = Infinity
  if (from) {
    const first = block(from)
    top = pageY(heading ? first.previousElementSibling : first).top
  }
  if (to) {
    const last = block(to)
    bottom = before ? pageY(last.previousElementSibling).top : pageY(last).bottom
  }
  return { top, bottom, startY }
}

/** In the page: show only what lies wholly between `top` and `bottom` (page px) and scroll so `top` sits where the
 *  page's own first block (`startY`) does at the top. A block that crosses the view's edge hides whole, a block taller
 *  than the view that crosses it is looked into instead (the page's columns, the session list's card), so a cut is
 *  always between two blocks. Returns the scroll position. */
function isolate({ top, bottom, startY, viewHeight }) {
  const pageY = (element) => { const box = element.getBoundingClientRect(); return { top: box.top + scrollY, bottom: box.bottom + scrollY } }
  const scroll = Math.max(0, Math.round(top - startY)) // whole pixels: a fraction would blur the picture
  const end = Math.min(bottom, scroll + viewHeight)
  const walk = (element) => {
    for (const child of element.children) {
      const box = pageY(child)
      if (box.top >= top && box.bottom <= end) continue
      const crosses = box.bottom > top && box.top < end
      if (crosses && box.bottom - box.top > viewHeight) walk(child)
      else child.style.setProperty("visibility", "hidden", "important")
    }
  }
  walk(document.querySelector("main"))
  window.scrollTo(0, scroll)
  return scroll
}

/** A screenshot made OUT_WIDTH wide by the browser's own high-quality scaling, as the pixels of an RGB PNG. */
async function smaller(page, png) {
  const scaled = await page.evaluate(async ({ data, width }) => {
    const image = new Image()
    image.src = `data:image/png;base64,${data}`
    await image.decode()
    const canvas = Object.assign(document.createElement("canvas"), { width, height: Math.round(image.height * width / image.width) })
    const draw = canvas.getContext("2d")
    draw.imageSmoothingQuality = "high"
    draw.drawImage(image, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL("image/png").split(",")[1]
  }, { data: png.toString("base64"), width: OUT_WIDTH })
  const out = PNG.sync.read(Buffer.from(scaled, "base64")) // written again, smaller: RGB at zlib's highest level
  return PNG.sync.write(out, { colorType: RGB, inputHasAlpha: true, deflateLevel: MOST_DEFLATE })
}

async function main() {
  const origin = option("--origin")?.replace(/\/?$/, "/")
  if (!origin) throw new Error("give the AgentCake to film: --origin http://127.0.0.1:<port>/")
  const browser = await launch()
  try {
    const context = await browser.newContext({ viewport: { width: VIEW.width, height: VIEW.height }, colorScheme: "light",
      reducedMotion: "reduce", deviceScaleFactor: VIEW.pixelRatio })
    await context.route("**/*", (route) => {
      const url = route.request().url()
      return /^(data|blob|about):/.test(url) || url.startsWith(origin) ? route.continue() : route.abort()
    })
    const page = await context.newPage(), scaler = await context.newPage()
    for (const slide of SLIDES) {
      await shoot(page, `${origin}index.html${slide.route}`)
      const parts = [slide.from, slide.to].filter(Boolean)
      for (const drawn of parts.length ? parts : [SESSION_ROW]) {
        await page.locator(drawn).first().waitFor() // a busy computer can take a while to draw what the page fetched
      }
      await page.evaluate(() => window.scrollTo(0, 0))
      const range = await page.evaluate(partRange, slide)
      const scroll = await page.evaluate(isolate, { ...range, viewHeight: VIEW.height })
      await page.waitForTimeout(250)
      const png = await smaller(scaler, await page.screenshot({ animations: "disabled", caret: "hide" }))
      await writeFile(path.join(OUT, slide.file), png)
      console.log(`${slide.file}: ${slide.route} from ${scroll} px, ${(png.length / 1e3).toFixed(0)} kB`)
      await page.goto("about:blank")
    }
  } finally {
    await browser.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main()
