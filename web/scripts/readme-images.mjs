// The pictures README.md shows (docs/assets/readme/): Crumb's head as the icon at the top, and the dashboard, a session's
// replay and the settings page. They are taken the way the visual baseline is (scripts/visual.mjs), from the same built app
// and the same answers: the dashboard shows cake's own answers on the fixed test library at a fixed moment
// (fixtures/library/, LIBRARY), the session and the settings the samples (src/data/fixtures/), so no visitor,
// address or folder of any computer can be in them. Light theme, 1280 wide, drawn at twice the pixels so they stay sharp
// where GitHub shrinks them to its column; each is the top of its page, as far down as README describes it.
// The repository's social preview (social-preview.png, the picture a shared link to the repository shows) is the top of
// the same dashboard at the size GitHub asks for, 1280x640 at one pixel per CSS pixel, which keeps it under GitHub's
// 1 MB (repo-best; it is uploaded in the repository's settings, under "Social preview").
//   cd web && npm run build && node scripts/readme-images.mjs        (when a page, Crumb or the tokens change; commit them)
// With --origin <url>, the dashboard, the session and the social preview are taken from that running AgentCake instead
// (the maintainers serve their own test recordings this way, which stay out of the repository): the session is
// --session <id>, else the first session its list calls Human + agent, shown at its first hand-off (the replay's own
// Jump to hand-off, played to the mark and paused). Every request that would leave that AgentCake is refused, so a
// replay never reaches the site it was recorded on.
//   node scripts/readme-images.mjs --origin http://127.0.0.1:<port>/ [--session <id>]
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { crumbHeadSvg } from "./favicon.mjs"
import { LIBRARY } from "./fixture-api.mjs"
import { launch, serve, shoot } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(here, "..", "..", "docs", "assets", "readme")
const ICON = { file: "crumb.png", size: 224 } // README shows it 112 px wide: twice that, for sharp screens
const VIEW = { width: 1280, pixelRatio: 2 } // the visual baseline's width
/** Each page's picture: its route, whether it is shot on the fixed test library, whether --origin's AgentCake gives it
 *  instead (the pages that show sessions; settings shows none, and a running AgentCake's page script line would name
 *  its own scratch port), and how much of the page from the top it keeps (CSS px), to just below the part README
 *  describes. */
const PAGES = {
  dashboard: { route: "#/dashboard", library: true, showcase: true, height: 1291 }, // the spotlight, the counts, session length, both charts
  session: { route: "#/sessions/7f3a-c1", library: false, showcase: true, height: 1116 }, // the replay, who acted when, the four layers
  settings: { route: "#/settings", library: false, showcase: false, height: 1465 }, // down to telemetry and registration
}
/** The social preview: GitHub's size "for best display" (VIEW.width wide), the dashboard README shows (--origin's, else the fixed test library's). */
const SOCIAL = { file: "social-preview.png", route: "#/dashboard", height: 640, pixelRatio: 1 }
const LIST = "api/sessions?range=7d" // what the session list asks when it opens (src/lib/filters.ts)
const TOOK_TURNS = "human_agent" // an Agent session where a human and an agent took turns (agent_turns, src/data/types.ts)
const SETTLE_MS = 600 // after pausing, for the replay to draw its frame
const option = (name) => { const at = process.argv.indexOf(name); return at > 0 ? process.argv[at + 1] : undefined }

async function drawIcon(context, origin) {
  const page = await context.newPage()
  await page.goto(`${origin}index.html#/`)
  const svg = await crumbHeadSvg(page)
  await page.setViewportSize({ width: ICON.size, height: ICON.size })
  await page.setContent(`<!doctype html><body style="margin:0">${svg.replace("<svg", `<svg width="${ICON.size}" height="${ICON.size}"`)}</body>`)
  const png = await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: ICON.size, height: ICON.size } })
  await page.close()
  return png
}

async function drawPage(page, url, height, before) {
  await page.setViewportSize({ width: VIEW.width, height })
  await shoot(page, url)
  if (before) await before(page)
  return page.screenshot({ animations: "disabled", caret: "hide", clip: { x: 0, y: 0, width: VIEW.width, height } })
}

/** What a replay hides as README's pictures and demo show it: the test shop's own words that call it cake's demo shop,
 *  namely its banner line ("Demo shop that comes with cake. Nothing is sold…"), its name ("Cake Demo Shop"), the
 *  checkout's note ("Demo checkout: … never recorded by cake") and its footer ("Served by cake on this computer · back
 *  to the task list", the recorder's start page). The maintainers' test recordings were made on the old demo shop's
 *  pages, and AgentCake has no demo shop any more, so these would tell a newcomer otherwise. Hidden with visibility, so
 *  nothing moves and the recorded pointer stays over what it pointed at; only the showing changes, never the recording. */
export const HIDDEN_IN_REPLAY = [".demo-note", "header.top .brand", "#app > h1 + p.mut", "footer.foot"]

