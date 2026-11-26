// AgentCake page script, part: the session ids. A browser's tabs of a site share one session, cut by PostHog's time
// rules; each tab also has an id and a session of its own, the part of the browser's session AgentCake judges, replays
// and stores.
//
// The rules are posthog-js's (packages/browser/src/sessionid.ts at commit c8f17c66, SessionIdManager and its
// checkAndGetSessionAndWindowId; posthog-js, Apache-2.0), written here in cake.js's own code:
// - The browser's session (`bs` in every batch) is kept in localStorage, so that every tab of the site has the same
//   one: its id alone (CFG.storage.browser_session, which a site's consent code can read as it is) and its clock, when
//   it began and when any tab last saw activity (CFG.storage.browser_clock, naming the session it belongs to). It ends
//   once no tab has seen activity for CFG.session.idle_ms (30 minutes), or once it has lasted CFG.session.max_ms
//   (24 hours): the next activity, in any tab, begins the next one. A tab reads the stored session again at most
//   every CFG.session.persist_every_ms of its activity, and always before ending it for idleness (posthog-js reads its
//   storage again then): another tab's activity keeps the session going, and a session another tab began is taken.
// - The tab's id (`w`, posthog-js's window id) is kept in sessionStorage (CFG.storage.window). A tab that begins the
//   browser's next session gets a new id with it, as posthog-js gives a new window id with a new session id; a tab
//   that takes another tab's session keeps its own. A tab that is a copy of another (duplicated, or opened by
//   window.open with an opener, which copy sessionStorage) is told apart by posthog-js's "primary window exists" mark
//   (CFG.storage.window_open): a page sets it when it starts and removes it when it is left, so a page that finds it
//   set holds a copy of a live page's sessionStorage, and takes a new id and session. posthog-js removes the mark at
//   beforeunload; cake.js at pagehide, which keeps the page fit for the back-forward cache, and sets it again when the
//   page comes back from it. The mark holds the page's own random value, so a page removes no other page's mark.
// - The tab's session (`s`) is cut as cake.js has always cut it, by the same rules on the tab's own clock
//   (sessionStorage CFG.storage.session and CFG.storage.clock), and also ends whenever the browser's session changes:
//   each tab session belongs to one browser session, which its clock names. One kept by an older cake.js, which
//   belongs to none, is not continued.
// A session that is gone from localStorage while this page had it there (another tab's window.cake.stop() or reset(),
// or storage cleared) is never written back: the page's next activity begins the next one, as posthog-js begins a new
// session when the id it stored is gone. Where localStorage takes no writes (a full quota) but sessionStorage does, the
// browser's session is the tab's own, kept in sessionStorage under the same names: the tab's pages go on with it and
// with the tab's session, one session per tab. Where neither can be used (a private window, storage turned off), it
// lives only as long as the page, as posthog-js's does in memory: each such page view is a session of its own. Where
// sessionStorage cannot be used, the same holds for the tab's id and session.
//
// Activity is what PostHog counts: its recorder's user interactions (lazy-loaded-session-recorder.ts, ACTIVE_SOURCES:
// mouse moves and clicks, scrolling, a resized window, input, touch), read here from the raw input records that stand
// for them (CFG.session.activity_raw, and a geometry record made by a resize), and a page view (PostHog's $pageview).
// When an activity ends the tab's session: what is buffered goes first under the old ids, then the new ids are kept,
// the new session's first record says why it began (a "session" record, with the page's source fields: PostHog takes a
// session's entry properties from its first event), and the replay starts over with a full snapshot, as PostHog's
// recorder restarts on a new session id. While the tab is idle, replay events are dropped, as PostHog's recorder drops
// them while idle (they show a page nobody acts on, and the next session's snapshot shows the page again); signal
// records still go, under the session they belong to. window.cake.reset() begins the browser's next session the same
// way at once, its record saying "reset" (identify.js); the other tabs take it at their next activity. The page number
// and the once-per-tab-session frame check start over with a new tab session. AgentCake's collector cuts the tab
// sessions of uploads from scripts that do not cut their own by the same rules, from the same settings
// (session_split.py).

var KEY = CFG.storage
var tab = null // { id, start, last }: this tab's session and its clock, epoch ms
var browser = null // { id, start, last }: the browser's session, as this page last saw it
var windowId = null // this tab's id
var mark = null // this page's value of the mark that it is the tab's live page
var shared = true // false once localStorage refused the browser's session: it is the tab's own from then on
var inShared = false // the browser's session was in localStorage as this page had it: read there, or written there
var synced = 0 // the time of the activity at which the browser's session was last read from localStorage
var tabWritten = 0 // the tab's last activity as last written to sessionStorage
var browserWritten = 0 // the browser's last activity as last written to localStorage
var activeRaw = {}
CFG.session.activity_raw.forEach(function (type) {
  activeRaw[type] = true
})

