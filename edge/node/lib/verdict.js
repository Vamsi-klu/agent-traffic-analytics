"use strict"
/*
 * verdict.js — botscent's server verdict on the page request, when the site hands botscent over (its botscent/server
 * module, or the promise import() returns). Asked once per page and never waited on longer than verdict_wait_ms,
 * counting the first import: a botscent that is missing, slow or failing gives a token without a verdict, never an error
 * and never a slower page than the wait. botscent reads the request's headers only and makes no network request; nothing
 * here adds one.
 */
const NO_VERDICT = Object.freeze({ verdict: null, version: null })
const TIMED_OUT = Symbol("timed out")

// A promise that resolves to TIMED_OUT after `ms`, and a way to stop its timer.
function deadline(ms) {
  let timer = null
  const promise = new Promise((resolve) => {
    timer = setTimeout(() => resolve(TIMED_OUT), ms)
  })
  return { promise, stop: () => clearTimeout(timer) }
}

// The work's value, or null when it fails or the deadline comes first. The work goes first, so work already done wins.
async function before(work, limit) {
  const value = await Promise.race([work.catch(() => null), limit.promise])
  return value === TIMED_OUT ? null : value
}

function verdictSource(botscent) {
  if (!botscent) return null
  let loading = null
  const load = () => {
    loading = loading || Promise.resolve(botscent).then((loaded) => (loaded && typeof loaded.inspect === "function" ? loaded : null), () => null)
    return loading
  }
  return {
    // { verdict, version } for a request in the shape botscent's inspect() reads.
    async read(request, waitMs) {
      const limit = deadline(waitMs)
      try {
        const loaded = await before(load(), limit)
        if (!loaded) return NO_VERDICT
        const version = typeof loaded.VERSION === "string" ? loaded.VERSION : null
        const verdict = await before(new Promise((resolve) => resolve(loaded.inspect(request))), limit)
        return { verdict, version }
      } finally {
        limit.stop()
      }
    },
  }
}

module.exports = { NO_VERDICT, verdictSource }
