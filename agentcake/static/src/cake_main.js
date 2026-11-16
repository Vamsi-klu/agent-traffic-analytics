// Agent Cake page script, part: start, stop and window.cake.
//
// As in cake 0.3.3, a site adds one line:
// <script src="https://<cake>/cake.js" data-site="<key>" defer></script>.
// cake.js sends to the address it was loaded from (…/cake.js → …/collect), keeps the session id in sessionStorage
// (one per tab, cut after 30 minutes without activity or 24 hours: session.js) and the visitor id in localStorage
// (visitor.js).
// Consent, as PostHog 1.0 left it to the site: a site that asks first either adds the tag
// only after the visitor agreed, or adds it with data-consent="required" and calls window.cake.start() once they
// agree; until then cake.js does nothing at all (no listener, no storage, no request). window.cake.stop() (the
// visitor said no) ends recording and sending on this page for good, drops what was not sent yet and forgets the
// session id, the visitor id and its identify hash. window.cake.identify(id) and window.cake.reset() are the sign-in
// and sign-out calls of identify.js. Code that may run before cake.js has loaded can queue the calls, as with
// posthog-js's snippet: window.cake = window.cake || []; window.cake.push('start') (or 'stop', 'reset',
// ['identify', id]); window.cake.push does the same once cake.js runs.
// A site must not get slower for having cake.js: when it starts, it only reads its settings and hooks its
// listeners; the replay's first snapshot is the next task; every detector waits for the page's load event and runs
// as one task per idle period (schedule.js).

var settings = {}
Object.keys(CFG.defaults).forEach(function (key) {
  settings[key] = key in RUNTIME ? RUNTIME[key] : CFG.defaults[key]
})

// What is never recorded: privacy.json's private elements, and the parts of the page the site owner
// lists in AgentCake's settings (hide_selectors). A list this browser cannot read is left out, and said so in the
// upload's faults, rather than stopping the recorders; AgentCake's settings page saves only lists a browser reads.
C.privateSelector = (function (owned) {
  if (!owned) return CFG.privacy.private_selector
  try {
    document.createDocumentFragment().querySelector(owned)
    return CFG.privacy.private_selector + ',' + owned
  } catch (e) {
    C.fault('hide_selectors', e)
    return CFG.privacy.private_selector
  }
})(settings.hide_selectors)

var consentRequired = !!TAG && TAG.getAttribute(CFG.attr.consent) === CFG.consent.required

function collectUrl() {
  if (!TAG || !TAG.src) return null
  try {
    return new URL(CFG.collect_path, TAG.src).href
  } catch (e) {
    return null
  }
}

function siteKey() {
  return (TAG && TAG.getAttribute(CFG.attr.site)) || RUNTIME.site_key || null
}

function nextPageNumber() {
  var n = (Number(C.store.get(CFG.storage.page_number)) || 0) + 1
  C.store.set(CFG.storage.page_number, String(n))
  return n
}

// The page record is made at `now`, the moment begin() chose the page view's session: a moment later the tab's session
// may have reached its idle time, and session.js would begin another before the batches have a header to carry it.
function pageRecord(now) {
  var nav = C.safe(function () {
    return performance.getEntriesByType('navigation')[0]
  })
  var record = {
    t: now,
    ty: 'page',
    n: nextPageNumber(),
    build: BUILD,
    nav: nav && nav.type ? nav.type : null,
    t0: C.round(performance.timeOrigin),
    ran: C.round(performance.now()),
    prerendering: document.prerendering === true,
    vis: document.visibilityState,
    hf: document.hasFocus(),
    hist: history.length,
    hook_dom: settings.hook_dom,
    consent: consentRequired ? 'start' : 'load',
    p: location.pathname // the page view's path (the address every upload carries has it too): navigation.js
  }
  return Object.assign(record, C.source.fields())
}

// Each step is guarded: one recorder failing must not stop the others or break the page.
function step(name, fn) {
  try {
    return fn()
  } catch (e) {
    C.fault(name, e)
    return null
  }
}

// The frame checks (automation.js) once per visit, on the first page view that finishes them; then the tasks record.
function framesThenReport() {
  var report = function () {
    C.push('x', C.schedule.report())
    C.flush('probes')
  }
  if (C.store.get(CFG.storage.frames_done)) {
    report()
    return
  }
  C.automation.frameChecks(function (record) {
    C.push('x', record)
    C.store.set(CFG.storage.frames_done, '1')
    report()
  })
}

