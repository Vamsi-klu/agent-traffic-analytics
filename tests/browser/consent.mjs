// GOAL T10's consent cases for the cake.js browser tests (plan step S1.4, GOAL G12; checked by
// tests/test_privacy_recording.py), run by drive.mjs on tests/browser/pages/consent.html: a consent bar whose Accept
// calls window.cake.start() and whose Reject calls window.cake.stop() (cake.js has data-consent="required").
//   consent_reject                refused at once
//   consent_accept_reject         accepted, two presses, refused
//   consent_accept                accepted, then a second page (the "yes" is remembered)
//   consent_reject_while_zipping  refused while batches are being gzipped; the gzips fail after the refusal
//   consent_reject_in_flight      refused with a batch parked in sessionStorage and uploads on their way, which fail
//                                 after the refusal; then accepted again on the next page
// What runs in the page before its own scripts (the page's account of the refusal, a gzip that waits) is set up per
// scenario by CONSENT_PREPARE.
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const CAKEJS = JSON.parse(readFileSync(path.join(here, '..', '..', 'agentcake', 'data', 'cakejs.json'), 'utf8')).script
const STORAGE = CAKEJS.storage
const FAILURES_SETTLE_MS = 1000 // after making uploads or gzips fail: their handlers in cake.js have run
const WAIT_LIMIT_MS = 15000 // longer than cake.js's longest send interval
const RESEND_WAIT_MS = 3000 // a new start sends what is parked in an idle task right after load
const POLL_MS = 50
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// ---------------------------------------------------------------- in the page, before any of its own scripts
// The page's own account of a refusal. It counts the uploads the page starts to cake (fetch or sendBeacon to the
// collect path) and, when the click on #reject reaches the page, notes that moment and the count so far in
// window.__cakeTestWatch. Its listener is the first on window in the capture phase: it runs before cake.js sees the
// click and before the button's own handler calls window.cake.stop(). The moment is on the clock cake.js stamps its
// batches with (performance.timeOrigin + performance.now(), rounded alike). A Date.now() taken by the driver before
// page.click() is not that moment: under load the click reaches the page up to a second later, and a batch cake.js
// makes meanwhile is still from before the refusal.
function watchRefusal({ collectPath, precision }) {
  const watch = { started: 0, refusal: null }
  window.__cakeTestWatch = watch
  const toCake = (url) => {
    try {
      return new URL(String(url), location.href).pathname.endsWith('/' + collectPath)
    } catch (e) {
      return false // not a URL at all: the browser itself refuses it, nothing goes to cake
    }
  }
  const fetch = window.fetch
  window.fetch = function (input) {
    if (toCake(input instanceof Request ? input.url : input)) watch.started++
    return fetch.apply(this, arguments)
  }
  const sendBeacon = navigator.sendBeacon
  navigator.sendBeacon = function (url) {
    if (toCake(url)) watch.started++
    return sendBeacon.apply(this, arguments)
  }
  const onClick = (event) => {
    if (watch.refusal || event.target.id !== 'reject') return
    const t = Math.round((performance.timeOrigin + performance.now()) * precision) / precision
    // cake_loaded: window.cake is cake.js's API, so the button's handler calls stop() at once, not through the queue.
    watch.refusal = { t, started: watch.started, cake_loaded: typeof (window.cake && window.cake.stop) === 'function' }
  }
  window.addEventListener('click', onClick, true)
}

// A CompressionStream whose gzip never finishes by itself: it waits until window.__cakeTestGzip.fail() makes it fail,
// as a real one can (rarely). cake.js then has a batch it meant to gzip and must decide whether to send it plain.
function holdGzip() {
  const held = []
  window.__cakeTestGzip = {
    held: () => held.length,
    fail: () => held.splice(0).forEach((controller) => controller.error(new Error('test: the gzip failed')))
  }
  window.CompressionStream = function () {
    return new TransformStream({
      start: (controller) => {
        held.push(controller)
      },
      transform: () => {}, // nothing comes out
      flush: () => new Promise(() => {}) // and the output never ends
    })
  }
}

const watchArgs = { collectPath: CAKEJS.collect_path, precision: CAKEJS.time_precision }

export const CONSENT_PREPARE = {
  consent_accept_reject: (context) => context.addInitScript(watchRefusal, watchArgs),
  consent_reject_while_zipping: async (context) => {
    await context.addInitScript(watchRefusal, watchArgs)
    await context.addInitScript(holdGzip)
  },
  consent_reject_in_flight: (context) => context.addInitScript(watchRefusal, watchArgs)
}

