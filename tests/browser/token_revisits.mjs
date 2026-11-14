// token_revisits.mjs — the server half when a browser shows a page again (case T8's visits, N1, N2). Chromium,
// WebKit and Firefox through Playwright, headless, each on three sites with cake.js of a scratch `agentcake serve` on
// every page: the Node middleware's test site with its HTML revalidated (no-cache + ETag, so going home again and reloading are
// 304s), the same site with noStore, and the test site's shop (tests/site: no cache headers, so going back shows the
// stored page). Chromium
// runs twice: as Playwright starts it (no back-forward cache, so going back reads the HTTP cache) and with the
// back-forward cache on, as Chrome ships. Each run: open home, follow the link, follow the link home, reload, go back,
// go forward, then an SPA route change (history.pushState). For each page it notes what the site answered (status,
// token id), which token the page sees in its navigation entry (this response's, an earlier one's, none), whether the
// browser kept the page alive (the same document: no new page view), what collect answered the batches that carried
// the token, and which token cake linked the page view to. N1: every page view whose entry had a token is linked to a
// token of its visit; a stored token comes back as reuse, never as replay, and is kept once. N2, with a real token: a
// changed byte is bad, another visit's replay, the same payload signed past the max age stale. Then, with collect's
// first answer to a token turned into a 503, the token goes again until it is taken.
//
//   node tests/browser/token_revisits.mjs [--out <folder>] [--browsers chromium,chromium-bfcache,webkit,firefox]
//                                         [--sites etag,nostore,demo]
//
// tests/browser/test_token_revisits.py runs it from the test suite. Playwright comes from web/node_modules
// (CAKE_PLAYWRIGHT: another playwright-core folder); Chromium is found as web/scripts/shots.mjs finds it (CAKE_CHROME:
// another executable), WebKit and Firefox in Playwright's own cache; cake runs on python3 (CAKE_PYTHON). A browser that
// is not installed is skipped and named in the report. Exit status 1 unless every check passes.
import { mkdirSync, writeFileSync } from "node:fs"
import os from "node:os"
import { createRequire } from "node:module"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { argument, batchOf, openContext, pause, startCake, startShop, today, tokenIn, versionOf } from "./revisit_kit.mjs"

const here = path.dirname(fileURLToPath(import.meta.url))
const repo = path.join(here, "..", "..")
const require = createRequire(import.meta.url)
const { startSite } = require(path.join(repo, "edge", "node", "scripts", "test-site.js"))
const { signPayload, verifyToken } = require(path.join(repo, "edge", "node", "index.js"))

const HAND_OVER_TIMEOUT_MS = 10000 // cake.js sends every 2 s at most while it holds a token
const POLL_MS = 100
const SPA_ROUTE = "/spa-route"
const UNAVAILABLE = 503 // protocol: Service Unavailable, one of cake.js's retry statuses
const NODE_PAGES = ["/", "/next"]
// A page the back-forward cache restores fires no load event: each step waits for the commit, then the document.
const UNTIL_COMMIT = { waitUntil: "commit" }
const PAGE_VIEW_ID = "f".repeat(32) // a page view id as cake.js makes them (16 random bytes, hex)
const PAST_THE_WINDOW_MS = 60000 // how far past the max age the N2 token is signed
const tokensById = new Map() // the tokens pages saw, for the N2 checks; the report keeps ids only
const CLOSED = /has been closed/ // Playwright's error for a page, context or browser closed under a call

// [step, how, where it lands (path and query)] for each site; `home` and `second` are the site's two pages.
const VISITS = {
  node: (base) => [
    ["open home", (page) => page.goto(base + "/"), "/"],
    ["follow the link to the second page", (page) => page.click("#link"), "/next"],
    ["follow the link home (304 unless noStore)", (page) => page.click("#link"), "/"],
    ["reload (304 unless noStore)", (page) => page.reload(), "/"],
    ["go back", (page) => page.goBack(UNTIL_COMMIT), "/next"],
    ["go forward", (page) => page.goForward(UNTIL_COMMIT), "/"],
  ],
  demo: (base) => [
    ["open the shop", (page) => page.goto(base + "/demo"), "/demo"],
    ["follow the link to Canvas Tote Bag", (page) => page.getByRole("link", { name: "Canvas Tote Bag", exact: true }).click(), "/demo/product?id=tote"],
    ["go back (the stored page)", (page) => page.goBack(UNTIL_COMMIT), "/demo"],
    ["go forward (the stored page)", (page) => page.goForward(UNTIL_COMMIT), "/demo/product?id=tote"],
    ["follow the link to all products", (page) => page.getByRole("link", { name: "← All products" }).click(), "/demo"],
    ["reload", (page) => page.reload(), "/demo"],
  ],
}

