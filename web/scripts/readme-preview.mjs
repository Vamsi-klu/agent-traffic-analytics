// README's dashboard preview, docs/assets/readme/preview-*.png: the dashboard as a newcomer sees it scrolling down, one
// part at a time (Key metrics; Top agents and Trends; Paths and Sources; Devices and Geography), then the session list,
// then the page of a session where a human and an agent took turns, its replay played to the hand-off and stopped
// there, beside who acted when and the four layers of reasons: pictures of one size for README to show in a row that
// scrolls sideways. Each is the browser's view at that place: the top bar stays (it is sticky), and whatever of the
// parts before and after would show in the view is hidden, so no picture ends in half a card; the session list hides a
// row the view's bottom edge would cut. Light theme, 1280 wide, decorative motion off, drawn at twice the pixels and
// saved at OUT_WIDTH, sharp where README shows them half as wide.
// It takes them from the AgentCake that --origin names, any one whose session list's first page has a session where a
// human and an agent took turns, with its replay (README's are of a copy of a demo shop's data folder, served with
// `agentcake serve`); without such a session it says so before taking any picture. It refuses every request that would
// leave that AgentCake, so a session's replay never reaches the site it was recorded on. --out writes the pictures to
// another folder than README's.
//   cd web && npm run build && node scripts/readme-preview.mjs --origin http://127.0.0.1:<port>/ [--out <folder>]
// It finds the parts by the icons of their cards' titles (lucide's classes) and the page's structure, never by
// words, so new interface words do not change it.
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { PNG } from "pngjs"
import { hideInReplay } from "./readme-images.mjs"
import { launch, shoot } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(here, "..", "..", "docs", "assets", "readme")
const VIEW = { width: 1280, height: 1160, pixelRatio: 2 } // tall enough for the tallest part (Top agents and Trends) under the top bar
const OUT_WIDTH = 1440 // README shows each 720 px wide: twice that, for sharp screens
const RGB = 2 // protocol: PNG colour type 2; screenshots are opaque, so alpha would only take room
const MOST_DEFLATE = 9 // protocol: zlib's highest compression level
const ICON = (name) => `main [data-slot=card-title] svg.lucide-${name}` // a card title's icon (the verdict icons reuse some)
const LIST = "api/sessions?range=7d" // what the session list asks when it opens (src/lib/filters.ts)
const TOOK_TURNS = "human_agent" // an Agent session where a human and an agent took turns (agent_turns, src/data/types.ts)
/** The pictures, in README's order: the route, and the part of the page each shows, from the block holding its first
 *  icon (or the page's top) to the block holding its last; `heading` takes in the section heading above the first.
 *  `session` opens the newest session of that kind (agent_turns) on the session list's first page, its id after the
 *  route, with its replay stopped at its first hand-off (stopAtHandoff); its part starts at the block holding the
 *  page's title: the classification, the title and the line under it. */
export const SLIDES = [
  { file: "preview-key-metrics.png", route: "#/dashboard", from: null, to: ICON("bot"), before: true },
  { file: "preview-top-agents.png", route: "#/dashboard", from: ICON("bot"), to: ICON("trending-up"), heading: true },
  { file: "preview-paths.png", route: "#/dashboard", from: ICON("route"), to: ICON("signpost") },
  { file: "preview-devices.png", route: "#/dashboard", from: ICON("monitor-smartphone"), to: ICON("map-pin") },
  { file: "preview-sessions.png", route: "#/sessions", from: null, to: null },
  { file: "preview-session-replay.png", route: "#/sessions/", session: TOOK_TURNS, from: "main :has(> h1)", to: ICON("search") },
]
const SESSION_ROW = 'main a[href^="#/sessions/"]' // a row of the session list
const option = (name) => { const at = process.argv.indexOf(name); return at > 0 ? process.argv[at + 1] : undefined }

/** In the page: where a part lies (page px), { top, bottom, startY }: from the block holding its first icon (or the
 *  page's top) to the block holding its last (or the page's end), and where the page's own first block starts at the
 *  top. README's demo pauses its scroll down the dashboard at the same parts. */
