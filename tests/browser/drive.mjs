// Drives Chromium through the test site's shop (tests/site; AgentCake's demo shop until D37) for the cake.js browser
// tests (plan steps S1.3, S1.4) and writes down what it
// did, so the Python side (tests/browser/test_capture.py) can check that cake.js delivered all of it to the stand-in
// collector (tests/browser/collector.py).
//
//   node tests/browser/drive.mjs --base http://127.0.0.1:<port> --out <dir> --plan direct:3,humanlike:3,bounce:4 \
//        --blocked '<CSS selector of the elements cake.js must not record>'
//
// Scenarios, each run in a new browser context (a new visit):
//   direct     Playwright's own clicks and fills, as a script would do it
//   humanlike  curved mouse paths with jitter, pauses, wheel scrolling, typing key by key
//   bounce     24 pages, each left 0.3–0.8 s after it opened
//   timing     the same pages with and without cake.js, to measure what cake.js adds (writes timing.json)
//   hidden     types --canary into an ordinary field and one the site owner hides (pages/hidden.html, S5.5)
//   privacy    types --canary (a made-up string) and the test card number into every kind of field, then checks out
//   consent_…  GOAL T10's cases on a page with a consent bar, and refusals while uploads are under way (consent.mjs)
// Writes <out>/<scenario>-<run>.json: the pages in the order they opened and every click (with the page it was on and
// whether its target is inside an element cake.js must not record, which the replay therefore does not show).
// playwright-core comes from CAKE_PLAYWRIGHT or web/node_modules/playwright-core, Chromium from CAKE_CHROME or the
// local Playwright cache (as web/scripts/shots.mjs does). Only made-up details are typed (GOAL section 4).
// CAKE_CPU_THROTTLE=<n> runs the scenarios' pages n times slower (Chromium's CPU throttling, as in DevTools): a loaded
// machine, made repeatable.
import { existsSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import zlib from 'node:zlib'
import { CONSENT_PREPARE, consentScenarios } from './consent.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const base = args.base
const blocked = args.blocked || ''
const canary = args.canary || ''
const CPU_THROTTLE = Number(process.env.CAKE_CPU_THROTTLE || 1)
const out = args.out
const VIEWPORT = { width: 1280, height: 900 }
const SETTLE_MS = 1500 // after leaving the site: let keepalive uploads land before the context closes

// Made-up checkout details only (no real personal information in tests).
const CHECKOUT_CARD = '4242 4242 4242 4242'
export const CHECKOUT = {
  email: 'visitor@example.test', fullname: 'Test Visitor', address: '1 Test Street', city: 'Testville',
  postcode: '00000', cardname: 'Test Visitor', cardnumber: CHECKOUT_CARD, expiry: '12/29', cvc: '123'
}
const card = args.card || CHECKOUT_CARD // a made-up card number only this run types (privacy scenario)

const BOUNCE_PAGES = [
  '/demo', '/demo?page=2', '/demo?page=3', '/demo?cat=Tops', '/demo?q=shirt',
  ...['tote', 'beanie', 'linen-shirt', 'socks', 'hoodie', 'denim-jacket', 'classic-tee', 'rain-jacket', 'cap',
    'shorts', 'scarf', 'chinos', 'kids-tee', 'belt', 'bottle'].map((id) => `/demo/product?id=${id}`),
  '/demo/cart', '/demo/checkout', '/demo/done', '/pages/plain.html'
]

const between = (low, high) => low + Math.random() * (high - low)
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function launch() {
  const app = 'chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
  const guess = path.join(process.env.HOME, 'Library/Caches/ms-playwright/chromium-1228', app)
  const executablePath = process.env.CAKE_CHROME || (existsSync(guess) ? guess : undefined)
  return chromium.launch({ executablePath })
}

function track(page, log) {
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame() || !frame.url().startsWith(base)) return
    const url = new URL(frame.url())
    log.pages.push(url.pathname + url.search)
  })
}

async function noteClick(log, locator, selector) {
  const isBlocked = blocked ? await locator.evaluate((el, sel) => !!el.closest(sel), blocked) : false
  log.clicks.push({ page: log.pages.length, selector, blocked: isBlocked })
}

