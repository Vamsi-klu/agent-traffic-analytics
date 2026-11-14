// Agent Cake page script, part: the asynchronous environment probes of a page view (plan step S1.3), stream "x".
//
// The research lab's asynchronous checks (env.js, 11/11), in our own code: the worker-consistency and
// native-tampering ideas come from rebrowser-bot-detector (no code of it is used, see automation.js). Added: the
// media-device counts (signal sig-040, and the evaluation's superline comparison) and a font check (sig-030, with
// botscent's width-measuring idea). Every probe has a time limit; all results go to cake in one
// record. Nothing here asks the visitor for a permission: enumerateDevices without a grant gives kinds, no labels,
// and only the counts per kind are kept.

function withTimeout(promise) {
  return new Promise(function (resolve) {
    var timer = setTimeout(function () {
      resolve({ error: 'timeout' })
    }, CFG.probes.timeout_ms)
    promise.then(
      function (value) {
        clearTimeout(timer)
        resolve(value)
      },
      function (e) {
        clearTimeout(timer)
        resolve({ error: String((e && e.message) || e) })
      }
    )
  })
}

// Read in the page and in a worker: automation that patches navigator in the page often forgets workers.
function navigatorFacts() {
  return {
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    languages: navigator.languages,
    hardwareConcurrency: navigator.hardwareConcurrency,
    brands: navigator.userAgentData && navigator.userAgentData.brands
  }
}

function comparable(key, value) {
  if (key !== 'brands' || !value) return JSON.stringify(value)
  return JSON.stringify(
    value
      .map(function (b) {
        return b.brand + '/' + b.version
      })
      .sort()
  )
}

function workerConsistency() {
  return new Promise(function (resolve, reject) {
    var source = 'var navigatorFacts = ' + navigatorFacts.toString() + '; postMessage(navigatorFacts())'
    var url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }))
    var worker = new Worker(url)
    var finish = function () {
      worker.terminate()
      URL.revokeObjectURL(url)
    }
    worker.onmessage = function (e) {
      finish()
      var page = navigatorFacts()
      var differs = Object.keys(page).filter(function (key) {
        var mine = page[key]
        var theirs = e.data[key]
        return mine != null && theirs != null && comparable(key, mine) !== comparable(key, theirs)
      })
      resolve({ differs: differs, worker: e.data })
    }
    worker.onerror = function (e) {
      finish()
      reject(new Error(e.message || 'worker error'))
    }
  })
}

// Native functions and getters that stealth tools replace: not native source any more, or a prototype of their own.
function nativeTampering() {
  var targets = {}
  var getters = CFG.probes.native_getters
  Object.keys(getters).forEach(function (owner) {
    var proto = window[owner] && window[owner].prototype
    getters[owner].forEach(function (name) {
      var d = proto && Object.getOwnPropertyDescriptor(proto, name)
      targets[owner + '.' + name] = d && d.get
    })
  })
  var methods = CFG.probes.native_methods
  Object.keys(methods).forEach(function (owner) {
    var proto = window[owner] && window[owner].prototype
    methods[owner].forEach(function (name) {
      targets[owner + '.' + name] = proto && proto[name]
    })
  })
  var tampered = {}
  Object.keys(targets).forEach(function (key) {
    var fn = targets[key]
    if (typeof fn !== 'function') return
    var reasons = []
    var source = Function.prototype.toString.call(fn)
    if (!/^function [^(]*\(\) \{\s*\[native code\]\s*\}$/.test(source)) {
      reasons.push('toString: ' + source.slice(0, CFG.probes.source_chars))
    }
    if (Object.prototype.hasOwnProperty.call(fn, 'prototype')) reasons.push('has own prototype')
    if (reasons.length) tampered[key] = reasons
  })
  return Promise.resolve({ tampered: tampered })
}

function permissionsMismatch() {
  var notification = window.Notification ? Notification.permission : null
  var answer = function (query) {
    return {
      notificationPermission: notification,
      permissionsQuery: query,
      mismatch: notification === 'denied' && query === 'prompt'
    }
  }
  if (!navigator.permissions) return Promise.resolve(answer(null))
  return navigator.permissions.query({ name: 'notifications' }).then(
    function (status) {
      return answer(status.state)
    },
    function (e) {
      return answer('error: ' + e.message)
    }
  )
}

function uaFullVersion() {
  if (!navigator.userAgentData || !navigator.userAgentData.getHighEntropyValues) return Promise.resolve(null)
  return navigator.userAgentData.getHighEntropyValues(CFG.probes.high_entropy_hints).then(function (values) {
    var brands = (values.fullVersionList || []).map(function (b) {
      return b.brand
    })
    values.chromiumWithoutGoogleChrome = brands.indexOf('Chromium') >= 0 && brands.indexOf('Google Chrome') < 0
    return values
  })
}

function mediaDeviceCounts() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return Promise.resolve(null)
  return navigator.mediaDevices.enumerateDevices().then(function (devices) {
    var counts = {}
    devices.forEach(function (device) {
      counts[device.kind] = (counts[device.kind] || 0) + 1
    })
    return counts
  })
}

// Whether a font is installed: a sample's width in that font differs from at least one generic fallback.
function hasFont(context, font) {
  return CFG.probes.font_bases.some(function (base) {
    context.font = CFG.probes.font_px + 'px ' + base
    var fallback = context.measureText(CFG.probes.font_sample).width
    context.font = CFG.probes.font_px + 'px "' + font + '",' + base
    return context.measureText(CFG.probes.font_sample).width !== fallback
  })
}

function fonts() {
  var context = document.createElement('canvas').getContext('2d')
  if (!context) return Promise.resolve(null)
  var found = {}
  CFG.probes.fonts.forEach(function (font) {
    found[font] = hasFont(context, font)
  })
  return Promise.resolve(found)
}

var PROBES = {
  permissions: permissionsMismatch,
  workerConsistency: workerConsistency,
  nativeTampering: nativeTampering,
  uaFullVersion: uaFullVersion,
  mediaDevices: mediaDeviceCounts,
  fonts: fonts
}

var results = null
var reported = false

// One record per page view: when every probe has answered, or at exit with the answers so far (the rest are listed
// as pending), so a page left quickly still reports what had finished.
function report() {
  if (reported || !results) return
  reported = true
  var record = { t: C.now(), ty: 'probes' }
  var pending = Object.keys(PROBES).filter(function (name) {
    if (name in results) record[name] = results[name]
    return !(name in results)
  })
  if (pending.length) record.pending = pending
  C.push('x', record)
}

C.probes = {
  /** Runs every probe; returns a promise that settles once the probes record has been pushed. */
  run: function () {
    results = {}
    return Promise.all(
      Object.keys(PROBES).map(function (name) {
        var answer
        try {
          answer = withTimeout(PROBES[name]())
        } catch (e) {
          answer = Promise.resolve({ error: String(e && e.message) })
        }
        return answer.then(function (value) {
          results[name] = value
        })
      })
    ).then(report)
  },
  atExit: report
}