export function partRange({ from, to, before, heading }) {
  const pageY = (element) => { const box = element.getBoundingClientRect(); return { top: box.top + scrollY, bottom: box.bottom + scrollY } }
  const main = document.querySelector("main")
  const block = (selector) => { // the outermost card or section holding it, else what was found (a page's title block)
    const found = document.querySelector(selector)
    if (!found) throw new Error(`no ${selector} on this page`)
    return found.closest("section") || found.closest("[data-slot=card]") || found
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
 *  than the view shows from `top` down that crosses it is looked into instead (the page's columns, the session list's
 *  card), so a cut is always between two blocks. Returns the scroll position. */
function isolate({ top, bottom, startY, viewHeight }) {
  const pageY = (element) => { const box = element.getBoundingClientRect(); return { top: box.top + scrollY, bottom: box.bottom + scrollY } }
  const scroll = Math.max(0, Math.round(top - startY)) // whole pixels: a fraction would blur the picture
  const room = scroll + viewHeight - top // the page the view shows from top down: a taller block never shows whole
  const end = Math.min(bottom, scroll + viewHeight)
  const walk = (element) => {
    for (const child of element.children) {
      const box = pageY(child)
      if (box.top >= top && box.bottom <= end) continue
      const crosses = box.bottom > top && box.top < end
      if (crosses && box.bottom - box.top > room) walk(child)
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

/** SLIDES as main takes them: one with `session` gets that session's id after its route and its first hand-off
 *  (handoffMs), asked of origin before any picture is taken, so a missing one is said first. */
async function opened(origin) {
  const ask = async (route) => {
    const answer = await fetch(origin + route)
    if (!answer.ok) throw new Error(`${origin}${route}: ${answer.status}`)
    return answer.json()
  }
  return Promise.all(SLIDES.map(async (slide) => {
    if (!slide.session) return slide
    const found = (await ask(LIST)).results.find((session) => session.agent_turns === slide.session)
    const handoff = found && (await ask(`api/session/${found.id}`)).timeline.handoffs[0]
    if (!handoff) throw new Error(`no session where a human and an agent took turns on the session list's first page (${LIST})`)
    return { ...slide, route: slide.route + found.id, handoffMs: handoff.at_ms }
  }))
}

/** A browser context as a newcomer's, that refuses every request that would leave origin. */
async function shotContext(browser, origin) {
  const context = await browser.newContext({ viewport: { width: VIEW.width, height: VIEW.height }, colorScheme: "light",
    reducedMotion: "reduce", deviceScaleFactor: VIEW.pixelRatio })
  await context.route("**/*", (route) => {
    const url = route.request().url()
    return /^(data|blob|about):/.test(url) || url.startsWith(origin) ? route.continue() : route.abort()
  })
  return context
}

/** A page whose clock Playwright drives (stopAtHandoff), in a context of its own: a clock is the whole context's, and
 *  the other pictures keep the browser's own. It runs as the real one does until stopAtHandoff stops it. */
async function clockedPage(browser, origin) {
  const page = await (await shotContext(browser, origin)).newPage()
  await page.clock.install()
  return page
}

/** Stop the page's clock: pauseAt takes a moment still ahead of it, and the clock runs on while the call travels, so
 *  the moment is a second ahead, then further if the computer is so busy that the clock got there first. */
async function stopClock(page) {
  for (let aheadMs = 1000; ; aheadMs *= 4) {
    try {
      return await page.clock.pauseAt(await page.evaluate((ms) => Date.now() + ms, aheadMs))
    } catch (error) {
      if (aheadMs >= 64000) throw error
    }
  }
}

/** A session page's replay on a clockedPage, played to the first hand-off and stopped there: it jumps as "Jump to
 *  hand-off" does (a few seconds before the hand-off) and pauses, then plays on the time left on the page's clock,
 *  which stands still but for that, and pauses again. The stage shows that moment as playback draws it, not a jump's
 *  first frame, and the timeline's playhead stands on the hand-off (short of it by less than an animation frame: the
 *  player's time moves on frames). Returns the moment it stopped at (ms), as the timeline gives it. */
async function stopAtHandoff(page, handoffMs) {
  const playhead = async () => Number(await page.locator("[data-timeline-bar]").getAttribute("aria-valuenow"))
  await page.locator("button:has(svg.lucide-skip-forward)").click() // the jump plays: pause it there
  await page.locator("button:has(svg.lucide-pause)").click()
  await page.locator("button:has(svg.lucide-play)").waitFor()
  const jumped = await playhead()
  await stopClock(page)
  // Clicks in the page itself: Playwright's own click waits for animation frames, which a clock standing still keeps.
  await page.locator("button:has(svg.lucide-play)").evaluate((button) => button.click())
  await page.clock.runFor(handoffMs - jumped)
  await page.locator("button:has(svg.lucide-pause)").evaluate((button) => button.click())
  await page.clock.resume() // the replay stays paused; the picture is taken as every other is
  await page.locator("button:has(svg.lucide-play)").waitFor()
  return playhead()
}

async function main() {
  const origin = option("--origin")?.replace(/\/?$/, "/")
  if (!origin) throw new Error("give the AgentCake to film: --origin http://127.0.0.1:<port>/")
  const out = option("--out") ? path.resolve(option("--out")) : OUT
  const slides = await opened(origin)
  await mkdir(out, { recursive: true })
  const browser = await launch()
  try {
    const context = await shotContext(browser, origin)
    const page = await context.newPage(), scaler = await context.newPage()
    for (const slide of slides) {
      const view = slide.session ? await clockedPage(browser, origin) : page
      await shoot(view, `${origin}index.html${slide.route}`)
      const parts = [slide.from, slide.to].filter(Boolean)
      for (const drawn of parts.length ? parts : [SESSION_ROW]) {
        await view.locator(drawn).first().waitFor() // a busy computer can take a while to draw what the page fetched
      }
      let stopped = null
      if (slide.session) {
        await hideInReplay(view) // the test shop's own words, as README's demo hides them (readme-images.mjs)
        stopped = await stopAtHandoff(view, slide.handoffMs)
      }
      await view.evaluate(() => window.scrollTo(0, 0))
      const range = await view.evaluate(partRange, slide)
      const scroll = await view.evaluate(isolate, { ...range, viewHeight: VIEW.height })
      await view.waitForTimeout(250)
      const png = await smaller(scaler, await view.screenshot({ animations: "disabled", caret: "hide" }))
      await writeFile(path.join(out, slide.file), png)
      const replay = stopped === null ? "" : `, its replay stopped at ${stopped} ms (hand-off at ${slide.handoffMs} ms)`
      console.log(`${slide.file}: ${slide.route} from ${scroll} px${replay}, ${(png.length / 1e3).toFixed(0)} kB`)
      await view.goto("about:blank")
    }
  } finally {
    await browser.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main()
