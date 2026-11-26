// Drives Chromium for tests/browser/test_session_tabs.py: a browser's tabs of a site share one session, in real tabs.
//   node tests/browser/session_tabs.mjs --base http://127.0.0.1:<port> --out <dir>
// Writes <out>/rules.json: cake.js's session part in real tabs, each scenario in a profile (browser context) of its
//   own, on a clock the test sets. Each tab opens a page of the stand-in collector without cake.js and runs util.js,
//   visitor.js and session.js from agentcake/static/src/ there, with the tab's real sessionStorage and localStorage and
//   stand-ins for the parts session.js talks to (as tests/browser/session_logic.mjs does in Node). A browser cannot
//   be made to wait 30 minutes (Playwright's fake clock moves performance.now() but not the timeStamp of DOM events),
//   so each activity is given its time.
// And <out>/script.json: the whole cake.js on the test pages, in real time: two tabs, a window one of them opens with
//   window.open, then reset() in the first tab and a click in the second (the uploads are in <out>/collect.ndjson).
import { readFileSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { executablePath } from './chromium.mjs'

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(here, '..', '..')
const require = createRequire(import.meta.url)
const { chromium } = require(process.env.CAKE_PLAYWRIGHT || path.join(repo, 'web', 'node_modules', 'playwright-core'))
const CFG = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const part = (name) => readFileSync(path.join(repo, 'agentcake', 'static', 'src', name), 'utf8')
const SOURCES = { util: part('util.js'), visitor: part('visitor.js'), session: part('session.js'), cfg: CFG }

const argv = process.argv.slice(2)
const args = Object.fromEntries(argv.flatMap((arg, i) => (arg.startsWith('--') ? [[arg.slice(2), argv[i + 1]]] : [])))
const MINUTE = 60 * 1000
const HOUR = 60 * MINUTE
const T0 = 1794518371300
const SEND_MS = CFG.batch.interval_min_ms + 1500 // a timer batch has gone, and its answer arrived
const SYNC_MS = CFG.session.persist_every_ms + 200 // a tab reads the browser's session again after this much activity
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const blank = (n) => `${args.base}/pages/plain.html?nocake=1&tab=${n}` // a page of the site without cake.js

/** In the page: the session part with stand-ins, on window.__cake (see the top). */
function install({ util, visitor, session, cfg }) {
  const log = []
  const C = {}
  new Function('C', 'CFG', util)(C, cfg) // eslint-disable-line no-new-func
  const state = { now: 0, ids: null, vid: null }
  C.now = () => state.now
  C.push = (stream, record) => log.push(['push', stream, record])
  C.flush = (why) => log.push(['flush', why])
  C.transport = {
    session: (ids) => { state.ids = ids; log.push(['transport', ids]) },
    visitor: (id) => { state.vid = id; log.push(['visitor', id]) },
    identity: (hash) => log.push(['identity', hash])
  }
  C.replay = { snapshot: () => log.push(['snapshot']) }
  C.source = { fields: () => ({}) }
  new Function('C', 'CFG', visitor)(C, cfg) // eslint-disable-line no-new-func
  new Function('C', 'CFG', session)(C, cfg) // eslint-disable-line no-new-func
  const admit = (stream, record) => { state.now = record.t; C.session.admit(stream, record) }
  window.__cake = {
    begin: (t) => { // cake_main.js: the ids, the visitor id, then the page record (the page view's activity)
      state.ids = C.session.begin(t)
      state.vid = C.visitor.id(t)
      admit('x', { ty: 'page', t })
      return state
    },
    act: (t) => { admit('r', { ty: 'click', t }); return state },
    reset: (t) => { // identify.js reset(): a new visitor id between the old session's batches and the new one's
      C.session.restart(t, cfg.session.why.reset, () => C.transport.visitor(C.visitor.renew(t)))
      return state
    },
    whys: () => log.filter((entry) => entry[0] === 'push' && entry[2].ty === cfg.session.record).map((e) => e[2].why),
    log
  }
}

/** A tab: a page of the site (without cake.js) with the session part installed. */
async function open(context, n, { before } = {}) {
  const page = await context.newPage()
  page.on('pageerror', (error) => errors.push(String(error)))
  await page.goto(blank(n))
  if (before) await page.evaluate(before.fn, before.arg)
  await page.evaluate(install, SOURCES)
  return page
}

const errors = []
const call = (page, name, t) => page.evaluate(({ name, t }) => window.__cake[name](t), { name, t })
const whys = (page) => page.evaluate(() => window.__cake.whys())
const storage = (page) => page.evaluate(() => ({ tab: { ...sessionStorage }, browser: { ...localStorage } }))
const ids = (state) => state.ids

/** Each scenario in a profile of its own. */
async function scenario(browser, fn, contextOptions = {}) {
  const context = await browser.newContext(contextOptions)
  try {
    return await fn(context)
  } finally {
    await context.close()
  }
}

const rules = {
  async two_tabs(context) {
    const one = await open(context, 1)
    const two = await open(context, 2)
    return { one: ids(await call(one, 'begin', T0)), two: ids(await call(two, 'begin', T0 + MINUTE)) }
  },

  // tab 1 acts every 5 minutes; tab 2, quiet for 40 minutes, then acts: the same browser session, tab 2's own cut
  async idle_tab(context) {
    const one = await open(context, 1)
    const two = await open(context, 2)
    const first = { one: ids(await call(one, 'begin', T0)), two: ids(await call(two, 'begin', T0)) }
    for (let minutes = 5; minutes <= 40; minutes += 5) await call(one, 'act', T0 + minutes * MINUTE)
    const after = {
      one: ids(await call(one, 'act', T0 + 40 * MINUTE + SYNC_MS)),
      two: ids(await call(two, 'act', T0 + 40 * MINUTE + 2 * SYNC_MS))
    }
    return { first, after, whys: { one: await whys(one), two: await whys(two) } }
  },

  // no tab acts for 31 minutes: the next activity begins the browser's next session, the other tab takes it
  async all_idle(context) {
    const one = await open(context, 1)
    const two = await open(context, 2)
    const first = { one: ids(await call(one, 'begin', T0)), two: ids(await call(two, 'begin', T0 + MINUTE)) }
    const after = {
      one: ids(await call(one, 'act', T0 + 32 * MINUTE)),
      two: ids(await call(two, 'act', T0 + 33 * MINUTE))
    }
    return { first, after, whys: { one: await whys(one), two: await whys(two) } }
  },

  // both tabs busy (tab 2 opened 12 hours later): the browser's session ends at 24 hours; tab 1 acts first after them
  async max(context) {
    const one = await open(context, 1)
    const two = await open(context, 2)
    const first = { one: ids(await call(one, 'begin', T0)) }
    let t = T0
    for (; t <= T0 + 24 * HOUR; t += 10 * MINUTE) {
      if (t === T0 + 12 * HOUR) first.two = ids(await call(two, 'begin', t))
      await call(one, 'act', t)
      if (first.two && t + SYNC_MS <= T0 + 24 * HOUR) await call(two, 'act', t + SYNC_MS)
    }
    return { first, after: { one: ids(await call(one, 'act', t)), two: ids(await call(two, 'act', t + SYNC_MS)) },
      whys: { one: await whys(one), two: await whys(two) } }
  },

  // window.open (Chromium copies sessionStorage to it) and a duplicated tab (its storage copied as Chrome copies it)
  // get a new tab id and tab session; the original keeps its own, and a reload of it keeps them
  async copies(context) {
    const one = await open(context, 1)
    const first = ids(await call(one, 'begin', T0))
    const copied = await storage(one)
    const [popup] = await Promise.all([
      context.waitForEvent('page'),
      one.evaluate((url) => { window.open(url) }, blank(3))
    ])
    popup.on('pageerror', (error) => errors.push(String(error)))
    await popup.waitForLoadState()
    const popupBefore = await storage(popup)
    await popup.evaluate(install, SOURCES)
    const opened = ids(await call(popup, 'begin', T0 + MINUTE))
    const seed = {
      fn: (items) => { for (const [key, value] of Object.entries(items)) sessionStorage.setItem(key, value) },
      arg: copied.tab
    }
    const duplicate = await open(context, 4, { before: seed })
    const duplicated = ids(await call(duplicate, 'begin', T0 + 2 * MINUTE))
    const original = {
      ids: ids(await call(one, 'act', T0 + 3 * MINUTE)), whys: await whys(one), stored: await storage(one)
    }
    await one.reload()
    await one.evaluate(install, SOURCES)
    const reloaded = ids(await call(one, 'begin', T0 + 4 * MINUTE))
    return { first, popupBefore: popupBefore.tab, opened, duplicated, original, reloaded }
  },

  // reset() in tab 1: a new browser session, tab id, tab session and visitor; tab 2 takes the session and the visitor
  async reset(context) {
    const one = await open(context, 1)
    const two = await open(context, 2)
    const first = { one: await call(one, 'begin', T0), two: await call(two, 'begin', T0) }
    const one2 = await call(one, 'reset', T0 + MINUTE)
    const two2 = await call(two, 'act', T0 + 2 * MINUTE)
    const log = await two.evaluate(() => window.__cake.log.map((entry) => entry.slice(0, 2)))
    return { first, after: { one: one2, two: two2 }, whys: { one: await whys(one), two: await whys(two) }, log }
  },

  // localStorage refused: each tab has a browser session of its own, kept in its sessionStorage, and nothing throws
  async refused(context) {
    const one = await open(context, 1)
    const firstPage = await call(one, 'begin', T0)
    await call(one, 'act', T0 + MINUTE)
    await one.reload()
    await one.evaluate(install, SOURCES)
    const secondPage = await call(one, 'begin', T0 + 2 * MINUTE)
    const two = await open(context, 2)
    const otherTab = await call(two, 'begin', T0 + 3 * MINUTE)
    return { pages: [ids(firstPage), ids(secondPage), ids(otherTab)], whys: await whys(one) }
  },

  // localStorage takes no writes (a full quota) and holds a session that ended: this page's own, no cut per activity
  async quota(context) {
    const one = await open(context, 1)
    await one.evaluate(({ key, stale }) => {
      window.__realSetItem.call(localStorage, key.browser_session, stale.b)
      window.__realSetItem.call(localStorage, key.browser_clock, JSON.stringify(stale))
    }, { key: CFG.storage, stale: { b: 'bs-stale', s: T0 - 3 * HOUR, l: T0 - 2 * HOUR } })
    const first = ids(await call(one, 'begin', T0))
    for (let minutes = 1; minutes <= 20; minutes++) await call(one, 'act', T0 + minutes * MINUTE)
    const last = ids(await call(one, 'act', T0 + 21 * MINUTE))
    return { first, last, whys: await whys(one), stored: (await storage(one)).browser }
  }
}

const refuseLocalStorage = () => {
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    get() { throw new DOMException('The operation is insecure.', 'SecurityError') }
  })
}
const fullQuota = () => {
  const setItem = Storage.prototype.setItem
  window.__realSetItem = setItem
  Storage.prototype.setItem = function (key, value) {
    if (this === window.localStorage) throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
    return setItem.call(this, key, value)
  }
}
const INIT = { refused: refuseLocalStorage, quota: fullQuota }

