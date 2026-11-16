// Runs cake.js's session part (agentcake/static/src/session.js) on its own in Node, with stand-ins for the parts it
// talks to (C.store, C.flush, C.transport, C.push, C.replay, C.source) and a clock the cases set, and prints what
// happened as JSON for tests/browser/test_session_logic.py. A browser cannot be made to wait 30 minutes: Playwright's
// fake clock moves performance.now() but not the timeStamp of the DOM events the raw records are stamped with.
//   node tests/browser/session_logic.mjs
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const CFG = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const SOURCE = readFileSync(path.join(repo, 'agentcake', 'static', 'src', 'session.js'), 'utf8')
const MINUTE = 60 * 1000
const T0 = 1794518371300

/** A fresh session part with stand-ins; storage: what sessionStorage holds before it starts. */
function make(storage = {}) {
  const store = new Map(Object.entries(storage))
  const log = []
  let ids = 0
  const C = {
    clock: T0,
    now: () => C.clock,
    randomId: () => `id${++ids}`,
    store: {
      get: (key) => (store.has(key) ? store.get(key) : null),
      set: (key, value) => { store.set(key, value); return true },
      remove: (key) => { store.delete(key); return true }
    },
    flush: (why) => log.push(['flush', why]),
    transport: { session: (id) => log.push(['transport', id]) },
    push: (stream, record) => log.push(['push', stream, record]),
    replay: { snapshot: () => log.push(['snapshot']) },
    source: { fields: () => ({ rd: 'www.example.org', utm: {}, ck: [], lang: 'en-US', tzo: 0 }) }
  }
  new Function('C', 'CFG', SOURCE)(C, CFG) // eslint-disable-line no-new-func
  return { C, log, store }
}

const raw = (ty, t) => ({ ty, t })
const cases = {}

{ // activity within the idle time keeps the session; replay events are dropped once the tab is idle, signals are not
  const { C, log, store } = make()
  const first = C.session.begin(T0)
  const kept = C.session.admit('r', raw('pointermove', T0 + 29 * MINUTE))
  C.clock = T0 + 29 * MINUTE + 31 * MINUTE
  cases.idle_drop = {
    first, kept, stored: store.get(CFG.storage.session), log: log.slice(),
    replayWhileIdle: C.session.admit('e', { type: 3, timestamp: C.clock }),
    signalWhileIdle: C.session.admit('x', { ty: 'markers', t: C.clock }),
    keyWhileIdle: C.session.admit('r', raw('keydown', C.clock))
  }
  const rotated = C.session.admit('r', raw('click', C.clock + 1))
  cases.idle_rotation = { rotated, stored: store.get(CFG.storage.session), clock: JSON.parse(store.get(CFG.storage.clock)), log }
}

{ // a session that lasted 24 hours ends at the next activity, however busy
  const { C, log } = make()
  C.session.begin(T0)
  for (let t = T0; t <= T0 + 24 * 60 * MINUTE + 20 * MINUTE; t += 20 * MINUTE) {
    C.clock = t
    C.session.admit('r', raw('scroll', t))
  }
  cases.max_rotation = { log }
}

{ // a page view begins a new session when the stored clock has run out, and keeps an older cake.js's id without one
  const old = { s: T0 - 60 * MINUTE, l: T0 - 31 * MINUTE }
  const expired = make({ [CFG.storage.session]: 'old', [CFG.storage.clock]: JSON.stringify(old), [CFG.storage.page_number]: '4' })
  const fresh = make({ [CFG.storage.session]: 'old', [CFG.storage.clock]: JSON.stringify({ s: T0 - MINUTE, l: T0 - MINUTE }) })
  const older = make({ [CFG.storage.session]: 'old' })
  cases.begin = {
    expired: expired.C.session.begin(T0), expiredPageNumber: expired.store.get(CFG.storage.page_number),
    fresh: fresh.C.session.begin(T0), older: older.C.session.begin(T0)
  }
  older.C.session.admit('r', raw('click', T0 + 5000))
  cases.begin.olderClock = JSON.parse(older.store.get(CFG.storage.clock)) // its clock starts at that page view
}

{ // a page view counts as activity; forget() removes the id and its clock
  const { C, store } = make()
  C.session.begin(T0)
  C.session.admit('x', { ty: 'path', t: T0 + 40 * MINUTE, p: '/b' })
  const afterPath = store.get(CFG.storage.session)
  C.session.forget()
  cases.path_and_forget = { afterPath, session: store.get(CFG.storage.session), clock: store.get(CFG.storage.clock) }
}

console.log(JSON.stringify(cases))