function parse(text) {
  try {
    return JSON.parse(text || 'null')
  } catch (e) {
    return null
  }
}

function isClock(value) {
  return !!value && typeof value.s === 'number' && typeof value.l === 'number'
}

/** Why a session ({ start, last }) has ended by `t`: idle or max, or null while it lasts. */
function ended(session, t) {
  if (t - session.last > CFG.session.idle_ms) return CFG.session.why.idle
  if (t - session.start > CFG.session.max_ms) return CFG.session.why.max
  return null
}

function isActivity(stream, record) {
  if (stream === 'r') {
    return activeRaw[record.ty] === true || (record.ty === 'geo' && CFG.session.activity_geo.indexOf(record.why) >= 0)
  }
  return stream === 'x' && CFG.session.activity_signals.indexOf(record.ty) >= 0
}

/** The browser's session as localStorage holds it (store: as the tab holds its own, in sessionStorage), or null. A
 * clock that names another session (read between another tab's two writes as it began one) is no clock: the session
 * goes on from `t`, as posthog-js starts the clock of a session id stored without one. */
function storedBrowser(t, store) {
  store = store || C.shared
  var id = store.get(KEY.browser_session)
  if (!id) return null
  var clock = parse(store.get(KEY.browser_clock))
  return isClock(clock) && clock.b === id ? { id: id, start: clock.s, last: clock.l } : { id: id, start: t, last: t }
}

/** Takes another tab's view of the same session: an earlier start (this page read the id before its clock), later
 * activity. */
function merge(stored) {
  if (stored.start < browser.start) browser.start = stored.start
  if (stored.last > browser.last) browser.last = stored.last
}

function writeBrowser() {
  browserWritten = browser.last
  var clock = JSON.stringify({ b: browser.id, s: browser.start, l: browser.last })
  if (shared && C.shared.set(KEY.browser_session, browser.id) && C.shared.set(KEY.browser_clock, clock)) {
    inShared = true
    return
  }
  shared = false // localStorage refused it: from now on the browser's session is the tab's own, in sessionStorage
  C.store.set(KEY.browser_session, browser.id)
  C.store.set(KEY.browser_clock, clock)
}

/** The browser's clock goes to localStorage, unless another tab has begun a session that still lasts (this page takes
 * that one at its next activity) or the session is gone from there (the next activity begins the next one). What
 * another tab stored of this session is kept (merge). Where localStorage takes no writes, to the tab's own. */
function persistBrowser() {
  if (!shared) return writeBrowser()
  var stored = storedBrowser(browser.last)
  if (stored && stored.id !== browser.id && !ended(stored, browser.last)) return
  if (!stored && inShared) return
  if (stored && stored.id === browser.id) merge(stored)
  writeBrowser()
}

function setWindow(id) {
  windowId = id
  C.store.set(KEY.window, id)
}

/** Begins the browser's next session at `t`, from this tab, which gets a new id with it. */
function beginBrowser(t) {
  browser = { id: C.randomId(), start: t, last: t }
  setWindow(C.randomId())
  writeBrowser()
}

/** The browser's session for an activity at `t` (posthog-js checkAndGetSessionAndWindowId): one another tab began and
 * that lasts is taken; one gone from localStorage does not go on (this tab begins the next); else this one goes on,
 * kept going by every tab's activity, until it has ended, when this tab begins the next. Returns why the tab's session
 * ends with it: idle or max (the session this page had ended), tab (another tab began the next one before this one
 * ended, or ended it), or null when it goes on. */
function checkBrowser(t) {
  if (shared && (t < synced || t - synced >= CFG.session.persist_every_ms || ended(browser, t))) {
    synced = t
    var stored = storedBrowser(t)
    if (stored && stored.id === browser.id) merge(stored)
    else if (stored && !ended(stored, t)) {
      var had = browser
      browser = stored
      inShared = true
      return ended(had, t) || CFG.session.why.tab
    } else if (!stored && inShared) {
      var gone = browser
      beginBrowser(t)
      return ended(gone, t) || CFG.session.why.tab
    }
  }
  var why = ended(browser, t)
  if (why) beginBrowser(t)
  return why
}

function writeClock() {
  tabWritten = tab.last
  C.store.set(KEY.clock, JSON.stringify({ s: tab.start, l: tab.last, b: browser.id }))
}

// What starts over with a tab's session: its id, its clock, its page count and its frame check.
function fresh(t) {
  tab = { id: C.randomId(), start: t, last: t }
  C.store.set(KEY.session, tab.id)
  C.store.remove(KEY.page_number)
  C.store.remove(KEY.frames_done)
  writeClock()
}

function ids() {
  return { s: tab.id, bs: browser.id, w: windowId }
}