// What the page itself reads in its navigation entry (what cake.js reads), and its visit id.
function seenByPage(page) {
  return page.evaluate((storageKey) => {
    const entry = performance.getEntriesByType("navigation")[0] || {}
    const cake = (entry.serverTiming || []).find((each) => each.name === "cake")
    return { origin: performance.timeOrigin, type: entry.type ?? null, response_status: entry.responseStatus ?? null,
      transfer_size: entry.transferSize ?? null, delivery_type: entry.deliveryType ?? null,
      server_timing_supported: Array.isArray(entry.serverTiming), token: cake ? cake.description : null,
      visit: sessionStorage.getItem(storageKey) }
  }, "cake_sid")
}

// Every batch cake.js sends in this context, with collect's answer: [{ at, pv, seq, u, st, answer }]. A batch can
// finish while the run closes the context; its answer can no longer be read then (Playwright: "Target page, context
// or browser has been closed"), and the run, which is over, reads no more batches, so it is left out. Any other error
// still fails the script.
function watchBatches(context) {
  const batches = []
  context.on("requestfinished", async (request) => {
    if (request.method() !== "POST" || !new URL(request.url()).pathname.endsWith("/collect")) return
    const batch = batchOf(request.postDataBuffer())
    if (!batch) return
    let response, headers
    try {
      response = await request.response()
      headers = response ? await response.allHeaders() : null
    } catch (error) {
      if (CLOSED.test(String(error?.message))) return
      throw error
    }
    const status = response ? response.status() : null
    const answer = response ? headers["x-cake-token"] || null : "no answer"
    batches.push({ at: batches.length, pv: batch.pv, seq: batch.seq, u: batch.u, st: batch.st || null,
      answer: status === UNAVAILABLE ? `HTTP ${status}` : answer })
  })
  context.on("requestfailed", (request) => {
    if (request.method() !== "POST") return
    const batch = batchOf(request.postDataBuffer())
    const why = (request.failure() || {}).errorText || "unknown"
    if (batch) batches.push({ at: batches.length, pv: batch.pv, seq: batch.seq, u: batch.u, st: batch.st || null, answer: `failed (${why})` })
  })
  return batches
}

async function until(test, timeoutMs = HAND_OVER_TIMEOUT_MS) {
  const deadline = Date.now() + timeoutMs
  for (;;) {
    const found = test()
    if (found || Date.now() > deadline) return found
    await pause(POLL_MS)
  }
}

// One site in one browser: the visits, then the SPA route change; returns the run's record.
async function run(cake, browserName, site, out) {
  const { context, close } = await openContext(browserName)
  const served = []
  const host = site.kind === "node" ? await startSite({ secret: cake.secret(), noStore: site.name === "nostore",
    head: `<script src="${cake.base}/cake.js" data-site="${cake.siteKey}" defer></script>`,
    onResponse: (answer) => served.push(answer) }) : await startShop(cake)
  const base = host.url.replace(/\/$/, "")
  const steps = []
  let spa = null
  let visit = null
  try {
    const page = context.pages()[0] || await context.newPage()
    const batches = watchBatches(context)
    for (const [step, go, landsOn] of VISITS[site.kind](base)) {
      const servedBefore = served.length
      const batchesBefore = batches.length
      await go(page)
      await page.waitForURL((url) => url.pathname + url.search === landsOn, UNTIL_COMMIT)
      await page.waitForFunction(() => document.readyState === "complete")
      const seen = await seenByPage(page)
      visit = visit || seen.visit
      // the same document as an earlier step: the back-forward cache kept it, and with it its page view
      const restored = steps.find((s) => s.seen.origin === seen.origin)
      const carried = seen.token && !restored ? await until(() => batches.find((b) => b.at >= batchesBefore && b.st === seen.token && b.answer)) : null
      const answer = served.slice(servedBefore).filter((s) => NODE_PAGES.includes(s.path)).pop() || null
      steps.push({ step, path: landsOn, seen, alive: Boolean(restored), pv: restored ? restored.pv : carried ? carried.pv : null,
        served: answer && { status: answer.status, token: tokenIn(answer.serverTiming) } })
    }
    spa = await spaRouteChange(page, batches, steps[steps.length - 1])
    for (const s of steps) s.answers = s.alive ? [] : batches.filter((b) => b.pv === s.pv && b.st).map((b) => b.answer)
    await page.screenshot({ path: path.join(out, `revisit-${browserName}-${site.name}.png`) })
    if (visit) await serverHalfShot(context, cake, visit, path.join(out, `server-half-${browserName}-${site.name}.png`))
  } finally {
    await close()
    await (host.close ? host.close() : host.stop())
  }
  return conclude(cake, browserName, site.name, visit, steps, spa)
}

