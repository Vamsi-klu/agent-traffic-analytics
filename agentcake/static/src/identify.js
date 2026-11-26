// AgentCake page script, part: window.cake.identify(id) and window.cake.reset(), as posthog-js has them.
//
// A site with sign-in may call window.cake.identify(<its own id for the visitor>) once they sign in, and
// window.cake.reset() when they sign out, so that AgentCake counts them as one visitor on every browser and device
// they sign in on. That is PostHog's person (posthog-js packages/browser/src/posthog-core.ts identify() and reset(),
// Apache-2.0; PostHog's nodejs/src/ingestion/common/persons/person-merge-service.ts, MIT): identify() links the
// anonymous id to the site's id, and the server merges the two, the anonymous id's earlier events included; reset()
// begins a new anonymous id and a new session, so that the next person to sign in on a shared computer is not merged
// into the last one.
// Unlike posthog-js, the site's id never leaves the browser: cake.js sends only the SHA-256 of the site key, a ":" and
// the id (CFG.identify), in hexadecimal, made with the browser's SubtleCrypto; the site key makes the same id give
// another hash on another site. Where SubtleCrypto is missing (a page that is not https or localhost), identify()
// does nothing but note why. The hash is kept with the visitor id (visitor.js), and from then on every batch carries
// it (`idh`, docs/collect-format.md), on this page and on every later page view in this browser.
// identify() with the hash already kept does nothing, as posthog-js does for the distinct id it already has; with
// another one (a sign-in without reset() after the last sign-out) the hash is replaced, as posthog-js then changes the
// distinct id without merging. Like posthog-js, it takes a non-empty string or a number, and refuses the words
// CFG.identify.refused (placeholders, not ids).
// Before cake.js starts (data-consent="required" without start() yet, or calls queued before it loaded) nothing is
// stored or sent: identify() waits for start; reset() deletes the stored visitor id, hash and session ids at once (the
// browser's too: no other tab writes it back), so that start() begins new ones. window.cake.stop() drops whatever is
// waiting (cake_main.js).

var siteKey = null // set when cake.js starts: the salt of the hash
var generation = 0 // reset() and stop() raise it: a hash still being made for an identity before them is dropped
var hashing = Promise.resolve() // hashes are made one after the other, in the order identify() was called
var markStarted = null
var started = new Promise(function (resolve) {
  markStarted = resolve
})

/** The id as a string, as posthog-js's identify() takes it, or null when it is not one. */
function usable(id) {
  var text = typeof id === 'number' && isFinite(id) ? String(id) : id
  if (typeof text !== 'string' || !text.trim()) return null
  return CFG.identify.refused.indexOf(text.toLowerCase()) >= 0 ? null : text
}

function digest(id) {
  var text = new TextEncoder().encode(siteKey + CFG.identify.separator + id)
  return crypto.subtle.digest(CFG.identify.algorithm, text).then(function (buffer) {
    return C.hex(new Uint8Array(buffer))
  })
}

function keep(hash) {
  if (hash === C.visitor.hash()) return
  C.visitor.identify(hash, C.now())
  C.transport.identity(hash)
}

function hashThenKeep(id, asked) {
  if (C.off || asked !== generation) return null
  if (!(window.crypto && crypto.subtle)) {
    C.fault(CFG.identify.fault, CFG.identify.no_crypto)
    return null
  }
  return digest(id).then(function (hash) {
    if (!C.off && asked === generation) keep(hash)
  })
}

C.identity = {
  /** cake.js has started (cake_main.js, once its batches have a header): identify() may hash and keep. */
  start: function (key) {
    siteKey = key
    markStarted()
  },
  /** window.cake.identify(id) */
  identify: function (id) {
    if (C.off) return
    var text = usable(id)
    var asked = generation
    hashing = hashing
      .then(function () {
        return started
      })
      .then(function () {
        if (text !== null) return hashThenKeep(text, asked)
        C.fault(CFG.identify.fault, CFG.identify.not_an_id) // why, never the value itself
        return null
      })
      .catch(function (e) {
        C.fault(CFG.identify.fault, e)
      })
  },
  /** window.cake.reset() */
  reset: function () {
    if (C.off) return
    generation++
    if (siteKey === null) {
      C.visitor.forget()
      C.session.forget()
      return
    }
    var now = C.now()
    C.session.restart(now, CFG.session.why.reset, function () {
      C.transport.visitor(C.visitor.renew(now))
    })
  },
  /** The visitor said no (window.cake.stop()): a hash still being made is dropped. */
  forget: function () {
    generation++
  }
}