// The detectors, one idle task each after load. The frame checks wait for the probes and BotD, whose synchronous
// reads would otherwise wait behind the frame's history writes (automation.js).
function queueDetectors() {
  var answers = []
  C.schedule.afterLoad('parked', C.transport.resendParked)
  C.schedule.afterLoad('markers', C.markers.start)
  C.schedule.afterLoad('env', C.env.environment)
  C.schedule.afterLoad('webgl', C.env.webgl)
  C.schedule.afterLoad('tz', C.env.timeZone)
  C.schedule.afterLoad('auto', function () {
    C.env.automationTraces()
    C.flush('env')
  })
  C.schedule.afterLoad('cdp', C.automation.probe)
  C.schedule.afterLoad('botscent', C.detectors.startBotscent)
  C.schedule.afterLoad('probes', function () {
    answers.push(C.probes.run())
  })
  C.schedule.afterLoad('botd', function () {
    answers.push(C.detectors.runBotd())
    Promise.all(answers).then(function () {
      C.schedule.afterLoad('frames', framesThenReport)
    })
  })
}

var exited = false

// At exit only cheap work: the page is going and the next one is waiting for it.
function onLeave(why) {
  if (!exited) {
    exited = true
    step('globals', C.env.atExit)
    step('probes', C.probes.atExit)
    step('botscent', C.detectors.atExit)
    step('markers', C.markers.atExit)
    C.push('x', { t: C.now(), ty: 'leave', why: why })
  }
  C.session.save()
  C.flush('exit')
}

function stop() {
  if (C.off) return
  C.transport.discard()
  C.stopAll()
  C.identity.forget()
  C.session.forget()
  C.visitor.forget()
  C.store.remove(CFG.storage.page_number)
  C.store.remove(CFG.storage.frames_done)
}

function begin() {
  var url = collectUrl()
  var key = siteKey()
  if (!url || !key) return
  var now = C.now()
  var header = {
    v: CFG.format_version,
    k: key,
    s: C.session.begin(now),
    vid: C.visitor.id(now),
    pv: C.randomId(),
    ua: navigator.userAgent,
    wd: navigator.webdriver === true
  }
  if (C.visitor.hash()) header.idh = C.visitor.hash()
  step('token', C.token.read)
  step('hooks', function () {
    C.automation.start(settings.hook_dom)
  })
  C.push('x', pageRecord(now))
  C.navigation.start()
  step('raw', C.raw.listen)
  C.transport.start(url, header)
  C.identity.start(key)
  C.listen(window, 'pagehide', function () {
    onLeave('pagehide')
  })
  C.listen(document, 'visibilitychange', function () {
    if (document.visibilityState === 'hidden') onLeave('hidden')
    else exited = false
  })
  C.listen(window, 'pageshow', function (e) {
    if (!e.persisted) return
    exited = false // back from the back-forward cache: recording goes on, the next exit is a new one
    C.push('x', { t: C.now(), ty: 'pageshow', persisted: true })
  })
  // The replay's first snapshot in a task of its own, right after this one. rrweb first, then the DOM watch: rrweb
  // adds and removes a frame of its own as it starts, which raw.js must not report.
  C.later(function () {
    var started = performance.now()
    step('rrweb', C.replay.start)
    step('dom_add', C.raw.watchDom)
    C.schedule.took('rrweb', performance.now() - started)
    C.flushSoon('start') // the page record goes now even if rrweb failed (rrweb sends its snapshot itself)
  }, 0)
  queueDetectors()
  C.schedule.start()
  C.schedule.took('start', performance.now() - STARTED)
}

var started = false

function start() {
  if (started || C.off) return
  started = true
  begin()
}

/** One queued call: 'start', 'stop', 'reset', or ['identify', id] (a name with its argument). */
function run(command) {
  var name = Array.isArray(command) ? command[0] : command
  if (name === CFG.consent.commands.stop) stop()
  if (name === CFG.consent.commands.start) start()
  if (name === CFG.identify.commands.reset) C.identity.reset()
  if (name === CFG.identify.commands.identify) C.identity.identify(Array.isArray(command) ? command[1] : undefined)
}

var queued = Array.isArray(window.cake) ? window.cake.slice() : []
window.cake = {
  stop: stop,
  start: start,
  identify: C.identity.identify,
  reset: C.identity.reset,
  push: run,
  version: BUILD
}
queued.forEach(run)
if (!consentRequired) start()