// ---------------------------------------------------------------- the driver's side
const stored = (page, key) => page.evaluate((name) => sessionStorage.getItem(name), key)
const visitId = (page) => stored(page, STORAGE.session)
const parked = (page) => page.evaluate((key) => JSON.parse(sessionStorage.getItem(key) || '[]').length, STORAGE.pending)
const watched = (page) => page.evaluate(() => window.__cakeTestWatch)

async function waitFor(condition, what) {
  for (let waited = 0; waited < WAIT_LIMIT_MS; waited += POLL_MS) {
    if (condition()) return
    await sleep(POLL_MS)
  }
  throw new Error(`waited ${WAIT_LIMIT_MS} ms for ${what}`)
}

// Every upload to cake waits (its route is kept in uploads.held) until the driver fails it with route.abort() (a
// network error, as when cake is down); once uploads.pass is set they go through.
async function holdUploads(page) {
  const uploads = { held: [], pass: false }
  await page.route((url) => url.pathname.endsWith('/' + CAKEJS.collect_path), (route) => {
    if (uploads.pass) return route.continue()
    uploads.held.push(route)
  })
  return uploads
}

export function consentScenarios(base) {
  async function consentReject(page, log) {
    await page.goto(base + '/pages/consent.html')
    await sleep(800)
    log.marks.reject = Date.now()
    await page.click('#reject')
    log.visit_id_after_reject = await visitId(page)
    await page.click('#press')
    await sleep(2500)
    await page.goto(base + '/pages/consent.html?again=1') // the "no" is remembered: this page never starts cake.js
    await page.click('#press')
    await sleep(1000)
  }

  async function consentAcceptReject(page, log) {
    await page.goto(base + '/pages/consent.html')
    log.marks.accept = Date.now()
    await page.click('#accept')
    await sleep(600)
    await page.click('#press')
    await sleep(400)
    await page.click('#press')
    await sleep(1500)
    log.visit_id_before_reject = await visitId(page)
    log.marks.reject = Date.now() // when this script asked for the click; the refusal itself is log.refusal
    await page.click('#reject')
    log.refusal = (await watched(page)).refusal
    log.visit_id_after_reject = await visitId(page)
    await page.click('#press')
    await sleep(2500) // longer than the shortest send interval: nothing may go
    log.uploads_started = (await watched(page)).started
  }

  async function consentAccept(page, log) {
    await page.goto(base + '/pages/consent.html')
    await page.click('#accept')
    await sleep(800)
    await page.click('#press')
    await page.click('#next') // the "yes" is remembered: the next page queues 'start' before cake.js has loaded
    await page.waitForLoadState('domcontentloaded')
    await page.click('#press')
    await sleep(1200)
  }

  async function consentRejectWhileZipping(page, log) {
    await page.goto(base + '/pages/consent.html')
    await page.click('#accept')
    await page.waitForFunction(() => window.__cakeTestGzip.held() > 0) // the replay's first snapshot, for one
    await page.click('#reject')
    log.refusal = (await watched(page)).refusal
    await page.evaluate(() => window.__cakeTestGzip.fail())
    await sleep(FAILURES_SETTLE_MS)
    log.uploads_started = (await watched(page)).started
    log.parked_after_failures = await parked(page)
  }

  async function consentRejectInFlight(page, log) {
    const uploads = await holdUploads(page)
    await page.goto(base + '/pages/consent.html')
    await page.click('#accept')
    await waitFor(() => uploads.held.length >= 2, 'two uploads on their way')
    await uploads.held.shift().abort() // one fails before the refusal: cake.js parks it for later
    await page.waitForFunction((key) => sessionStorage.getItem(key) !== null, STORAGE.pending)
    log.visit_id_before_reject = await visitId(page)
    await page.click('#reject')
    log.refusal = (await watched(page)).refusal
    log.parked_at_refusal = await parked(page)
    await Promise.all(uploads.held.splice(0).map((route) => route.abort())) // the ones on their way fail now
    await sleep(FAILURES_SETTLE_MS)
    log.uploads_started = (await watched(page)).started
    log.parked_after_failures = await parked(page)
    uploads.pass = true
    await page.click('#next')
    await page.waitForLoadState('domcontentloaded')
    await page.click('#accept') // the visitor agrees after all: a new visit, with nothing from before the refusal
    await sleep(RESEND_WAIT_MS)
    log.visit_id_after_accept = await visitId(page)
  }

  return {
    consent_reject: consentReject,
    consent_accept_reject: consentAcceptReject,
    consent_accept: consentAccept,
    consent_reject_while_zipping: consentRejectWhileZipping,
    consent_reject_in_flight: consentRejectInFlight
  }
}
