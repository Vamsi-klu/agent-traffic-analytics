// Drives Chromium for tests/browser/test_web_metrics.py: what cake.js records for the dashboard's web analytics, against
// the stand-in collector (tests/browser/collector.py), each scenario in a browser context of its own (a profile).
//   node tests/browser/web_metrics.mjs --base http://127.0.0.1:<port> --out <dir>
// Writes <out>/<scenario>.json with what the page itself said (its storage, its referrer, the clock it read):
//   sources      from another site's page that hands over its whole address (localhost, no cake.js) to a page with
//                campaign parameters and an ad click id; then a single-page app's navigation (a new path, a new query
//                string alone, the first path again), a second page load, a page load after the session's clock ran
//                out (set back in sessionStorage before cake.js reads it), and window.cake.stop()
//   profile      another profile opens the page: another visitor id
//   consent      data-consent="required": nothing stored before Accept, the visitor id after it, none after Reject
import { createRequire } from 'node:module'
import { existsSync, readFileSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))
const CAKEJS = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const STORAGE = CAKEJS.storage

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const base = args.base
const other = base.replace('127.0.0.1', 'localhost') // another origin, for the referring page
const SEND_MS = CAKEJS.batch.interval_min_ms + 1500 // a timer batch has gone, and its answer arrived
const MINUTE_MS = 60 * 1000
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function launch() {
  const app = 'chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
  const guess = path.join(process.env.HOME, 'Library/Caches/ms-playwright/chromium-1228', app)
  const executablePath = process.env.CAKE_CHROME || (existsSync(guess) ? guess : undefined)
  return chromium.launch({ executablePath })
}

/** What the page keeps: the visitor id, the session id and its clock. */
function storage(page) {
  return page.evaluate((keys) => ({
    visitor: localStorage.getItem(keys.visitor), session: sessionStorage.getItem(keys.session),
    clock: sessionStorage.getItem(keys.clock)
  }), STORAGE)
}

/** A click on the page's heading: an event, so cake.js looks at the path again. */
async function poke(page) {
  await page.click('#title')
  await sleep(200)
}

async function sources(browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  const log = {}
  await page.goto(`${other}/pages/referrer.html?nocake=1&secret=REFERRERSECRET123`)
  await Promise.all([page.waitForNavigation(), page.click('#out')])
  log.referrer = await page.evaluate(() => document.referrer)
  await sleep(SEND_MS)
  log.landing = await storage(page)
  for (const to of ['/pages/spa-b', '/pages/spa-b?x=2', '/pages/plain.html']) {
    await page.evaluate((url) => history.pushState({}, '', url), to)
    await poke(page)
  }
  await sleep(SEND_MS)
  await page.goto(`${base}/pages/plain.html`)
  await sleep(SEND_MS)
  log.secondPage = await storage(page)
  // The page being left writes its clock; the next one finds it set back before cake.js reads it.
  await page.addInitScript(({ key, minute }) => {
    const now = Date.now()
    sessionStorage.setItem(key, JSON.stringify({ s: now - 120 * minute, l: now - 31 * minute }))
  }, { key: STORAGE.clock, minute: MINUTE_MS })
  await page.reload()
  await sleep(SEND_MS)
  log.afterIdle = await storage(page)
  await page.evaluate(() => window.cake.stop())
  log.afterStop = await storage(page)
  await context.close()
  return log
}

async function profile(browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(`${base}/pages/plain.html`)
  await sleep(SEND_MS)
  const log = { landing: await storage(page) }
  await context.close()
  return log
}

async function consent(browser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await page.goto(`${base}/pages/consent.html`)
  await sleep(500)
  const log = { beforeAccept: await storage(page) }
  await page.click('#accept')
  await sleep(SEND_MS)
  log.afterAccept = await storage(page)
  await page.click('#reject')
  await sleep(300)
  log.afterReject = await storage(page)
  await context.close()
  return log
}

await mkdir(args.out, { recursive: true })
const browser = await launch()
try {
  for (const [name, scenario] of Object.entries({ sources, profile, consent })) {
    await writeFile(path.join(args.out, `${name}.json`), JSON.stringify(await scenario(browser), null, 2))
  }
} finally {
  await browser.close()
}
