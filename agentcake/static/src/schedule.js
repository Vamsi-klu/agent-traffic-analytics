// AgentCake page script, part: running the detectors after the page has loaded, a little at a time.
//
// A site that adds cake.js must not get slower. So only what has to see the page from its first moment runs when
// cake.js starts (the input listeners, the replay's first snapshot); every detector waits for the page's load event
// and then runs as one task per idle period of the browser (requestIdleCallback, or a timer where there is none),
// each task well under a long task (50 ms). The tasks' times go to cake in a "tasks" record: how long each took
// ("start" is cake.js's own first task from its first line, after the browser compiled it; "rrweb" the first
// snapshot) and how long after load the last one finished.

var tasks = []
var took = {}
var loadedAt = null
var scheduled = false

function nextTask() {
  scheduled = false
  if (C.off || !tasks.length) return
  var task = tasks.shift()
  var started = performance.now()
  try {
    task.run()
  } catch (e) {
    C.fault(task.name, e)
  }
  took[task.name] = C.round(performance.now() - started)
  schedule()
}

function schedule() {
  if (scheduled || loadedAt === null || !tasks.length) return
  scheduled = true
  if (window.requestIdleCallback) requestIdleCallback(nextTask, { timeout: CFG.idle_timeout_ms })
  else C.later(nextTask, CFG.idle_gap_ms)
}

function loaded() {
  loadedAt = performance.now()
  schedule()
}

C.schedule = {
  /** Starts the queue at the page's load event (at once if the page has loaded already). */
  start: function () {
    if (document.readyState === 'complete') loaded()
    else C.listen(window, 'load', loaded, { once: true })
  },
  /** Queues fn to run in an idle period after load, after the tasks queued before it. */
  afterLoad: function (name, fn) {
    tasks.push({ name: name, run: fn })
    schedule()
  },
  /** Notes the time (ms) of a task that ran outside the queue. */
  took: function (name, ms) {
    took[name] = C.round(ms)
  },
  /** The "tasks" record: each task's time (ms) and how long after load this record was made. */
  report: function () {
    var longest = 0
    Object.keys(took).forEach(function (name) {
      longest = Math.max(longest, took[name])
    })
    var afterLoad = loadedAt === null ? null : C.round(performance.now() - loadedAt)
    return { t: C.now(), ty: 'tasks', after_load_ms: afterLoad, took_ms: took, longest_ms: longest }
  }
}