// An SPA's route change keeps the page view and its token: the next batch has the new URL, the same page view, no token.
async function spaRouteChange(page, batches, last) {
  const before = batches.length
  await page.evaluate((route) => history.pushState({}, "", route), SPA_ROUTE)
  await page.mouse.move(40, 40)
  await page.mouse.click(40, 40)
  const next = await until(() => batches.find((b) => b.at >= before && (b.u || "").endsWith(SPA_ROUTE)))
  return { route: SPA_ROUTE, batch_seen: Boolean(next), same_page_view: Boolean(next && last.pv && next.pv === last.pv),
    token_sent_again: Boolean(next && next.st) }
}

async function serverHalfShot(context, cake, visit, file) {
  const page = await context.newPage()
  await page.goto(`${cake.base}/#/sessions/${encodeURIComponent(visit)}`) // the session page
  const half = page.getByRole("heading", { name: "Server half" })
  if (await half.count()) await half.scrollIntoViewIfNeeded()
  await page.screenshot({ path: file, fullPage: true })
  await page.close()
}

// The run's record, with what cake kept: srv rows and the token each page view's batches are linked to.
async function conclude(cake, browserName, siteName, visit, steps, spa) {
  const secret = cake.secret()
  const kept = visit ? cake.rows("SELECT id, pv, reuses, ua_match, lang_match, net_match FROM srv WHERE session_id=? ORDER BY page_ms", [visit]) : []
  const links = visit ? cake.rows("SELECT pv, token_id FROM batches WHERE session_id=? AND token_id IS NOT NULL", [visit]) : []
  const idOf = async (token) => {
    if (!token) return null
    const id = ((await verifyToken(secret, token)).payload || {}).id || "unverified"
    tokensById.set(id, token)
    return id
  }
  const earlier = []
  for (const s of steps) {
    const seenToken = s.seen.token
    s.served_token_id = s.served ? await idOf(s.served.token) : null
    s.token_id = await idOf(seenToken)
    s.token_the_page_sees = !seenToken ? "none" : s.served && s.served.token === seenToken ? "this response's"
      : earlier.includes(seenToken) ? "an earlier response's" : s.served ? "unknown" : "new (no request logged)"
    if (s.alive) s.token_the_page_sees = "the same document (kept alive)"
    s.linked = s.alive || !seenToken ? null : links.some(([pv, id]) => pv === s.pv && id === s.token_id)
    if (seenToken) earlier.push(seenToken)
    if (s.served) s.served = { status: s.served.status, token_id: s.served_token_id }
    delete s.seen.token
    delete s.seen.visit
  }
  const counted = steps.filter((s) => s.linked !== null)
  const reused = steps.filter((s) => (s.answers || []).includes("reuse")).length
  return { browser: browserName, site: siteName, steps, spa, srv_rows: kept.map(([id, pv, reuses, ua, lang, network]) => ({ id, reuses, ua_match: ua, lang_match: lang, net_match: network })),
    n1: { pages_with_a_token: counted.length, linked: counted.filter((s) => s.linked).length },
    reuse_answers: reused, reuses_kept: kept.reduce((sum, row) => sum + row[2], 0),
    replay_answers: steps.flatMap((s) => s.answers || []).filter((a) => a === "replay").length }
}

// N2 with a real token from the browser: one byte changed, another visit, the same payload signed past the max age.
async function n2(cake, token) {
  const secret = cake.secret()
  const { payload } = await verifyToken(secret, token)
  const middle = token.indexOf(".") + 3
  const changed = token.slice(0, middle) + (token[middle] === "A" ? "B" : "A") + token.slice(middle + 1)
  const old = await signPayload(secret, { ...payload, id: `${payload.id}-old`, t: Date.now() - cake.maxAgeMs() - PAST_THE_WINDOW_MS })
  const post = async (st, visit) => {
    const body = { v: 1, k: cake.siteKey, s: visit, pv: PAGE_VIEW_ID, seq: 0, t: Date.now(), u: cake.base + "/", why: "timer", ua: "n2", wd: false, e: [], r: [], x: [], st }
    const response = await fetch(cake.base + "/collect", { method: "POST", body: JSON.stringify(body), headers: { "Content-Type": "text/plain" } })
    return { status: response.status, answer: response.headers.get("x-cake-token") }
  }
  const visit = (letter) => letter.repeat(PAGE_VIEW_ID.length) // a visit id of its own for each check
  return { changed_byte: await post(changed, visit("e")), another_visit: await post(token, visit("d")), past_max_age: await post(old, visit("c")) }
}

