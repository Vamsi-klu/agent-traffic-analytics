// AgentCake page script, part: small shared helpers.
//
// build_js.py concatenates the parts in agentcake/static/src/ into agentcake/static/cake.js, each inside its own
// function, and gives them in the enclosing scope:
//   C        the parts' private namespace (never a global; parts talk to each other only through it)
//   CFG      the "script" object of agentcake/data/cakejs.json (every number and name the script uses)
//   RUNTIME  values cake fills in when it serves cake.js (site key, settings the site owner turned on)
//   TAG      this <script> element, read while the script first runs
//   BUILD    a short hash of the sources, sent with every page so data can be traced to the script that made it
//   STARTED  performance.now() when cake.js began to run
//
// The helpers here read clocks, sessionStorage and localStorage and keep the list of everything stop() must undo.

var HEX_RADIX = 16 // protocol: hexadecimal digits of an id
var HEX_DIGITS_PER_BYTE = 2 // protocol: one byte is two hexadecimal digits

// Event timestamps are relative to the page's time origin; cake wants epoch milliseconds that compare across pages.
var timeOrigin = performance.timeOrigin || Date.now() - performance.now()

C.off = false

/** Epoch milliseconds for a performance timestamp (event.timeStamp, performance.now()), to CFG.time_precision. */
C.epoch = function (ts) {
  return Math.round((timeOrigin + ts) * CFG.time_precision) / CFG.time_precision
}

C.now = function () {
  return C.epoch(performance.now())
}

/** A coordinate or size rounded the same way as times (the lab recorded both at this precision). */
C.round = function (value) {
  return Math.round(value * CFG.time_precision) / CFG.time_precision
}

/** fn's value, or why it failed: a probe that throws records the reason instead of breaking the page. */
C.safe = function (fn) {
  try {
    return fn()
  } catch (e) {
    return 'error: ' + (e && e.message)
  }
}

/** Bytes (a Uint8Array) as lowercase hexadecimal digits, two per byte. */
C.hex = function (bytes) {
  return Array.prototype.map
    .call(bytes, function (b) {
      return b.toString(HEX_RADIX).padStart(HEX_DIGITS_PER_BYTE, '0')
    })
    .join('')
}

/** A random hexadecimal id for a visit or a page view. Nothing about the device or the time goes into it. */
C.randomId = function () {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID().replace(/-/g, '')
  return C.hex(crypto.getRandomValues(new Uint8Array(CFG.id_bytes)))
}

// sessionStorage and localStorage can be missing or throw (private windows, storage turned off, a full quota; even
// reading the property can throw, so `open` is called inside the try). Then cake.js keeps working without them: a
// page simply starts new ids of its own and nothing is parked for the next page.
function storage(open) {
  return {
    get: function (key) {
      try {
        return open().getItem(key)
      } catch (e) {
        return null
      }
    },
    /** Returns whether the value was stored. */
    set: function (key, value) {
      try {
        open().setItem(key, value)
        return true
      } catch (e) {
        return false
      }
    },
    remove: function (key) {
      try {
        open().removeItem(key)
      } catch (e) {
        return false
      }
      return true
    }
  }
}

/** This tab's storage (sessionStorage): the tab's id, its session, its page count, parked uploads. */
C.store = storage(function () {
  return sessionStorage
})

/** The storage every tab of the site shares (localStorage): the browser's session (session.js). */
C.shared = storage(function () {
  return localStorage
})

/** Records one of cake.js's own failures (where, and the message only) so a broken probe shows up in cake. */
C.fault = function (where, error) {
  if (!C.push) return
  var message = String((error && error.message) || error).slice(0, CFG.limits.error_chars)
  C.push('x', { t: C.now(), ty: 'err', where: where, msg: message })
}

// Everything that has to be undone when the visitor says no (window.cake.stop()): listeners, timers, observers,
// the recorder. Each part registers its own undo here.
var undo = []

C.onStop = function (fn) {
  undo.push(fn)
}

C.listen = function (target, type, fn, options) {
  target.addEventListener(type, fn, options)
  C.onStop(function () {
    target.removeEventListener(type, fn, options)
  })
}

C.every = function (fn, ms) {
  var id = setInterval(fn, ms)
  C.onStop(function () {
    clearInterval(id)
  })
}

C.later = function (fn, ms) {
  var id = setTimeout(function () {
    if (!C.off) fn()
  }, ms)
  C.onStop(function () {
    clearTimeout(id)
  })
}

C.stopAll = function () {
  C.off = true
  undo.splice(0).forEach(function (fn) {
    try {
      fn()
    } catch (e) {
      // Stopping must finish even if one recorder fails to stop; nothing is sent any more, so there is no one to tell.
      return
    }
  })
}