async function settled(page) {
  await page.waitForLoadState('domcontentloaded')
}

// ---------------------------------------------------------------- direct: a script's way
async function directClick(page, log, selector) {
  const locator = page.locator(selector).first()
  await noteClick(log, locator, selector)
  await locator.click()
  await settled(page)
}

async function shopDirect(page, log) {
  const records = watchRecords(page)
  await page.goto(base + '/demo')
  await page.fill('#q', 'classic')
  await directClick(page, log, '.search button[type=submit]')
  await directClick(page, log, '.card h3 a[href$="id=classic-tee"]')
  await directClick(page, log, 'label:has(input[value="Blue"])')
  await page.selectOption('#size', 'M')
  await directClick(page, log, '#add')
  await directClick(page, log, '.cartlink')
  await directClick(page, log, '#checkout')
  for (const [field, value] of Object.entries(CHECKOUT)) await page.fill('#' + field, value)
  await page.selectOption('#country', 'Other')
  await directClick(page, log, '#agree')
  await directClick(page, log, '#place')
  await page.waitForURL('**/demo/done')
  await records.until(null, VISIT_KINDS)
}

// ---------------------------------------------------------------- humanlike: curved paths, pauses, wheel, keys
let mouse = { x: 0, y: 0 }

async function moveTo(page, x, y) {
  const steps = Math.round(between(18, 40))
  const bend = { x: between(-120, 120), y: between(-80, 80) }
  const start = { ...mouse }
  for (let i = 1; i <= steps; i++) {
    const t = i / steps
    const ease = t * t * (3 - 2 * t)
    const cx = (start.x + x) / 2 + bend.x
    const cy = (start.y + y) / 2 + bend.y
    const px = (1 - ease) ** 2 * start.x + 2 * (1 - ease) * ease * cx + ease ** 2 * x + between(-1.5, 1.5)
    const py = (1 - ease) ** 2 * start.y + 2 * (1 - ease) * ease * cy + ease ** 2 * y + between(-1.5, 1.5)
    await page.mouse.move(px, py)
    await sleep(between(6, 22))
  }
  await page.mouse.move(x, y)
  mouse = { x, y }
}

async function wheelIntoView(page, locator) {
  for (let i = 0; i < 30; i++) {
    const box = await locator.boundingBox()
    if (box && box.y > 40 && box.y + box.height < VIEWPORT.height - 40) return box
    await page.mouse.wheel(0, box && box.y < 40 ? -between(90, 140) : between(90, 140))
    await sleep(between(60, 160))
  }
  return locator.boundingBox()
}

async function humanClick(page, log, selector) {
  const locator = page.locator(selector).first()
  const box = await wheelIntoView(page, locator)
  await moveTo(page, box.x + box.width * between(0.25, 0.75), box.y + box.height * between(0.3, 0.7))
  await sleep(between(150, 600))
  await noteClick(log, locator, selector)
  await page.mouse.down()
  await sleep(between(60, 140))
  await page.mouse.up()
  await settled(page)
  await sleep(between(300, 900))
}

async function humanType(page, text) {
  for (const ch of text) {
    await page.keyboard.type(ch)
    await sleep(between(50, 170))
  }
}

// Records cake.js sends only once its detectors have run in idle time (test_capture.py): each page's botd and tasks,
// and the visit's one frames record. A run waits for them before it closes, up to a deadline, instead of closing at
// once: on a fast walk or under load they came after the browser had closed, and the run lacked them.
const LATE_KINDS = ['botd', 'tasks']
const VISIT_KINDS = ['frames']
const LATE_DEADLINE_MS = 30000

/** Watches the batches cake.js posts to collect; until(path, kinds) waits until the page at `path` (any page, for
 *  null) has sent every kind in `kinds`, or the deadline passes. */