// cake.js keeps a page's token until collect has taken it: collect's first answer to it is turned into a 503.
async function untilTaken(cake, browserName) {
  const { context, close } = await openContext(browserName)
  const host = await startSite({ secret: cake.secret(), head: `<script src="${cake.base}/cake.js" data-site="${cake.siteKey}" defer></script>` })
  try {
    let refused = 0
    await context.route("**/collect", async (route) => {
      const batch = batchOf(route.request().postDataBuffer())
      // with the CORS header collect's local listener sends, so the page reads the 503 (not a network error)
      if (batch && batch.st && !refused++) return route.fulfill({ status: UNAVAILABLE, body: "", headers: { "Access-Control-Allow-Origin": "*" } })
      return route.continue()
    })
    const batches = watchBatches(context)
    const page = context.pages()[0] || await context.newPage()
    await page.goto(host.url)
    const token = (await seenByPage(page)).token
    const taken = await until(() => batches.find((b) => b.st === token && b.answer === "ok"))
    return { intercepted: refused > 0, answers: batches.filter((b) => b.st === token).map((b) => b.answer), taken: Boolean(taken) }
  } finally {
    await close()
    await host.close()
  }
}

const passes = (r) => r.n1.linked === r.n1.pages_with_a_token && r.replay_answers === 0 && r.reuse_answers === r.reuses_kept &&
  new Set(r.srv_rows.map((row) => row.id)).size === r.srv_rows.length && r.spa.batch_seen && r.spa.same_page_view && !r.spa.token_sent_again

function describe(r) {
  const lines = r.steps.map((s) => `  ${s.step.padEnd(44)} server ${s.served ? String(s.served.status) : "-  "} ` +
    `page sees ${s.token_the_page_sees.padEnd(30)} collect ${(s.answers || []).join(",") || "-"}${s.linked === false ? "  NOT LINKED" : ""}`)
  return [`${r.browser} · ${r.site}: N1 ${r.n1.linked}/${r.n1.pages_with_a_token}, srv rows ${r.srv_rows.length}, reuse ${r.reuse_answers}, ` +
    `replay ${r.replay_answers}, SPA route: same page view ${r.spa.same_page_view}, token sent again ${r.spa.token_sent_again}`, ...lines].join("\n")
}

async function main() {
  const out = path.resolve(argument("--out", path.join(os.tmpdir(), "agentcake-evidence", today(), "token-revisits")))
  const browsers = argument("--browsers", "chromium,chromium-bfcache,webkit,firefox").split(",")
  const sites = argument("--sites", "etag,nostore,demo").split(",").map((name) => ({ name, kind: name === "demo" ? "demo" : "node" }))
  mkdirSync(out, { recursive: true })
  const cake = await startCake()
  const report = { versions: {}, skipped: {}, runs: [], n2: null, until_taken: {} }
  let failures = 0
  try {
    for (const browserName of browsers) {
      try {
        report.versions[browserName] = await versionOf(browserName)
      } catch (error) {
        report.skipped[browserName] = String(error.message || error).split("\n")[0]
        console.log(`${browserName}: skipped (${report.skipped[browserName]})`)
        continue
      }
      for (const site of sites) {
        const result = await run(cake, browserName, site, out)
        report.runs.push(result)
        if (!passes(result)) failures++
        console.log(describe(result))
      }
      report.until_taken[browserName] = await untilTaken(cake, browserName)
      console.log(`${browserName}: first answer 503 -> ${report.until_taken[browserName].answers.join(",")}`)
      if (!report.until_taken[browserName].taken) failures++
    }
    const first = report.runs.find((r) => r.steps[0].token_id)
    const token = first ? tokensById.get(first.steps[0].token_id) : null
    report.n2 = token ? await n2(cake, token) : null
    const expected = { changed_byte: "bad", another_visit: "replay", past_max_age: "stale" }
    for (const [check, answer] of Object.entries(expected)) {
      if (!report.n2 || report.n2[check].answer !== answer || report.n2[check].status !== 204) failures++
    }
    console.log(`N2 with a real token: ${JSON.stringify(report.n2)}`)
  } finally {
    await cake.stop()
  }
  writeFileSync(path.join(out, "token-revisits.json"), `${JSON.stringify(report, null, 2)}\n`)
  console.log(failures ? `${failures} check(s) failed` : "every page view's token is linked to its visit (N1), stored tokens are reuse, N2 holds")
  process.exitCode = failures ? 1 : 0
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
