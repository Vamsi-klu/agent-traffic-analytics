// Agent Cake page script, part: probes for a browser driven over the DevTools protocol, stream "x".
//
// The ideas of these checks come from rebrowser-bot-detector (github.com/rebrowser/rebrowser-bot-detector, commit
// 55fa59b); the code is our own. That repository declares MIT in its package.json but has no licence file, so none of
// its code is used (our rule: no code without a licence). The ideas:
//   1. A DevTools-protocol client with the Runtime domain on (Puppeteer, Playwright) has console messages serialised
//      at once, so a logged error is formatted right away: Error.prepareStackTrace runs for it and its name is read
//      more often (research lab, 11/11: per round 1 formatting and 3 name reads for Playwright, 0 and 1 for Claude in
//      Chrome).
//   2. Chrome ignores a burst of same-document history updates beyond its IPC flooding limit, unless it was started
//      with --disable-ipc-flooding-protection, as Puppeteer and Playwright start it.
//   3. A document the automation tool served itself has a navigation entry no network or service worker made.
//   4. Code a DevTools client evaluates in the page leaves its own frames on the call stack (Puppeteer's pptr: URLs,
//      Playwright's UtilityScript), visible from inside the page's DOM lookups. Off unless the site owner turns it
//      on, since it wraps the site's own DOM methods.
// Field names follow the research lab's (runtimeEnableLeak, ipcFlooding.all300, …): cake's environment rules
// read them.

// ---------------------------------------------------------------- 1. the logged-error probe
var leak = { rounds: 0, prepareStackTraceCount: 0, nameGetterCount: 0, stackLookupCount: 0, firstHitRound: null }

// V8's own format, for any other error formatted while the counting hook is in place.
function plainStack(error, callSites) {
  return [String(error)]
    .concat(
      callSites.map(function (site) {
        return '    at ' + site
      })
    )
    .join('\n')
}

function countFormatting() {
  var own = Object.getOwnPropertyDescriptor(Error, 'prepareStackTrace')
  if (own && !own.configurable) return // the page fixed it: this round cannot see formatting
  var watched = new Error(CFG.env.cdp_message)
  var outer = Error.prepareStackTrace
  Object.defineProperty(Error, 'prepareStackTrace', {
    configurable: true,
    writable: true,
    value: function (error, callSites) {
      if (error === watched) leak.prepareStackTraceCount++
      return outer ? outer(error, callSites) : plainStack(error, callSites)
    }
  })
  try {
    console.debug(watched)
  } finally {
    if (own) Object.defineProperty(Error, 'prepareStackTrace', own)
    else delete Error.prepareStackTrace
  }
}

function countReads(property, field) {
  var watched = new Error(CFG.env.cdp_message)
  var value = property === 'name' ? watched.name : ''
  Object.defineProperty(watched, property, {
    configurable: true,
    get: function () {
      leak[field]++
      return value
    }
  })
  console.debug(watched)
}

function probeRound() {
  leak.rounds++
  countFormatting()
  countReads('name', 'nameGetterCount')
  countReads('stack', 'stackLookupCount')
  var nameReadsPerRound = leak.nameGetterCount / leak.rounds
  var seen = leak.prepareStackTraceCount > 0 || leak.stackLookupCount > 0
  seen = seen || nameReadsPerRound > CFG.env.cdp_name_lookups_per_round
  if (seen && leak.firstHitRound === null) leak.firstHitRound = leak.rounds
  if (!seen && leak.rounds < CFG.env.cdp_rounds) {
    C.later(probeRound, CFG.env.cdp_round_ms)
    return
  }
  var copy = {}
  Object.keys(leak).forEach(function (key) {
    copy[key] = leak[key]
  })
  C.push('x', { t: C.now(), ty: 'cdp', runtimeEnableLeak: copy })
}

