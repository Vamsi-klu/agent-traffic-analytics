// Runs cake.js's start (agentcake/static/src/cake_main.js) with its real session and transport parts (session.js,
// transport.js) in Node, every other part a stand-in that does nothing, and a clock that moves on at every read, as
// time passes while a page starts; prints what happened as JSON for tests/browser/test_startup_logic.py.
//   node tests/browser/startup_logic.mjs
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const data = (name) => JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', name), 'utf8'))
const CFG = data('cakejs.json').script
CFG.privacy = data('privacy.json').page // the build adds it to CFG (cakejs.json "build" "data")
const part = (name) => readFileSync(path.join(repo, 'agentcake', 'static', 'src', name), 'utf8')
const SOURCES = ['session.js', 'transport.js', 'cake_main.js'].map(part)
const T0 = 1794518371300
const SITE_KEY = 'ck_startup_test'

/** A part this harness does not run: any property is another stand-in, any call does nothing. */
function standIn() {
  const kept = {}
  return new Proxy(function () {}, {
    get: (_, key) => (key in kept ? kept[key] : (kept[key] = standIn())),
    apply: () => undefined
  })
}

/** cake.js starting on a page, sessionStorage holding `storage`; the clock moves on 1 ms at each read. Returns whether
 * it threw, the session id stored, and the batches its first flush sends (their session id and record kinds). */
function start(storage) {
  const store = new Map(Object.entries(storage))
  const pushed = []
  const sent = []
  let clock = T0
  let ids = 0
  const base = {
    off: false,
    now: () => clock++,
    round: (value) => value,
    randomId: () => `id${++ids}`,
    safe: (fn) => { try { return fn() } catch (e) { return String(e) } },
    fault: (where, error) => pushed.push(['fault', where, String((error && error.message) || error)]),
    store: {
      get: (key) => (store.has(key) ? store.get(key) : null),
      set: (key, value) => { store.set(key, value); return true },
      remove: (key) => { store.delete(key); return true }
    },
    source: { fields: () => ({ rd: '', utm: {}, ck: [], lang: 'en-US', tzo: 0 }) }
  }
  const C = new Proxy(base, { get: (target, key) => (key in target ? target[key] : (target[key] = standIn())) })
  const page = {
    TAG: { src: 'https://cake.example/cake.js', getAttribute: (name) => (name === CFG.attr.site ? SITE_KEY : null) },
    RUNTIME: {},
    BUILD: 'startup-test',
    STARTED: 0,
    window: {},
    document: { visibilityState: 'visible', hasFocus: () => true, prerendering: false },
    location: { origin: 'https://shop.example', pathname: '/', search: '' },
    navigator: { userAgent: 'node', webdriver: false },
    performance: { timeOrigin: T0, now: () => clock - T0, getEntriesByType: () => [] },
    history: { length: 1 },
    setTimeout: () => 0, // no tick runs: the harness flushes once itself
    clearTimeout: () => undefined,
    fetch: (url, init) => {
      sent.push(JSON.parse(new TextDecoder().decode(init.body)))
      return Promise.resolve({ ok: true, status: 204 })
    }
  }
  const names = ['C', 'CFG', ...Object.keys(page)]
  let threw = null
  try {
    for (const source of SOURCES) {
      new Function(...names, source)(C, CFG, ...Object.values(page)) // eslint-disable-line no-new-func
    }
    C.flush('timer')
  } catch (e) {
    threw = String((e && e.message) || e)
  }
  const batches = sent.map((batch) => ({ s: batch.s, x: batch.x.map((record) => [record.ty, record.t - T0]) }))
  return { threw, stored: store.get(CFG.storage.session) || null, batches, faults: pushed }
}

const idle = CFG.session.idle_ms
const cases = {
  // the tab's session went quiet exactly idle_ms before the page began: still the same session at that moment
  edge_of_idle: start({ [CFG.storage.session]: 'old', [CFG.storage.clock]: JSON.stringify({ s: T0 - 2 * idle, l: T0 - idle }) }),
  // well inside the idle time, and long after it
  recent: start({ [CFG.storage.session]: 'old', [CFG.storage.clock]: JSON.stringify({ s: T0 - idle, l: T0 - 60000 }) }),
  expired: start({ [CFG.storage.session]: 'old', [CFG.storage.clock]: JSON.stringify({ s: T0 - 3 * idle, l: T0 - 2 * idle }) })
}
process.stdout.write(JSON.stringify(cases))