function watchRecords(page) {
  const kinds = new Map()
  page.on('request', (request) => {
    const url = new URL(request.url())
    if (request.method() !== 'POST' || !url.pathname.endsWith('/collect')) return
    const body = request.postDataBuffer()
    if (!body) return
    let batch
    try { batch = JSON.parse((url.searchParams.get('z') === 'gzip' ? zlib.gunzipSync(body) : body).toString('utf8')) } catch { return }
    const at = new URL(batch.u).pathname
    for (const where of [at, null]) {
      if (!kinds.has(where)) kinds.set(where, new Set())
      for (const record of batch.x || []) kinds.get(where).add(record.ty)
    }
  })
  return {
    async until(at, wanted) {
      const deadline = Date.now() + LATE_DEADLINE_MS
      while (Date.now() < deadline && !wanted.every((kind) => kinds.get(at)?.has(kind))) await sleep(100)
    },
  }
}

async function shopHumanlike(page, log) {
  const records = watchRecords(page)
  mouse = { x: between(200, 900), y: between(100, 600) }
  await page.goto(base + '/demo')
  await sleep(between(600, 1200))
  await humanClick(page, log, '#q')
  await humanType(page, 'classic')
  await humanClick(page, log, '.search button[type=submit]')
  await humanClick(page, log, '.card h3 a[href$="id=classic-tee"]')
  await humanClick(page, log, 'label:has(input[value="Blue"])')
  await humanClick(page, log, '#size')
  await page.selectOption('#size', 'M')
  await humanClick(page, log, '#add')
  await humanClick(page, log, '.cartlink')
  await humanClick(page, log, '#checkout')
  for (const [field, value] of Object.entries(CHECKOUT)) {
    await humanClick(page, log, '#' + field)
    await humanType(page, value)
  }
  await page.selectOption('#country', 'Other')
  await humanClick(page, log, '#agree')
  await humanClick(page, log, '#place')
  await page.waitForURL('**/demo/done')
  await records.until('/demo/done', LATE_KINDS)
}

// ---------------------------------------------------------------- bounce: open, leave after 0.3–0.8 s
async function bounce(page, log) {
  for (const url of BOUNCE_PAGES) {
    await page.goto(base + url, { waitUntil: 'domcontentloaded' })
    await sleep(between(300, 800))
  }
}

// ---------------------------------------------------------------- privacy: what must never reach cake
async function typeInto(page, locator, text) {
  await locator.click()
  await page.keyboard.type(text, { delay: between(5, 25) })
}

async function privacy(page, log) {
  await page.goto(base + '/pages/private.html')
  for (const field of ['#name', '#secret', '#pw', '#notes', '#note']) await typeInto(page, page.locator(field), canary)
  await typeInto(page, page.locator('#cc'), card)
  const frame = page.frameLocator('#pay')
  await typeInto(page, frame.locator('#holder'), canary)
  await typeInto(page, frame.locator('#card'), card)
  await sleep(600)
  // The shop's checkout, the canary in every text field: typed key by key in some, filled at once in others.
  await page.goto(base + '/demo/product?id=classic-tee')
  await page.selectOption('#size', 'M')
  await page.click('#add')
  await page.goto(base + '/demo/checkout')
  await typeInto(page, page.locator('#email'), canary + '@example.test')
  await typeInto(page, page.locator('#fullname'), canary)
  await page.fill('#address', canary)
  await page.fill('#city', canary)
  await typeInto(page, page.locator('#postcode'), canary)
  await typeInto(page, page.locator('#cardname'), canary)
  await typeInto(page, page.locator('#cardnumber'), CHECKOUT.cardnumber)
  await page.fill('#expiry', CHECKOUT.expiry)
  await page.fill('#cvc', CHECKOUT.cvc)
  await page.selectOption('#country', 'Other')
  await page.click('#agree')
  await page.click('#place')
  await settled(page)
}

// ---------------------------------------------------------------- hidden: what the site owner hides (S5.5)
// pages/hidden.html, with the collector's cake.js carrying hide_selectors (test_privacy_recording.py): the canary typed
// into an ordinary field and into one the owner hides.
async function hidden(page, log) {
  await page.goto(base + '/pages/hidden.html')
  await typeInto(page, page.locator('#open'), canary)
  await typeInto(page, page.locator('#owner-note'), canary)
  await sleep(600)
}

