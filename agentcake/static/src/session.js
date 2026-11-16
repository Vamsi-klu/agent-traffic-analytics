// Agent Cake page script, part: the session id, one per browser tab, cut by PostHog's time rules.
//
// A session is what one tab did with no more than CFG.session.idle_ms (30 minutes) between two moments of activity,
// and at most CFG.session.max_ms (24 hours) long: the rules of posthog-js's packages/browser/src/sessionid.ts
// (DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS, SESSION_LENGTH_LIMIT_MILLISECONDS; posthog-js, MIT). Unlike PostHog, which
// shares one session between the tabs of a site, each tab keeps its own in sessionStorage, as cake.js always has: a
// human in one tab and an agent in another never share a timeline.
//
// Activity is what PostHog counts: its recorder's user interactions (lazy-loaded-session-recorder.ts, ACTIVE_SOURCES:
// mouse moves and clicks, scrolling, a resized window, input, touch), read here from the raw input records that stand
// for them (CFG.session.activity_raw, and a geometry record made by a resize), and a page view (PostHog's $pageview).
// The first activity after the idle time, or after the session has lasted max_ms, starts a new session: what is
// buffered goes first under the old id, then the new id is kept, its first record says why it began (a "session"
// record, with the page's source fields: PostHog takes a session's entry properties from its first event), and the
// replay starts over with a full snapshot, as PostHog's recorder restarts on a new session id. While the tab is idle,
// replay events are dropped, as PostHog's recorder drops them while idle (they show a page nobody acts on, and the
// next session's snapshot shows the page again); signal records still go, under the session they belong to.
// window.cake.reset() begins a new session the same way at once, its record saying "reset" (identify.js).
// The page number and the once-per-visit frame check start over with a new session. AgentCake's collector applies
// the same rules to uploads from scripts that do not (session_split.py), from the same settings.

var current = null // { id, start, last }: the session and its activity clock, epoch ms
var written = 0 // when the clock was last written to sessionStorage
var activeRaw = {}
CFG.session.activity_raw.forEach(function (type) {
  activeRaw[type] = true
})

function readClock() {
  try {
    var clock = JSON.parse(C.store.get(CFG.storage.clock) || 'null')
    return clock && typeof clock.s === 'number' && typeof clock.l === 'number' ? clock : null
  } catch (e) {
    return null
  }
}

function writeClock() {
  written = current.last
  C.store.set(CFG.storage.clock, JSON.stringify({ s: current.start, l: current.last }))
}

function expired(t) {
  return t - current.last > CFG.session.idle_ms || t - current.start > CFG.session.max_ms
}

function isActivity(stream, record) {
  if (stream === 'r') {
    return activeRaw[record.ty] === true || (record.ty === 'geo' && CFG.session.activity_geo.indexOf(record.why) >= 0)
  }
  return stream === 'x' && CFG.session.activity_signals.indexOf(record.ty) >= 0
}

// What starts over with a session: its id, its clock, its page count and its frame check.
function fresh(t) {
  current = { id: C.randomId(), start: t, last: t }
  C.store.set(CFG.storage.session, current.id)
  C.store.remove(CFG.storage.page_number)
  C.store.remove(CFG.storage.frames_done)
  writeClock()
}

// between: what changes after the old session's last batch and before the new one's first (reset(): the visitor id).
function rotate(t, why, between) {
  C.flush(CFG.session.flush_why) // what is buffered belongs to the session that ends
  if (between) between()
  fresh(t)
  C.transport.session(current.id)
  C.push('x', Object.assign({ t: t, ty: CFG.session.record, why: why }, C.source.fields()))
  C.replay.snapshot()
}

function touch(t) {
  if (t > current.last) current.last = t
  if (current.last - written >= CFG.session.persist_every_ms) writeClock()
}

C.session = {
  /** The tab's session id when a page view begins at `now`, a new one when there is none or it has run out. A
   * session kept by an older cake.js has no clock: it goes on from now, as PostHog starts the clock of a session id
   * stored without one. */
  begin: function (now) {
    var id = C.store.get(CFG.storage.session)
    var clock = readClock() || { s: now, l: now }
    current = id ? { id: id, start: clock.s, last: clock.l } : null
    if (!current || expired(now)) fresh(now)
    return current.id
  },
  /** Whether a record may be buffered; an activity record may first start a new session (see the top). */
  admit: function (stream, record) {
    if (!current) return true
    if (isActivity(stream, record)) {
      if (expired(record.t)) {
        rotate(record.t, record.t - current.last > CFG.session.idle_ms ? CFG.session.why.idle : CFG.session.why.max)
      }
      touch(record.t)
      return true
    }
    return stream !== 'e' || C.now() - current.last <= CFG.session.idle_ms
  },
  /** Ends the session at `t` and begins the next one, as the idle time does, for `why` (window.cake.reset(), as
   * posthog-js's reset() calls resetSessionId()): what is buffered goes under the old id, then between() runs. */
  restart: function (t, why, between) {
    if (current) rotate(t, why, between)
  },
  /** The clock goes to sessionStorage now (the page is being left). */
  save: function () {
    if (current) writeClock()
  },
  /** Forgets the session and its clock (the visitor said no). */
  forget: function () {
    current = null
    C.store.remove(CFG.storage.session)
    C.store.remove(CFG.storage.clock)
  }
}