/** Keep HIDDEN_IN_REPLAY hidden in the replay on page: rrweb builds its frame's document again for every page of the
 *  recording, so the style is put back whenever the frame's content changes (a mutation observer, which runs before the
 *  frame is painted) and checked again on every animation frame (a document rrweb made anew). */
export async function hideInReplay(page) {
  await page.evaluate((selectors) => {
    const hide = (doc) => {
      for (const element of doc.querySelectorAll(selectors.join(","))) element.style.setProperty("visibility", "hidden", "important")
    }
    let watched = null, observer = null
    const check = () => {
      const doc = document.querySelector("[data-replay] iframe")?.contentDocument
      if (doc && doc !== watched) {
        observer?.disconnect()
        watched = doc
        observer = new MutationObserver(() => hide(doc))
        observer.observe(doc, { childList: true, subtree: true })
      }
      if (doc) hide(doc)
      requestAnimationFrame(check)
    }
    check()
  }, HIDDEN_IN_REPLAY)
}

/** The session --origin's pictures show: --session, else the first its list calls Human + agent. */
async function showcaseSession(origin) {
  if (option("--session")) return option("--session")
  const found = (await (await fetch(origin + LIST)).json()).results.find((session) => session.agent_turns === TOOK_TURNS)
  if (!found) throw new Error(`${origin}: no session where a human and an agent took turns`)
  return found.id
}

/** On a session page: the replay at its first hand-off (Jump to hand-off, played up to the mark, paused). */
function atHandoff(leadMs) {
  return async (page) => {
    await page.waitForFunction(() => document.querySelector("[data-replay]") && !document.querySelector('[data-replay="loading"]'))
    await hideInReplay(page)
    await page.locator("button:has(svg.lucide-skip-forward)").click()
    await page.locator("button:has(svg.lucide-pause)").waitFor()
    await page.waitForTimeout(leadMs)
    await page.locator("button:has(svg.lucide-pause)").click()
    await page.waitForTimeout(SETTLE_MS)
  }
}

/** A browser context that refuses every request to anywhere but origins (a replay's pages stay on the stage). */
async function onlyFrom(context, origins) {
  await context.route("**/*", (route) => {
    const url = route.request().url()
    return /^(data|blob|about):/.test(url) || origins.some((o) => url.startsWith(o)) ? route.continue() : route.abort()
  })
  return context
}

async function main() {
  await mkdir(OUT, { recursive: true })
  const samples = await serve(), library = await serve(undefined, { fixtures: LIBRARY })
  const origin = `http://127.0.0.1:${samples.address().port}/`, libraryOrigin = `http://127.0.0.1:${library.address().port}/` // protocol: the screenshot servers' loopback address
  const browser = await launch()
  try {
    const icons = await browser.newContext({ colorScheme: "light", reducedMotion: "reduce", deviceScaleFactor: 1 })
    await writeFile(path.join(OUT, ICON.file), await drawIcon(icons, origin))
    console.log(`${ICON.file}: Crumb's head, ${ICON.size} px`)
    await icons.close()
    const showcase = option("--origin")
    const pages = { ...PAGES }, steps = {}
    if (showcase) {
      const id = await showcaseSession(showcase)
      const lead = (await (await fetch(`${showcase}api/session/${id}`)).json()).replay.handoff_lead_ms
      pages.session = { ...PAGES.session, route: `#/sessions/${id}` }
      steps.session = atHandoff(lead)
    }
    const from = ({ library: onLibrary, showcase: shown }) => (showcase && shown ? showcase : onLibrary ? libraryOrigin : origin)
    const context = await browser.newContext({ viewport: { width: VIEW.width, height: PAGES.dashboard.height }, colorScheme: "light",
      reducedMotion: "reduce", deviceScaleFactor: VIEW.pixelRatio })
    if (showcase) await onlyFrom(context, [showcase, origin, libraryOrigin])
    const page = await context.newPage()
    for (const [name, entry] of Object.entries(pages)) {
      const png = await drawPage(page, `${from(entry)}index.html${entry.route}`, entry.height, steps[name])
      await writeFile(path.join(OUT, `${name}.png`), png)
      console.log(`${name}.png: ${entry.route}, ${VIEW.width}x${entry.height} at ${VIEW.pixelRatio}x${from(entry) === showcase ? " (--origin)" : ""}`)
    }
    const social = await browser.newContext({ viewport: { width: VIEW.width, height: SOCIAL.height }, colorScheme: "light",
      reducedMotion: "reduce", deviceScaleFactor: SOCIAL.pixelRatio })
    if (showcase) await onlyFrom(social, [showcase])
    await writeFile(path.join(OUT, SOCIAL.file), await drawPage(await social.newPage(), `${from(PAGES.dashboard)}index.html${SOCIAL.route}`, SOCIAL.height))
    console.log(`${SOCIAL.file}: ${SOCIAL.route}, ${VIEW.width}x${SOCIAL.height} at ${SOCIAL.pixelRatio}x`)
  } finally {
    await browser.close()
    samples.close()
    library.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main()