// Another tab may have changed the visitor id or its identify hash (window.cake.reset() or identify() there, which
// begins the session this tab takes): the tab's next session carries the stored ones, as posthog-js's tabs take a new
// distinct id from the persistence they share.
function followVisitor(t) {
  var taken = C.visitor.follow(t)
  if (!taken) return
  C.transport.visitor(taken.id)
  if (taken.h) C.transport.identity(taken.h)
}

// between: what changes after the old session's last batch and before the new one's first (reset(): the visitor id).
function rotate(t, why, between) {
  C.flush(CFG.session.flush_why) // what is buffered belongs to the session that ends
  followVisitor(t)
  if (between) between()
  // a later page of this tab may have begun a newer tab id (this page is back from the back-forward cache)
  windowId = C.store.get(KEY.window) || windowId
  fresh(t)
  C.transport.session(ids())
  C.push('x', Object.assign({ t: t, ty: CFG.session.record, why: why }, C.source.fields()))
  C.replay.snapshot()
}

function touch(t) {
  if (t > tab.last) tab.last = t
  if (t > browser.last) browser.last = t
  if (tab.last - tabWritten >= CFG.session.persist_every_ms) writeClock()
  if (browser.last - browserWritten >= CFG.session.persist_every_ms) persistBrowser()
}

/** This page is the tab's live page (posthog-js's "primary window exists"). */
function holdTab() {
  mark = mark || C.randomId()
  C.store.set(KEY.window_open, mark)
}

/** The page is left: its mark goes, unless another page of the tab has put its own there. */
function releaseTab() {
  if (C.store.get(KEY.window_open) === mark) C.store.remove(KEY.window_open)
}

/** Whether this page's sessionStorage is a copy of a live page's (see the top); marks the tab as this page's. A page
 * being prerendered holds a copy of its own tab's sessionStorage, which becomes the tab's when the page is shown (what
 * it wrote meanwhile is dropped): it is no copy of another tab, and marks the tab and writes its ids once shown. */
function takeTab() {
  C.listen(window, 'pagehide', releaseTab)
  C.listen(window, 'pageshow', function (event) {
    if (event.persisted) holdTab() // back from the back-forward cache: the tab's live page again
  })
  if (document.prerendering) {
    C.listen(document, 'prerenderingchange', function () {
      holdTab()
      setWindow(windowId)
      C.store.set(KEY.session, tab.id)
      writeClock()
    })
    return false
  }
  var copy = C.store.get(KEY.window_open) !== null
  holdTab()
  return copy
}

C.session = {
  /** The ids a page view begins with at `now`: { s, bs, w }. The stored ones while they last; new ones in a copied tab,
   * after the time rules, and where nothing is stored. */
  begin: function (now) {
    if (takeTab()) {
      C.store.remove(KEY.window)
      C.store.remove(KEY.session)
      C.store.remove(KEY.clock)
    }
    windowId = C.store.get(KEY.window)
    synced = now
    var stored = storedBrowser(now)
    var own = storedBrowser(now, C.store) // kept by an earlier page of the tab where localStorage took no writes
    if (stored && !ended(stored, now)) {
      browser = stored
      inShared = true
    } else if (own && !ended(own, now)) browser = own
    else beginBrowser(now)
    if (!windowId) setWindow(C.randomId())
    var id = C.store.get(KEY.session)
    var clock = parse(C.store.get(KEY.clock))
    tab = id && isClock(clock) && clock.b === browser.id ? { id: id, start: clock.s, last: clock.l } : null
    if (!tab || ended(tab, now)) fresh(now)
    return ids()
  },
  /** Whether a record may be buffered; an activity record may first end the tab's session (see the top). */
  admit: function (stream, record) {
    if (!tab) return true
    if (isActivity(stream, record)) {
      var own = ended(tab, record.t) // the tab's own clock first: its session is cut as it always was
      var changed = checkBrowser(record.t) // always: the browser's session may go on, be taken or begin anew
      var why = own || changed
      if (why) rotate(record.t, why)
      touch(record.t)
      return true
    }
    return stream !== 'e' || C.now() - tab.last <= CFG.session.idle_ms
  },
  /** Begins the browser's next session at `t` from this tab, for `why` (window.cake.reset(), as posthog-js's reset()
   * calls resetSessionId()): what is buffered goes under the old ids, then between() runs. */
  restart: function (t, why, between) {
    if (!tab) return
    beginBrowser(t)
    rotate(t, why, between)
  },
  /** The clocks are written now (the page is being left). */
  save: function () {
    if (!tab) return
    writeClock()
    persistBrowser()
  },
  /** Forgets the ids and their clocks (the visitor said no). */
  forget: function () {
    tab = null
    var own = [KEY.session, KEY.clock, KEY.window, KEY.window_open, KEY.browser_session, KEY.browser_clock]
    own.forEach(function (key) {
      C.store.remove(key)
    })
    C.shared.remove(KEY.browser_session)
    C.shared.remove(KEY.browser_clock)
  }
}