/** The whole cake.js in real time (see the top); returns what each page kept at the end. */
async function script(context) {
  const page = async (url) => {
    const opened = await context.newPage()
    opened.on('pageerror', (error) => errors.push(String(error)))
    await opened.goto(url)
    return opened
  }
  const poke = async (target) => { await target.click('#title'); await sleep(200) }
  const one = await page(`${args.base}/pages/plain.html`)
  const two = await page(`${args.base}/pages/plain.html?tab=2`)
  await poke(one)
  await poke(two)
  await sleep(SEND_MS)
  // tab 2 goes to another page of the site as a link would take it, then back: one tab, one tab id and session
  await Promise.all([two.waitForNavigation(), two.evaluate(() => { location.href = '/pages/plain.html?tab=2&page=2' })])
  await poke(two)
  await two.goBack() // from the back-forward cache where the browser keeps the page, else loaded again
  await poke(two)
  await sleep(SEND_MS)
  const [popup] = await Promise.all([
    context.waitForEvent('page'),
    one.evaluate((url) => { window.open(url) }, '/pages/plain.html?popup=1')
  ])
  popup.on('pageerror', (error) => errors.push(String(error)))
  await popup.waitForLoadState()
  await poke(popup)
  await sleep(SEND_MS)
  await one.evaluate(() => window.cake.reset())
  await poke(one)
  await sleep(SYNC_MS)
  await poke(two)
  await sleep(SEND_MS)
  const kept = {}
  for (const [name, target] of Object.entries({ one, two, popup })) kept[name] = await storage(target)
  return kept
}

await mkdir(args.out, { recursive: true })
const browser = await chromium.launch({ executablePath: executablePath() })
try {
  const found = {}
  for (const [name, fn] of Object.entries(rules)) {
    found[name] = await scenario(browser, async (context) => {
      if (INIT[name]) await context.addInitScript(INIT[name])
      return fn(context)
    })
  }
  found.errors = errors.splice(0)
  await writeFile(path.join(args.out, 'rules.json'), JSON.stringify(found, null, 2))
  const kept = await scenario(browser, script)
  await writeFile(path.join(args.out, 'script.json'), JSON.stringify({ kept, errors }, null, 2))
} finally {
  await browser.close()
}
