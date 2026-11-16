// Runs cake.js's identify and visitor parts (agentcake/static/src/identify.js, visitor.js, with util.js's C.hex) on
// their own in Node, with Node's WebCrypto and stand-ins for the parts they talk to (localStorage, the session, the
// transport's header, faults), and prints what happened as JSON for tests/browser/test_identify_logic.py.
//   node tests/browser/identify_logic.mjs
import { webcrypto } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const CFG = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const part = (name) => readFileSync(path.join(repo, 'agentcake', 'static', 'src', name), 'utf8')
const SOURCES = ['util.js', 'visitor.js', 'identify.js'].map(part)
const T0 = 1794518371300
const KEY_A = 'ck_site_a'
const KEY_B = 'ck_site_b'

/** A localStorage stand-in; refuse: every call throws, as in a browser with storage turned off. */
function fakeStorage(items = {}, refuse = false) {
  const map = new Map(Object.entries(items))
  const guard = () => { if (refuse) throw new Error('storage refused') }
  return {
    map,
    getItem: (key) => { guard(); return map.has(key) ? map.get(key) : null },
    setItem: (key, value) => { guard(); map.set(key, String(value)) },
    removeItem: (key) => { guard(); map.delete(key) }
  }
}

/** The three parts, with stand-ins; stored: what localStorage holds before; crypto: what window.crypto is. */
function make({ stored = {}, crypto = webcrypto, refuse = false } = {}) {
  const storage = fakeStorage(stored, refuse)
  const log = []
  let ids = 0
  const C = {
    clock: T0,
    session: {
      forget: () => log.push(['session.forget']),
      restart: (t, why, between) => { log.push(['session.restart', why]); between(); log.push(['session.new']) }
    },
    transport: {
      identity: (hash) => log.push(['header.idh', hash]),
      visitor: (id) => log.push(['header.vid', id])
    },
    push: () => {}
  }
  const window = { crypto }
  const performance = { timeOrigin: T0, now: () => C.clock - T0 }
  for (const source of SOURCES) {
    new Function('C', 'CFG', 'window', 'crypto', 'localStorage', 'sessionStorage', 'performance', source)( // eslint-disable-line no-new-func
      C, CFG, window, crypto, storage, fakeStorage(), performance)
  }
  // util.js has made its own of these: the stand-ins replace them
  C.randomId = () => `visitor${++ids}`
  C.now = () => C.clock
  C.fault = (where, error) => log.push(['fault', where, String((error && error.message) || error)])
  return { C, log, storage }
}

const entry = (storage) => JSON.parse(storage.map.get(CFG.storage.visitor) || 'null')
const settle = () => new Promise((resolve) => setTimeout(resolve, 20))
const cases = {}

{ // the same id gives the same hash, kept with the visitor id and put into the header once
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-42')
  await settle()
  const first = entry(storage)
  C.identity.identify('user-42')
  await settle()
  cases.stable = { first, again: entry(storage), log }
}

{ // another site key, another hash; a number is taken as its string
  const { C, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_B)
  C.identity.identify('user-42')
  await settle()
  const byKey = entry(storage).h
  C.identity.reset()
  C.identity.identify(42)
  await settle()
  cases.other_key = { byKey, number: entry(storage).h }
}

{ // what is not an id is refused, and the fault says why without the value
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  for (const value of ['', '   ', null, undefined, {}, ['x'], NaN, 'undefined', 'NULL', 'distinct_id']) {
    C.identity.identify(value)
  }
  await settle()
  cases.refused = { entry: entry(storage), log }
}

{ // without SubtleCrypto (a page that is not https or localhost) nothing is kept or sent
  const { C, log, storage } = make({ crypto: {} })
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-42')
  await settle()
  cases.no_crypto = { entry: entry(storage), log }
}

{ // before cake.js starts nothing is stored or sent; once it starts the hash is kept
  const { C, log, storage } = make()
  C.identity.identify('user-42')
  await settle()
  const before = { stored: Object.fromEntries(storage.map), log: log.slice() }
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  await settle()
  cases.before_start = { before, after: entry(storage), log }
}

{ // reset() after start: a new session, and between its batches a new visitor id without the hash
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-a')
  await settle()
  const identified = entry(storage)
  C.clock = T0 + 1000
  C.identity.reset()
  cases.reset = { identified, after: entry(storage), hash: C.visitor.hash(), log }
}

{ // reset() before start deletes the stored id, its hash and the session id, so start() begins new ones
  const stored = { [CFG.storage.visitor]: JSON.stringify({ id: 'old', t: T0, h: 'a'.repeat(64) }) }
  const { C, log, storage } = make({ stored })
  C.identity.reset()
  cases.reset_before_start = { stored: Object.fromEntries(storage.map), log, nextId: C.visitor.id(T0) }
}

{ // a page view begins with the stored hash; a year without use forgets the id and its hash
  const stored = { [CFG.storage.visitor]: JSON.stringify({ id: 'kept', t: T0, h: 'b'.repeat(64) }) }
  const fresh = make({ stored })
  const keptId = fresh.C.visitor.id(T0 + 1000)
  const later = make({ stored })
  const laterId = later.C.visitor.id(T0 + CFG.visitor.max_age_ms + 1)
  cases.page_view = { keptId, kept: fresh.C.visitor.hash(), laterId, later: later.C.visitor.hash() }
}

{ // identify A, reset, identify B at once: the hash still being made for A is dropped
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-a')
  C.identity.reset()
  C.identity.identify('user-b')
  await settle()
  cases.shared = { entry: entry(storage), log }
}

{ // identify B over A without reset: the hash is replaced, the visitor id stays
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-a')
  await settle()
  C.identity.identify('user-b')
  await settle()
  cases.replaced = { entry: entry(storage), log }
}

{ // stop() while a hash is being made: it is not kept
  const { C, log, storage } = make()
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-a')
  C.identity.forget()
  C.visitor.forget()
  await settle()
  cases.stopped = { stored: Object.fromEntries(storage.map), log }
}

{ // localStorage refused: the hash still goes with this page's batches
  const { C, log } = make({ refuse: true })
  C.visitor.id(T0)
  C.identity.start(KEY_A)
  C.identity.identify('user-42')
  await settle()
  cases.no_storage = { hash: C.visitor.hash(), log }
}

process.stdout.write(JSON.stringify({ keys: { a: KEY_A, b: KEY_B }, separator: CFG.identify.separator, cases }))
