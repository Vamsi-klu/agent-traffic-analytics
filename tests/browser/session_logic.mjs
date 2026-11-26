// Runs cake.js's session part (agentcake/static/src/session.js) on its own in Node, with stand-ins for the parts it
// talks to (C.store and C.shared over Maps, C.flush, C.transport, C.push, C.replay, C.source, C.visitor, C.listen, the
// page's window and document) and a clock the cases set, and prints what happened as JSON for
// tests/browser/test_session_logic.py. A browser cannot be made to wait 30 minutes: Playwright's fake clock moves
// performance.now() but not the timeStamp of the DOM events the raw records are stamped with. The same part in real
// tabs, with their real storage, is tests/browser/session_tabs.mjs.
//   node tests/browser/session_logic.mjs
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..')
const CFG = JSON.parse(readFileSync(path.join(repo, 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const SOURCE = readFileSync(path.join(repo, 'agentcake', 'static', 'src', 'session.js'), 'utf8')
const KEY = CFG.storage
const MINUTE = 60 * 1000
const HOUR = 60 * MINUTE
const T0 = 1794518371300
let made = 0 // ids are unique across every page the cases make

/** A Map behind C.store's or C.shared's interface; refuse: writes fail, as with a full quota or storage turned off. */
function fakeStore(map, refuse = false) {
  return {
    get: (key) => (map.has(key) ? map.get(key) : null),
    set: (key, value) => { if (refuse) return false; map.set(key, value); return true },
    remove: (key) => { map.delete(key); return true }
  }
}

/** A page with a fresh session part. tab and browser: the Maps behind its sessionStorage and localStorage (pass the
 * same Map to make two pages of one tab, or two tabs of one browser). */
function make(options = {}) {
  const { tab = new Map(), browser = new Map(), refuseShared = false, prerendering = false, follow = null } = options
  const log = []
  const listeners = []
  const C = {
    clock: T0,
    now: () => C.clock,
    randomId: () => `id${++made}`,
    store: fakeStore(tab),
    shared: fakeStore(browser, refuseShared),
    flush: (why) => log.push(['flush', why]),
    transport: {
      session: (ids) => log.push(['transport', ids]),
      visitor: (id) => log.push(['visitor', id]),
      identity: (hash) => log.push(['identity', hash])
    },
    push: (stream, record) => log.push(['push', stream, record]),
    replay: { snapshot: () => log.push(['snapshot']) },
    source: { fields: () => ({ rd: 'www.example.org', utm: {}, ck: [], lang: 'en-US', tzo: 0 }) },
    visitor: { follow: () => follow },
    listen: (target, type, fn) => listeners.push({ target, type, fn })
  }
  const window = { name: 'window' }
  const document = { name: 'document', prerendering }
  new Function('C', 'CFG', 'window', 'document', SOURCE)(C, CFG, window, document) // eslint-disable-line no-new-func
  const fire = (type, event = {}) => listeners.filter((l) => l.type === type).forEach((l) => l.fn(event))
  return { C, log, tab, browser, fire, document }
}

/** What storage holds: the tab's and the browser's. */
function held({ tab, browser }) {
  return { tab: Object.fromEntries(tab), browser: Object.fromEntries(browser) }
}

/** A browser session `id` stored by another tab, with its clock. */
function storedBrowser(id, start, last) {
  return new Map([[KEY.browser_session, id], [KEY.browser_clock, JSON.stringify({ b: id, s: start, l: last })]])
}

/** A tab session `id` stored by an earlier page of the tab; b: the browser session its clock names (none: older). */
function storedTab(id, start, last, b) {
  const clock = b === undefined ? { s: start, l: last } : { s: start, l: last, b }
  return new Map([[KEY.session, id], [KEY.clock, JSON.stringify(clock)], [KEY.window, 'w-old']])
}

const raw = (ty, t) => ({ ty, t })
const rotations = (log) => log.filter((entry) => entry[0] === 'push' && entry[2].ty === CFG.session.record)
  .map((entry) => entry[2].why)
const cases = {}

{ // activity within the idle time keeps the session; replay events are dropped once the tab is idle, signals are not
  const page = make()
  const { C, log } = page
  const first = C.session.begin(T0)
  const kept = C.session.admit('r', raw('pointermove', T0 + 29 * MINUTE))
  C.clock = T0 + 29 * MINUTE + 31 * MINUTE
  cases.idle_drop = {
    first, kept, stored: held(page), log: log.slice(),
    replayWhileIdle: C.session.admit('e', { type: 3, timestamp: C.clock }),
    signalWhileIdle: C.session.admit('x', { ty: 'markers', t: C.clock }),
    keyWhileIdle: C.session.admit('r', raw('keydown', C.clock))
  }
  const rotated = C.session.admit('r', raw('click', C.clock + 1))
  cases.idle_rotation = { first, rotated, stored: held(page), log }
}

{ // a session that lasted 24 hours ends at the next activity, however busy
  const { C, log } = make()
  C.session.begin(T0)
  for (let t = T0; t <= T0 + 24 * HOUR + 20 * MINUTE; t += 20 * MINUTE) {
    C.clock = t
    C.session.admit('r', raw('scroll', t))
  }
  cases.max_rotation = { whys: rotations(log) }
}

{ // a page view keeps the tab's session while it lasts and belongs to the browser's; else it begins a new one
  const browser = () => storedBrowser('bs-old', T0 - 2 * HOUR, T0 - MINUTE)
  const page = (tab) => make({ tab, browser: browser() })
  const expired = page(storedTab('old', T0 - 60 * MINUTE, T0 - 31 * MINUTE, 'bs-old'))
  expired.tab.set(KEY.page_number, '4')
  const fresh = page(storedTab('old', T0 - MINUTE, T0 - MINUTE, 'bs-old'))
  const otherBrowser = page(storedTab('old', T0 - MINUTE, T0 - MINUTE, 'bs-before'))
  const olderClock = page(storedTab('old', T0 - MINUTE, T0 - MINUTE))
  const older = make({ tab: new Map([[KEY.session, 'old']]), browser: browser() })
  cases.begin = {
    expired: expired.C.session.begin(T0), expiredPageNumber: expired.tab.get(KEY.page_number) ?? null,
    fresh: fresh.C.session.begin(T0), freshClock: JSON.parse(fresh.tab.get(KEY.clock)),
    otherBrowser: otherBrowser.C.session.begin(T0),
    olderClock: olderClock.C.session.begin(T0),
    older: older.C.session.begin(T0)
  }
}

{ // a page view counts as activity; forget() removes every id and clock, the tab's and the browser's
  const page = make()
  const { C } = page
  C.session.begin(T0)
  C.session.admit('x', { ty: 'path', t: T0 + 40 * MINUTE, p: '/b' })
  const afterPath = held(page)
  C.session.forget()
  cases.path_and_forget = { afterPath, afterForget: held(page) }
}

{ // one tab, pages and activity at random: its session is cut where cake.js 0.6.1 cut it, by the tab's own clock
  // (session.js before the browser's session: t - last > idle_ms, else t - start > max_ms; a page view is activity)
  let seed = 7
  const random = () => (seed = (seed * 16807) % 2147483647) / 2147483647
  const gaps = [2000, 40000, 5 * MINUTE, 29 * MINUTE, 30 * MINUTE, 31 * MINUTE, 3 * HOUR, 23 * HOUR]
  const RANDOM_STEPS = 3000
  const BUSY_STEPS = 160 // then 20 minutes apart for over two days: sessions end at 24 hours
  const tab = new Map()
  const browser = new Map()
  let page = make({ tab, browser })
  let t = T0
  const pageView = (at) => { // cake_main.js: the page's ids, then its page record, the page view's activity
    const s = page.C.session.begin(at).s
    page.C.clock = at
    page.C.session.admit('x', { ty: 'page', t: at })
    return s
  }
  pageView(t)
  const got = []
  const expected = []
  let rule = { start: t, last: t }
  for (let step = 0; step < RANDOM_STEPS + BUSY_STEPS; step++) {
    t += step < RANDOM_STEPS ? gaps[Math.floor(random() * gaps.length)] * random() : 20 * MINUTE
    const why = t - rule.last > CFG.session.idle_ms ? 'idle' : t - rule.start > CFG.session.max_ms ? 'max' : null
    if (random() < 0.05) { // the next page of the tab
      page.C.session.save()
      page.fire('pagehide')
      const current = tab.get(KEY.session)
      page = make({ tab, browser })
      got.push([pageView(t) === current ? 'same' : 'new', t])
      expected.push([why ? 'new' : 'same', t])
    } else {
      page.C.clock = t
      page.log.length = 0
      page.C.session.admit('r', raw('click', t))
      const whys = rotations(page.log)
      got.push([whys.length ? whys[0] : 'same', t])
      expected.push([why || 'same', t])
    }
    rule = why ? { start: t, last: t } : { start: rule.start, last: Math.max(rule.last, t) }
  }
  cases.single_tab = { got, expected, steps: expected.length }
}

{ // a clock that names another session (another tab between its two writes) is no clock: no session ends for it
  const browser = new Map([[KEY.browser_session, 'bs-new'],
    [KEY.browser_clock, JSON.stringify({ b: 'bs-before', s: T0 - 30 * HOUR, l: T0 - 2 * HOUR })]])
  const page = make({ browser })
  const ids = page.C.session.begin(T0)
  page.C.session.admit('r', raw('click', T0 + MINUTE))
  cases.torn = { ids, whys: rotations(page.log), clock: JSON.parse(browser.get(KEY.browser_clock)) }
}

{ // localStorage takes no writes (full quota) and holds a session that ended: the browser's session is the page's own
  const browser = storedBrowser('bs-stale', T0 - 3 * HOUR, T0 - 2 * HOUR)
  const page = make({ browser, refuseShared: true })
  const ids = page.C.session.begin(T0)
  const steps = [5, 10, 20, 61, 65].map((minutes) => T0 + minutes * MINUTE) // 41 minutes between 20 and 61
  steps.forEach((t) => page.C.session.admit('r', raw('click', t)))
  const after = page.log.filter((entry) => entry[0] === 'transport').map((entry) => entry[1])
  cases.refused = { ids, whys: rotations(page.log), after, browser: Object.fromEntries(browser) }
}

{ // localStorage takes no writes, sessionStorage does: the browser's session is the tab's own, kept in sessionStorage,
  // so the tab's next page goes on with it and with the tab's session (as 0.6.1 kept a tab's session), not anew
  const tab = new Map()
  const browser = new Map()
  const first = make({ tab, browser, refuseShared: true })
  const firstIds = first.C.session.begin(T0)
  first.C.session.admit('r', raw('click', T0 + MINUTE))
  first.C.session.save() // the page is left: its clocks are written, and its mark goes
  first.fire('pagehide')
  const next = make({ tab, browser, refuseShared: true })
  const nextIds = next.C.session.begin(T0 + 2 * MINUTE)
  next.C.session.forget()
  cases.refused_pages = { first: firstIds, next: nextIds, localStorage: Object.fromEntries(browser),
    afterForget: held(next) }
}

{ // another tab's stop() (or reset() before start) removes the browser's session from localStorage: a tab still
  // recording never writes it back (not on its activity, not when it is left), and begins the next one at its next
  // activity, as posthog-js begins a new session when the id it stored is gone
  const browser = new Map()
  const tabA = make({ browser })
  const tabB = make({ browser })
  const ids = tabA.C.session.begin(T0)
  tabB.C.session.begin(T0 + 1000)
  tabA.C.session.forget() // the visitor said no in tab A: window.cake.stop()
  tabB.C.clock = T0 + 1500
  tabB.C.session.save() // tab B hidden: its clocks are written
  const afterSave = browser.get(KEY.browser_session) ?? null
  tabB.C.session.admit('r', raw('click', T0 + 3000))
  tabB.C.session.admit('r', raw('click', T0 + 5000))
  const sent = tabB.log.filter((entry) => entry[0] === 'transport').map((entry) => entry[1])
  cases.removed = { ids, afterSave, whys: rotations(tabB.log), sent, stored: browser.get(KEY.browser_session) ?? null }
}

{ // the mark: set when the page starts, removed when it is left unless another page's is there, set again on return
  const page = make()
  page.C.session.begin(T0)
  const mark = page.tab.get(KEY.window_open)
  page.fire('pagehide')
  const afterLeave = page.tab.get(KEY.window_open) ?? null
  page.fire('pageshow', { persisted: true })
  const afterReturn = page.tab.get(KEY.window_open)
  page.tab.set(KEY.window_open, 'another-page')
  page.fire('pagehide')
  cases.mark = { mark, afterLeave, afterReturn, othersKept: page.tab.get(KEY.window_open) }
}

{ // a page that finds a live page's mark holds a copy: a new tab id and tab session; the browser's session goes on
  const browser = storedBrowser('bs-live', T0 - HOUR, T0 - MINUTE)
  const tab = storedTab('s-original', T0 - HOUR, T0 - MINUTE, 'bs-live')
  tab.set(KEY.window_open, 'original-page')
  const page = make({ tab, browser })
  cases.copy = { ids: page.C.session.begin(T0), mark: tab.get(KEY.window_open) }
}

{ // a prerendered page's copy of its own tab's storage is no copy: kept, and marked and written once shown
  const browser = storedBrowser('bs-live', T0 - HOUR, T0 - MINUTE)
  const tab = storedTab('s-tab', T0 - HOUR, T0 - MINUTE, 'bs-live')
  tab.set(KEY.window_open, 'initiator-page')
  const page = make({ tab, browser, prerendering: true })
  const ids = page.C.session.begin(T0)
  const whilePrerendering = page.tab.get(KEY.window_open)
  page.tab.clear() // shown: the tab's own storage, without what the prerendered page wrote
  page.document.prerendering = false
  page.fire('prerenderingchange')
  cases.prerender = { ids, whilePrerendering, shown: held(page).tab }
}

{ // another tab's session is taken at the next activity: tab (it began before this one ended), idle, max
  const take = (had, started, last, at) => {
    const browser = storedBrowser('bs-mine', had.start, had.last)
    const page = make({ browser })
    page.C.session.begin(had.last)
    browser.set(KEY.browser_session, 'bs-other')
    browser.set(KEY.browser_clock, JSON.stringify({ b: 'bs-other', s: started, l: last }))
    page.C.session.admit('r', raw('click', at))
    return { whys: rotations(page.log), sent: page.log.filter((entry) => entry[0] === 'transport').map((e) => e[1]) }
  }
  cases.taken = {
    tab: take({ start: T0, last: T0 }, T0 + MINUTE, T0 + MINUTE, T0 + 2 * MINUTE),
    idle: take({ start: T0, last: T0 }, T0 + 40 * MINUTE, T0 + 40 * MINUTE, T0 + 41 * MINUTE),
    max: take({ start: T0 - 23 * HOUR - 50 * MINUTE, last: T0 }, T0 + 11 * MINUTE, T0 + 11 * MINUTE, T0 + 12 * MINUTE)
  }
}

{ // reset(): the browser's next session from this tab, with a new tab id; the visitor changes between the batches
  const browser = new Map()
  const page = make({ browser })
  const before = page.C.session.begin(T0)
  page.C.session.restart(T0 + MINUTE, CFG.session.why.reset, () => page.log.push(['between']))
  cases.reset = { before, log: page.log, stored: browser.get(KEY.browser_session) }
}

{ // a new tab session carries the visitor id and hash another tab stored (its reset() or identify())
  const page = make({ follow: { id: 'visitor-new', h: 'hash-new' } })
  page.C.session.begin(T0)
  page.C.session.admit('r', raw('click', T0 + 40 * MINUTE))
  cases.follow = { steps: page.log.map((entry) => entry[0]), log: page.log }
}

console.log(JSON.stringify(cases))