// ---------------------------------------------------------------- timing: with and without cake.js
// Long tasks (over 50 ms on the main thread), seen from before any script of the page runs.
function watchLongTasks() {
  window.__longTasks = []
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__longTasks.push(Math.round(entry.duration))
    }).observe({ type: 'longtask', buffered: true })
  } catch (e) {
    window.__longTasks = null
  }
}

async function measure(browser, url) {
  const context = await browser.newContext({ viewport: VIEWPORT })
  await context.addInitScript(watchLongTasks)
  const page = await context.newPage()
  const cdp = await context.newCDPSession(page)
  await cdp.send('Performance.enable')
  await page.goto(url, { waitUntil: 'load' })
  await sleep(3000) // idle-time probes, BotD and botscent's later passes are included
  const metrics = Object.fromEntries((await cdp.send('Performance.getMetrics')).metrics.map((m) => [m.name, m.value]))
  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0]
    const fcp = performance.getEntriesByName('first-contentful-paint')[0]
    const longTasks = window.__longTasks || []
    return { dcl: nav.domContentLoadedEventEnd, load: nav.loadEventEnd, fcp: fcp ? fcp.startTime : null,
      long_tasks: longTasks.length, longest_task: longTasks.length ? Math.max(...longTasks) : 0 }
  })
  await context.close()
  return { ...timing, script_ms: metrics.ScriptDuration * 1000, task_ms: metrics.TaskDuration * 1000 }
}

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b)
  return s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2
}

async function timing(browser, runs) {
  const result = {}
  for (const page of ['/pages/plain.html', '/demo']) {
    const samples = { cake: [], nocake: [] }
    for (let i = 0; i < runs; i++) {
      const order = i % 2 ? ['nocake', 'cake'] : ['cake', 'nocake']
      for (const variant of order) {
        const url = base + page + (variant === 'nocake' ? (page.includes('?') ? '&' : '?') + 'nocake=1' : '')
        samples[variant].push(await measure(browser, url))
      }
    }
    const summary = {}
    for (const key of ['dcl', 'load', 'fcp', 'script_ms', 'task_ms', 'long_tasks', 'longest_task']) {
      const withCake = median(samples.cake.map((s) => s[key]))
      const without = median(samples.nocake.map((s) => s[key]))
      summary[key] = { with_cake: withCake, without, added: withCake - without }
    }
    result[page] = { runs, summary, samples }
  }
  await writeFile(path.join(out, 'timing.json'), JSON.stringify(result, null, 2))
}

// What a scenario needs in its browser context before its page opens.
const PREPARE = { ...CONSENT_PREPARE }

async function slowDown(context, page) {
  if (CPU_THROTTLE <= 1) return
  const cdp = await context.newCDPSession(page)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: CPU_THROTTLE })
}

const SCENARIOS = {
  direct: shopDirect,
  humanlike: shopHumanlike,
  bounce,
  privacy,
  hidden,
  ...consentScenarios(base)
}

async function main() {
  await mkdir(out, { recursive: true })
  const browser = await launch()
  try {
    for (const item of args.plan.split(',')) {
      const [scenario, count] = item.split(':')
      const runs = Number(count || 1)
      if (scenario === 'timing') {
        await timing(browser, runs)
        continue
      }
      for (let run = 1; run <= runs; run++) {
        const context = await browser.newContext({ viewport: VIEWPORT })
        if (PREPARE[scenario]) await PREPARE[scenario](context)
        const page = await context.newPage()
        await slowDown(context, page)
        const log = { scenario, run, pages: [], clicks: [], marks: {}, started: Date.now() }
        track(page, log)
        await SCENARIOS[scenario](page, log)
        await sleep(between(300, 800))
        await page.goto('about:blank') // leave the site: the last page's exit upload goes now
        await sleep(SETTLE_MS)
        log.ended = Date.now()
        await context.close()
        await writeFile(path.join(out, `${scenario}-${run}.json`), JSON.stringify(log, null, 2))
      }
    }
  } finally {
    await browser.close()
  }
}

await main()
