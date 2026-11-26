// Crumb's head as the icon at the top of README (docs/assets/readme/crumb.png), drawn from the favicon's SVG
// (scripts/favicon.mjs), and the repository's social preview (social-preview.png, the picture a shared link to the
// repository shows; it is uploaded in the repository's settings, under "Social preview"): the top of the dashboard at the
// size GitHub asks for, 1280x640 at one pixel per CSS pixel, which keeps it under GitHub's 1 MB. Light theme, in Cake
// (the pages' default is Minimal; README and the social preview stay in Cake). By default
// the dashboard is cake's own answers on the fixed test library at a fixed moment (fixtures/library/, LIBRARY), taken
// the way the visual baseline is (scripts/visual.mjs), so no visitor, address or folder of any computer can be in it.
// With --origin <url> it is that running AgentCake's dashboard instead (the maintainers serve a copy of the demo data's
// server home this way), and every request that would leave that AgentCake is refused.
//   cd web && npm run build && node scripts/readme-images.mjs [--origin http://127.0.0.1:<port>/]
// README's dashboard preview is readme-preview.mjs's; the maintainers' script that films README's demo takes
// hideInReplay() from here.
// Playwright and Chromium: as scripts/shots.mjs finds them.
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { crumbHeadSvg } from "./favicon.mjs"
import { LIBRARY } from "./fixture-api.mjs"
import { launch, pickStyle, serve, shoot } from "./shots.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(here, "..", "..", "docs", "assets", "readme")
const ICON = { file: "crumb.png", size: 224 } // README shows it 112 px wide: twice that, for sharp screens
/** The social preview: GitHub's size "for best display", the visual baseline's width. */
const SOCIAL = { file: "social-preview.png", route: "#/dashboard", width: 1280, height: 640, pixelRatio: 1 }
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

async function drawPage(page, url, width, height) {
  await page.setViewportSize({ width, height })
  await shoot(page, url)
  return page.screenshot({ animations: "disabled", caret: "hide", clip: { x: 0, y: 0, width, height } })
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
    const social = await browser.newContext({ viewport: { width: SOCIAL.width, height: SOCIAL.height }, colorScheme: "light",
      reducedMotion: "reduce", deviceScaleFactor: SOCIAL.pixelRatio })
    await pickStyle(social, "cake")
    if (showcase) await onlyFrom(social, [showcase])
    const dashboard = `${showcase ?? libraryOrigin}index.html${SOCIAL.route}`
    await writeFile(path.join(OUT, SOCIAL.file), await drawPage(await social.newPage(), dashboard, SOCIAL.width, SOCIAL.height))
    console.log(`${SOCIAL.file}: ${SOCIAL.route}, ${SOCIAL.width}x${SOCIAL.height} at ${SOCIAL.pixelRatio}x${showcase ? " (--origin)" : ""}`)
  } finally {
    await browser.close()
    samples.close()
    library.close()
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) await main()
