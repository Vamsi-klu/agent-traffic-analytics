// Draws agent products' marks on a page at noted moments, for the browser test of cake.js's mark watch
// (tests/browser/test_markers.py; threshold A5).
//
//   node tests/browser/markers.mjs --base http://127.0.0.1:<port> --out <dir>
//
// Scenarios, each in a new browser context (a new visit), each writing <out>/<scenario>.json:
//   marks     on tests/browser/pages/markers.html: a Comet stop button in the page's DOM, Claude in Chrome 1.0.107's
//             "working" tag (top, moved to the bottom, hidden), its "needs your input" tag, its Stop button, and a
//             style sheet left behind; each change's moment on the page's clock (what cake.js must have noted)
//   none      a plain page with no mark, for a few seconds: cake.js must note nothing
//   refused   the consent page: accepted, a mark shown, then refused; changes after the refusal must not be sent
//   cost      what cake.js's looks cost, a few seconds on each of: the test site's shop; a page of COST_ELEMENTS elements;
//             the same page changing every CHURN_MS (the selectors are matched at every look); the same page with
//             Claude in Chrome's working tag shown (its spots are hit-tested at every look)
// playwright-core and Chromium are found as drive.mjs finds them.
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { executablePath } from './chromium.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const base = args.base
const out = args.out
const VIEWPORT = { width: 1280, height: 900 }
const WATCH_STARTS_MS = 2500 // after load: cake.js starts its watch in an idle task after the load event
const HOLD_MS = 1500 // how long each mark stays, and the gap after it: several of cake.js's looks
const SETTLE_MS = 1500 // after leaving: let the exit uploads land before the context closes
const COST_ELEMENTS = 20000
const COST_STAY_MS = 6000
const CHURN_MS = 100

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function launch() {
  return chromium.launch({ executablePath: executablePath() })
}

async function open(browser, url) {
  const context = await browser.newContext({ viewport: VIEWPORT })
  const page = await context.newPage()
  await page.goto(base + url, { waitUntil: 'load' })
  return { context, page }
}

async function leave(context, page) {
  await page.goto('about:blank')
  await sleep(SETTLE_MS)
  await context.close()
}

const clock = (page) => page.evaluate(() => performance.timeOrigin + performance.now())

// One change on the page, noted as [marker id, 1 shown or 0 gone, its moment]; marker null: no record expected.
async function change(page, log, marker, on, fn, ...fnArgs) {
  const t = await page.evaluate(fn, fnArgs)
  log.changes.push({ marker, on, t })
  await sleep(HOLD_MS)
}

async function marks(browser) {
  const { context, page } = await open(browser, '/pages/markers.html')
  const log = { started: await clock(page), changes: [] }
  await sleep(WATCH_STARTS_MS)
  const add = ([tag, attrs, where]) => window.agentMarks.add(tag, attrs, where)
  const remove = ([selector]) => window.agentMarks.remove(selector)
  const show = ([name, at]) => window.agentMarks.show(name, at)
  const hide = ([name]) => window.agentMarks.hide(name)
  await change(page, log, 'comet.overlay', 1, add, 'button', { id: 'pplx-agent-overlay-stop-button' })
  await change(page, log, 'comet.overlay', 0, remove, '#pplx-agent-overlay-stop-button')
  await change(page, log, 'claude-chrome.working', 1, show, 'working', 'top')
  await change(page, log, null, null, show, 'working', 'bottom') // moved to the other edge: still on
  await change(page, log, 'claude-chrome.working', 0, hide, 'working')
  await change(page, log, 'claude-chrome.waiting', 1, show, 'waiting')
  await change(page, log, 'claude-chrome.waiting', 0, hide, 'waiting')
  await change(page, log, 'claude-chrome.bottom', 1, show, 'stop')
  await change(page, log, 'claude-chrome.bottom', 0, hide, 'stop')
  await change(page, log, 'claude-chrome.styles', 1, add, 'style', { id: 'claude-agent-animation-styles' }, 'head')
  log.ended = await clock(page)
  await leave(context, page)
  return log
}

async function none(browser) {
  const { context, page } = await open(browser, '/pages/plain.html')
  const log = { started: await clock(page), changes: [] }
  await sleep(WATCH_STARTS_MS + HOLD_MS)
  log.ended = await clock(page)
  await leave(context, page)
  return log
}

async function refused(browser) {
  const { context, page } = await open(browser, '/pages/consent.html')
  const log = { started: await clock(page), changes: [] }
  await page.click('#accept')
  await sleep(WATCH_STARTS_MS)
  const add = ([id]) => {
    document.body.appendChild(Object.assign(document.createElement('button'), { id }))
    return performance.timeOrigin + performance.now()
  }
  await change(page, log, 'comet.overlay', 1, add, 'pplx-agent-overlay-stop-button')
  log.refused = await page.evaluate(() => {
    document.getElementById('reject').click()
    return performance.timeOrigin + performance.now()
  })
  // Changes after the refusal: cake.js must send nothing of them.
  await page.evaluate(() => document.getElementById('pplx-agent-overlay-stop-button').remove())
  await page.evaluate(() => {
    document.body.appendChild(Object.assign(document.createElement('div'), { id: 'eko-highlight-container' }))
  })
  await sleep(HOLD_MS * 2)
  log.ended = await clock(page)
  await leave(context, page)
  return log
}

async function cost(browser) {
  const log = { pages: [] }
  const cases = [
    { name: 'shop', url: '/demo' },
    { name: 'big page', url: '/pages/markers.html', fill: COST_ELEMENTS },
    { name: 'big page, changing', url: '/pages/markers.html', fill: COST_ELEMENTS, churn: CHURN_MS },
    { name: 'big page, working tag shown', url: '/pages/markers.html', fill: COST_ELEMENTS, tag: 'working' }
  ]
  for (const { name, url, fill, churn, tag } of cases) {
    const { context, page } = await open(browser, url)
    const started = await clock(page)
    const elements = await page.evaluate(([fill, churn, tag]) => {
      if (fill) window.agentMarks.fill(fill)
      if (churn) window.agentMarks.churn(churn)
      if (tag) window.agentMarks.show(tag, 'top')
      return document.getElementsByTagName('*').length
    }, [fill, churn, tag])
    await sleep(COST_STAY_MS)
    log.pages.push({ name, url, elements, started, ended: await clock(page) })
    await leave(context, page)
  }
  return log
}

await mkdir(out, { recursive: true })
const browser = await launch()
try {
  for (const [name, run] of Object.entries({ marks, none, refused, cost })) {
    await writeFile(path.join(out, `${name}.json`), JSON.stringify(await run(browser), null, 2))
  }
} finally {
  await browser.close()
}