// ---------------------------------------------------------------- 2. history writes in a hidden frame
// A burst of history writes makes Chrome's browser process queue them, and any synchronous call into it meanwhile
// (navigator.plugins, Notification.permission, the site's own document.cookie) waits, ~0.1 s for 300 at once. So
// the writes go in short bursts (CFG.env.frame_burst_writes every frame_burst_gap_ms), still well inside Chrome's
// counting window, and cake_main.js runs this once per visit, when idle. The frame is marked, so raw.js does not
// report it and rrweb records only an empty placeholder for it; calls done(record) when finished.
function frameChecks(done) {
  var frame = document.createElement('iframe')
  frame.setAttribute(CFG.env.probe_attr, '')
  frame.style.display = 'none'
  var record = { ty: 'frames' }
  var finish = function () {
    frame.remove()
    record.t = C.now()
    done(record)
  }
  try {
    ;(document.body || document.documentElement).appendChild(frame)
    record.iframeSharesRealm = frame.contentWindow.Navigator === window.Navigator
  } catch (e) {
    record.error = String(e)
    finish()
    return
  }
  var frameHistory = frame.contentWindow.history
  var target = CFG.env.frame_history_writes
  var written = 0
  var stoppedBy = null
  record.longest_burst_ms = 0
  var burst = function () {
    var started = performance.now()
    var until = Math.min(written + CFG.env.frame_burst_writes, target)
    while (written < until && stoppedBy === null) {
      try {
        frameHistory.replaceState({ n: written + 1 }, '')
        written++
      } catch (e) {
        stoppedBy = String(e.name || e)
      }
    }
    record.longest_burst_ms = Math.max(record.longest_burst_ms, C.round(performance.now() - started))
    if (written < target && stoppedBy === null) {
      C.later(burst, CFG.env.frame_burst_gap_ms)
      return
    }
    // A throttled write is dropped without an error: the state shows how many went through.
    var applied = frameHistory.state ? frameHistory.state.n : null
    record.ipcFlooding = { applied: applied, error: stoppedBy, all300: applied === target }
    finish()
  }
  burst()
}

// ---------------------------------------------------------------- 3. how the document arrived
function documentInterception() {
  var nav = performance.getEntriesByType('navigation')[0]
  if (!nav) return null
  var noHop = nav.nextHopProtocol === ''
  var noWorker = nav.workerStart === 0 && (nav.deliveryType || '') === ''
  return {
    nextHopProtocol: nav.nextHopProtocol,
    transferSize: nav.transferSize,
    deliveryType: nav.deliveryType,
    workerStart: nav.workerStart,
    intercepted: noHop && noWorker && nav.transferSize > 0
  }
}

// ---------------------------------------------------------------- 4. who calls the page's DOM lookups
var hookHits = []
var lookups = { checked: 0, total: 0 }

function noteLookup(method, argument) {
  lookups.total++
  if (lookups.checked >= CFG.env.hook.checks_max || hookHits.length >= CFG.env.hook.hits_max) return
  lookups.checked++
  var stack = String(new Error(CFG.env.cdp_message).stack || '')
  var hit = { fn: method, arg: String(argument).slice(0, CFG.env.hook.arg_chars), t: C.now() }
  var found = false
  Object.keys(CFG.env.hook.markers).forEach(function (flag) {
    hit[flag] = stack.indexOf(CFG.env.hook.markers[flag]) >= 0
    found = found || hit[flag]
  })
  if (!found) return
  hit.stack = stack.split('\n').slice(1, CFG.env.hook.stack_frames + 1).join(' | ').slice(0, CFG.env.stack_chars)
  hookHits.push(hit)
}

function watchDomLookups() {
  CFG.env.hook.methods.forEach(function (method) {
    var original = document[method]
    if (typeof original !== 'function') return
    var hadOwn = Object.prototype.hasOwnProperty.call(document, method)
    document[method] = function () {
      noteLookup(method, arguments[0])
      return original.apply(this, arguments)
    }
    C.onStop(function () {
      if (hadOwn) document[method] = original
      else delete document[method]
    })
  })
}

C.automation = {
  start: function (watchDom) {
    if (watchDom) watchDomLookups()
  },
  probe: probeRound,
  frameChecks: frameChecks,
  documentInterception: documentInterception,
  /** What the DOM lookups showed so far (only when the site owner turned the watch on). */
  lookups: function () {
    return hookHits.length || lookups.total ? { hookHits: hookHits.slice(), lookups: lookups } : {}
  }
}
